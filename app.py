import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
from dotenv import load_dotenv

from reportes import reportes_bp
from supabase_client import (
    SessionExpiredError,
    SupabaseError,
    save_auth_session,
    select,
    sign_in,
    sign_up,
    update,
    update_password,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Set FLASK_SECRET_KEY in the environment before starting the app.")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_DEBUG") != "1"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.register_blueprint(reportes_bp)


@app.errorhandler(SessionExpiredError)
def handle_expired_session(_error):
    session.clear()
    flash("Tu sesión expiró. Inicia sesión nuevamente.", "danger")
    return redirect(url_for("login"))


@app.route("/")
def home():
    if "usuario_id" in session:
        return redirect(url_for("perfil"))
    return redirect(url_for("login"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        email = request.form["email"].strip().lower()
        contrasena = request.form["contrasena"]

        try:
            response = sign_up(email, contrasena, nombre)
        except SupabaseError as error:
            if error.status in (400, 422):
                flash("El correo electrónico ya se encuentra registrado o no es válido.", "danger")
                return render_template("registro.html")
            raise

        if response.get("access_token"):
            save_auth_session(response)
            flash("¡Registro completado con éxito!", "success")
            return redirect(url_for("perfil"))

        flash("Revisa tu correo para confirmar la cuenta y luego inicia sesión.", "success")
        return redirect(url_for("login"))

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        contrasena = request.form["contrasena"]

        try:
            sign_in(email, contrasena)
        except SupabaseError as error:
            if error.status in (400, 401, 422):
                flash("Correo electrónico o contraseña incorrectos.", "danger")
                return render_template("login.html")
            raise

        return redirect(url_for("perfil"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        update(
            "usuarios",
            {"id": f"eq.{session['usuario_id']}"},
            {"telefono": request.form.get("telefono", "").strip()},
        )
        flash("¡Teléfono de contacto guardado con éxito!", "success")
        return redirect(url_for("perfil"))

    rows = select(
        "usuarios",
        {
            "select": "nombre,email,telefono,foto_perfil",
            "id": f"eq.{session['usuario_id']}",
            "limit": 1,
        },
    )
    if not rows:
        session.clear()
        flash("No se encontró el perfil de esta cuenta. Inicia sesión nuevamente.", "danger")
        return redirect(url_for("login"))

    return render_template("perfil.html", usuario=rows[0])


@app.route("/perfil/cambiar_contrasena", methods=["POST"])
def cambiar_contrasena():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    contrasena_actual = request.form["contrasena_actual"]
    nueva_contrasena = request.form["nueva_contrasena"]

    try:
        verified_session = sign_in(session["email"], contrasena_actual)
    except SupabaseError as error:
        if error.status in (400, 401, 422):
            flash("La contraseña actual es incorrecta.", "danger")
            return redirect(url_for("perfil"))
        raise

    update_password(nueva_contrasena, verified_session["access_token"])
    flash("¡Contraseña actualizada con éxito!", "success")
    return redirect(url_for("perfil"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
