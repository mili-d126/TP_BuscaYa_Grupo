import os
import sqlite3
import uuid
from datetime import date
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, jsonify, abort)
from werkzeug.utils import secure_filename

reportes_bp = Blueprint('reportes', __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}

CATEGORIAS = [
    "Documentos", "Celulares y electrónicos", "Llaves", "Billeteras y carteras",
    "Mochilas y bolsos", "Ropa y accesorios", "Útiles y libros", "Otro",
]


# ---------- Utilidades ----------
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_reportes_db():
    """Crea la tabla de reportes y la carpeta de fotos."""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('perdido', 'encontrado')),
            titulo TEXT NOT NULL,
            descripcion TEXT,
            categoria TEXT,
            lugar TEXT,
            latitud REAL NOT NULL,
            longitud REAL NOT NULL,
            fecha TEXT NOT NULL,
            foto TEXT,
            estado TEXT NOT NULL DEFAULT 'activo',
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')
    conn.commit()
    conn.close()


def login_requerido(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Inicia sesión para continuar.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorada


def extension_valida(nombre):
    return '.' in nombre and nombre.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS


def guardar_foto(archivo):
    """Guarda la foto con un nombre único y devuelve el nombre (o None)."""
    if not archivo or archivo.filename == '':
        return None
    if not extension_valida(archivo.filename):
        return False
    ext = secure_filename(archivo.filename).rsplit('.', 1)[1].lower()
    nombre = f"{uuid.uuid4().hex}.{ext}"
    archivo.save(os.path.join(UPLOAD_FOLDER, nombre))
    return nombre


# ---------- Rutas ----------
@reportes_bp.route('/mapa')
@login_requerido
def mapa():
    return render_template('mapa.html', categorias=CATEGORIAS)


@reportes_bp.route('/api/reportes')
@login_requerido
def api_reportes():
    """Devuelve los reportes activos en JSON (lo consume el mapa)."""
    tipo = request.args.get('tipo', '')
    categoria = request.args.get('categoria', '')

    sql = "SELECT id, tipo, titulo, categoria, lugar, latitud, longitud, fecha, foto FROM reportes WHERE estado = 'activo'"
    params = []
    if tipo in ('perdido', 'encontrado'):
        sql += " AND tipo = ?"
        params.append(tipo)
    if categoria in CATEGORIAS:
        sql += " AND categoria = ?"
        params.append(categoria)
    sql += " ORDER BY creado_en DESC"

    conn = get_db()
    filas = [dict(f) for f in conn.execute(sql, params).fetchall()]
    conn.close()
    return jsonify(filas)


@reportes_bp.route('/reportes')
@login_requerido
def lista():
    tipo = request.args.get('tipo', '')
    categoria = request.args.get('categoria', '')
    q = request.args.get('q', '').strip()
    mios = request.args.get('mios') == '1'

    sql = '''SELECT r.*, u.nombre AS autor FROM reportes r
             JOIN usuarios u ON u.id = r.usuario_id WHERE 1=1'''
    params = []
    if mios:
        sql += " AND r.usuario_id = ?"
        params.append(session['usuario_id'])
    else:
        sql += " AND r.estado = 'activo'"
    if tipo in ('perdido', 'encontrado'):
        sql += " AND r.tipo = ?"
        params.append(tipo)
    if categoria in CATEGORIAS:
        sql += " AND r.categoria = ?"
        params.append(categoria)
    if q:
        sql += " AND (r.titulo LIKE ? OR r.descripcion LIKE ? OR r.lugar LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY r.creado_en DESC"

    conn = get_db()
    reportes = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template('reportes.html', reportes=reportes, categorias=CATEGORIAS,
                           tipo=tipo, categoria=categoria, q=q, mios=mios)


@reportes_bp.route('/reportes/nuevo', methods=['GET', 'POST'])
@login_requerido
def nuevo():
    hoy = date.today().isoformat()

    if request.method == 'POST':
        tipo = request.form.get('tipo', '')
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        categoria = request.form.get('categoria', '')
        lugar = request.form.get('lugar', '').strip()
        fecha = request.form.get('fecha', '')

        try:
            latitud = float(request.form.get('latitud', ''))
            longitud = float(request.form.get('longitud', ''))
            if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                raise ValueError
        except ValueError:
            flash('Marca la ubicación del objeto en el mapa.', 'danger')
            return render_template('nuevo_reporte.html', categorias=CATEGORIAS, hoy=hoy, datos=request.form)

        if tipo not in ('perdido', 'encontrado') or not titulo or not fecha:
            flash('Completa el tipo, el título y la fecha.', 'danger')
            return render_template('nuevo_reporte.html', categorias=CATEGORIAS, hoy=hoy, datos=request.form)
        if categoria not in CATEGORIAS:
            categoria = 'Otro'

        foto = guardar_foto(request.files.get('foto'))
        if foto is False:
            flash('La foto debe ser PNG, JPG o WEBP.', 'danger')
            return render_template('nuevo_reporte.html', categorias=CATEGORIAS, hoy=hoy, datos=request.form)

        conn = get_db()
        cur = conn.execute(
            '''INSERT INTO reportes (usuario_id, tipo, titulo, descripcion, categoria,
                                     lugar, latitud, longitud, fecha, foto)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (session['usuario_id'], tipo, titulo, descripcion, categoria,
             lugar, latitud, longitud, fecha, foto)
        )
        conn.commit()
        nuevo_id = cur.lastrowid
        conn.close()

        flash('¡Reporte publicado con éxito!', 'success')
        return redirect(url_for('reportes.detalle', reporte_id=nuevo_id))

    return render_template('nuevo_reporte.html', categorias=CATEGORIAS, hoy=hoy, datos={})


@reportes_bp.route('/reportes/<int:reporte_id>')
@login_requerido
def detalle(reporte_id):
    conn = get_db()
    reporte = conn.execute(
        '''SELECT r.*, u.nombre AS autor, u.telefono AS telefono, u.email AS email
           FROM reportes r JOIN usuarios u ON u.id = r.usuario_id WHERE r.id = ?''',
        (reporte_id,)
    ).fetchone()
    conn.close()
    if reporte is None:
        abort(404)
    return render_template('detalle_reporte.html', r=reporte)


@reportes_bp.route('/reportes/<int:reporte_id>/resolver', methods=['POST'])
@login_requerido
def resolver(reporte_id):
    conn = get_db()
    conn.execute("UPDATE reportes SET estado = 'resuelto' WHERE id = ? AND usuario_id = ?",
                 (reporte_id, session['usuario_id']))
    conn.commit()
    conn.close()
    flash('¡Reporte marcado como resuelto!', 'success')
    return redirect(url_for('reportes.detalle', reporte_id=reporte_id))


@reportes_bp.route('/reportes/<int:reporte_id>/eliminar', methods=['POST'])
@login_requerido
def eliminar(reporte_id):
    conn = get_db()
    fila = conn.execute("SELECT foto FROM reportes WHERE id = ? AND usuario_id = ?",
                        (reporte_id, session['usuario_id'])).fetchone()
    if fila:
        conn.execute("DELETE FROM reportes WHERE id = ?", (reporte_id,))
        conn.commit()
        if fila['foto']:
            ruta = os.path.join(UPLOAD_FOLDER, fila['foto'])
            if os.path.exists(ruta):
                os.remove(ruta)
        flash('Reporte eliminado.', 'success')
    conn.close()
    return redirect(url_for('reportes.lista', mios=1))