import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from reportes import reportes_bp, init_reportes_db

app = Flask(__name__)
app.secret_key = "clave_secreta_buscaya"
app.register_blueprint(reportes_bp)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # fotos de hasta 5 MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "database.db")

# Crear Base de Datos SQLite
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            telefono TEXT,
            foto_perfil TEXT DEFAULT 'default.jpg'
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def home():
    if 'usuario_id' in session:
        return redirect(url_for('perfil'))
    return redirect(url_for('login'))

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        contrasena = request.form['contrasena']

        try:
            # 1. CAMBIADO: Usamos DATABASE_PATH para evitar duplicaciones
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usuarios (nombre, email, contrasena) VALUES (?, ?, ?)",
                (nombre, email, contrasena)
            )
            conn.commit()
            conn.close()
            
            # 2. AÑADIDO: Mensaje de éxito antes de redirigir
            flash('¡Registro completado con éxito! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
            
        except sqlite3.IntegrityError:
            # 3. MEJORADO: Avisamos si el correo ya existe sin borrar los datos del usuario
            flash('El correo electrónico ya se encuentra registrado.', 'danger')
            return render_template('registro.html')

    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        contrasena = request.form['contrasena']

        conn = sqlite3.connect(DATABASE_PATH)

        
        # Este comando hace que podamos acceder a las columnas por su nombre (ej: usuario['contrasena'])
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # 1. Buscamos al usuario únicamente por su correo electrónico
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        usuario = cursor.fetchone()
        conn.close()

        # 2. VALIDACIÓN: Si el correo no existe en la base de datos
        if usuario is None:
            flash('El correo electrónico no está registrado. ¡Regístrate primero!')
            return render_template('login.html')

        # 3. VALIDACIÓN: Si el correo existe, pero la contraseña introducida es incorrecta
        if usuario['contrasena'] != contrasena: 
            flash('La contraseña es incorrecta.')
            return render_template('login.html')

        # 4. Si todo coincide, iniciamos la sesión con total seguridad
        session['usuario_id'] = usuario['id'] # O como se llame tu columna de ID (ej: id_usuario)
        session['nombre'] = usuario['nombre']
        return redirect(url_for('perfil'))

    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # 1. CAMBIADO: Usamos DATABASE_PATH para mantener la consistencia de las rutas
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        nuevo_telefono = request.form['telefono']
        cursor.execute("UPDATE usuarios SET telefono = ? WHERE id = ?", (nuevo_telefono, session['usuario_id']))
        conn.commit()
        conn.close() # Cerramos aquí antes de redirigir

        # 2. AÑADIDO: Mensaje de éxito flotante
        flash('¡Teléfono de contacto guardado con éxito!', 'success')
        return redirect(url_for('perfil'))

    cursor.execute("SELECT nombre, email, telefono, foto_perfil FROM usuarios WHERE id = ?", (session['usuario_id'],))
    datos_usuario = cursor.fetchone()
    conn.close()

    return render_template('perfil.html', usuario=datos_usuario)

@app.route('/perfil/cambiar_contrasena', methods=['POST'])
def cambiar_contrasena():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_id = session['usuario_id']
    contrasena_actual = request.form['contrasena_actual']
    nueva_contrasena = request.form['nueva_contrasena']

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 1. Buscamos la contraseña que está guardada actualmente en la base de datos (columna 3)
    cursor.execute("SELECT contrasena FROM usuarios WHERE id = ?", (usuario_id,))
    resultado = cursor.fetchone()
    
    if resultado is None:
        conn.close()
        flash('Error al procesar el usuario.', 'danger')
        return redirect(url_for('perfil'))
        
    contrasena_guardada = resultado[0]

    # 2. VALIDACIÓN: Verificamos si escribió bien su contraseña actual
    if contrasena_actual != contrasena_guardada:
        conn.close()
        flash('La contraseña actual es incorrecta.', 'danger')
        return redirect(url_for('perfil'))

    # 3. ÉXITO: Si coincide, actualizamos con la nueva contraseña
    cursor.execute("UPDATE usuarios SET contrasena = ? WHERE id = ?", (nueva_contrasena, usuario_id))
    conn.commit()
    conn.close()

    flash('¡Contraseña actualizada con éxito!', 'success')
    return redirect(url_for('perfil'))

if __name__ == '__main__':
    init_db()
    init_reportes_db()   # ← agregar esta línea
    app.run(debug=True)