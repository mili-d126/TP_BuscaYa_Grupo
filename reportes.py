import uuid
from datetime import date
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from supabase_client import (
    delete as delete_rows,
    delete_report_photo,
    insert,
    select,
    update,
    upload_report_photo,
)

reportes_bp = Blueprint("reportes", __name__)

EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
CATEGORIAS = [
    "Documentos", "Celulares y electrónicos", "Llaves", "Billeteras y carteras",
    "Mochilas y bolsos", "Ropa y accesorios", "Útiles y libros", "Otro",
]


def login_requerido(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Inicia sesión para continuar.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorada


def extension_valida(nombre):
    return "." in nombre and nombre.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def _con_autor(reporte):
    perfil = reporte.pop("usuarios", None) or {}
    reporte["autor"] = perfil.get("nombre")
    reporte["telefono"] = perfil.get("telefono")
    reporte["email"] = perfil.get("email")
    return reporte


@reportes_bp.route("/mapa")
@login_requerido
def mapa():
    return render_template("mapa.html", categorias=CATEGORIAS)


@reportes_bp.route("/api/reportes")
@login_requerido
def api_reportes():
    params = {
        "select": "id,tipo,titulo,categoria,lugar,latitud,longitud,fecha,foto",
        "estado": "eq.activo",
        "order": "creado_en.desc",
    }
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    if tipo in ("perdido", "encontrado"):
        params["tipo"] = f"eq.{tipo}"
    if categoria in CATEGORIAS:
        params["categoria"] = f"eq.{categoria}"
    return jsonify(select("reportes", params))


@reportes_bp.route("/reportes")
@login_requerido
def lista():
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    q = request.args.get("q", "").strip().casefold()
    mios = request.args.get("mios") == "1"

    params = {"select": "*,usuarios(nombre)", "order": "creado_en.desc"}
    if mios:
        params["usuario_id"] = f"eq.{session['usuario_id']}"
    else:
        params["estado"] = "eq.activo"
    if tipo in ("perdido", "encontrado"):
        params["tipo"] = f"eq.{tipo}"
    if categoria in CATEGORIAS:
        params["categoria"] = f"eq.{categoria}"

    reportes = [_con_autor(row) for row in select("reportes", params)]
    if q:
        reportes = [
            row for row in reportes
            if any(q in (row.get(field) or "").casefold()
                   for field in ("titulo", "descripcion", "lugar"))
        ]
    return render_template(
        "reportes.html",
        reportes=reportes,
        categorias=CATEGORIAS,
        tipo=tipo,
        categoria=categoria,
        q=request.args.get("q", "").strip(),
        mios=mios,
    )


@reportes_bp.route("/reportes/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo():
    hoy = date.today().isoformat()

    if request.method == "POST":
        tipo = request.form.get("tipo", "")
        titulo = request.form.get("titulo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        categoria = request.form.get("categoria", "")
        lugar = request.form.get("lugar", "").strip()
        fecha = request.form.get("fecha", "")

        try:
            latitud = float(request.form.get("latitud", ""))
            longitud = float(request.form.get("longitud", ""))
            if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                raise ValueError
        except ValueError:
            flash("Marca la ubicación del objeto en el mapa.", "danger")
            return render_template(
                "nuevo_reporte.html", categorias=CATEGORIAS, hoy=hoy, datos=request.form
            )

        if tipo not in ("perdido", "encontrado") or not titulo or not fecha:
            flash("Completa el tipo, el título y la fecha.", "danger")
            return render_template(
                "nuevo_reporte.html", categorias=CATEGORIAS, hoy=hoy, datos=request.form
            )
        if categoria not in CATEGORIAS:
            categoria = "Otro"

        archivo = request.files.get("foto")
        foto = None
        if archivo and archivo.filename:
            filename = secure_filename(archivo.filename)
            if not extension_valida(filename):
                flash("La foto debe ser PNG, JPG o WEBP.", "danger")
                return render_template(
                    "nuevo_reporte.html", categorias=CATEGORIAS, hoy=hoy, datos=request.form
                )
            extension = filename.rsplit(".", 1)[1].lower()
            content_types = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }
            object_path = f"{session['usuario_id']}/{uuid.uuid4().hex}.{extension}"
            foto = upload_report_photo(
                object_path, archivo.read(), content_types[extension]
            )

        rows = insert(
            "reportes",
            {
                "usuario_id": session["usuario_id"],
                "tipo": tipo,
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria,
                "lugar": lugar,
                "latitud": latitud,
                "longitud": longitud,
                "fecha": fecha,
                "foto": foto,
            },
        )
        if not rows:
            raise RuntimeError("Supabase did not return the newly created report.")

        flash("¡Reporte publicado con éxito!", "success")
        return redirect(url_for("reportes.detalle", reporte_id=rows[0]["id"]))

    return render_template("nuevo_reporte.html", categorias=CATEGORIAS, hoy=hoy, datos={})


@reportes_bp.route("/reportes/<int:reporte_id>")
@login_requerido
def detalle(reporte_id):
    rows = select(
        "reportes",
        {
            "select": "*,usuarios(nombre,telefono,email)",
            "id": f"eq.{reporte_id}",
            "limit": 1,
        },
    )
    if not rows:
        abort(404)
    return render_template("detalle_reporte.html", r=_con_autor(rows[0]))


@reportes_bp.route("/reportes/<int:reporte_id>/resolver", methods=["POST"])
@login_requerido
def resolver(reporte_id):
    rows = update(
        "reportes",
        {
            "id": f"eq.{reporte_id}",
            "usuario_id": f"eq.{session['usuario_id']}",
        },
        {"estado": "resuelto"},
    )
    if not rows:
        abort(404)
    flash("¡Reporte marcado como resuelto!", "success")
    return redirect(url_for("reportes.detalle", reporte_id=reporte_id))


@reportes_bp.route("/reportes/<int:reporte_id>/eliminar", methods=["POST"])
@login_requerido
def eliminar(reporte_id):
    rows = select(
        "reportes",
        {
            "select": "foto",
            "id": f"eq.{reporte_id}",
            "usuario_id": f"eq.{session['usuario_id']}",
            "limit": 1,
        },
    )
    if rows:
        delete_rows(
            "reportes",
            {
                "id": f"eq.{reporte_id}",
                "usuario_id": f"eq.{session['usuario_id']}",
            },
        )
        if rows[0].get("foto"):
            delete_report_photo(rows[0]["foto"])
        flash("Reporte eliminado.", "success")
    return redirect(url_for("reportes.lista", mios=1))
