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
    report_photo_url,
    select,
    update,
    upload_report_photo,
)

reportes_bp = Blueprint("reportes", __name__)

EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
SELECT_REPORTE = (
    "*,usuarios(nombre,telefono,email),tipos_reporte(codigo),"
    "categorias(nombre),estados_reporte(codigo),archivos_adjuntos(ruta_storage)"
)


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


def _catalogos(tabla):
    return select(tabla, {"select": "id,codigo,nombre", "order": "nombre.asc"})


def _catalogo_id(tabla, codigo):
    rows = select(
        tabla,
        {"select": "id", "codigo": f"eq.{codigo}", "limit": 1},
    )
    if not rows:
        raise RuntimeError(f"No existe el código {codigo!r} en el catálogo {tabla}.")
    return rows[0]["id"]


def _normalizar_reporte(reporte):
    tipo = reporte.pop("tipos_reporte", None) or {}
    categoria = reporte.pop("categorias", None) or {}
    estado = reporte.pop("estados_reporte", None) or {}
    adjuntos = reporte.pop("archivos_adjuntos", None) or []

    reporte["tipo"] = tipo.get("codigo")
    reporte["categoria"] = categoria.get("nombre")
    reporte["estado"] = estado.get("codigo")
    reporte["fotos"] = [
        report_photo_url(adjunto["ruta_storage"])
        for adjunto in adjuntos
        if adjunto.get("ruta_storage")
    ]
    reporte["foto"] = reporte["fotos"][0] if reporte["fotos"] else None
    return reporte


def _con_autor(reporte):
    perfil = reporte.pop("usuarios", None) or {}
    reporte["autor"] = perfil.get("nombre")
    reporte["telefono"] = perfil.get("telefono")
    reporte["email"] = perfil.get("email")
    return _normalizar_reporte(reporte)


def _render_nuevo(datos, hoy):
    return render_template(
        "nuevo_reporte.html",
        categorias=_catalogos("categorias"),
        hoy=hoy,
        datos=datos,
    )


@reportes_bp.route("/mapa")
@login_requerido
def mapa():
    return render_template("mapa.html", categorias=_catalogos("categorias"))


@reportes_bp.route("/api/reportes")
@login_requerido
def api_reportes():
    params = {
        "select": (
            "id,titulo,lugar,latitud,longitud,fecha,tipo_reporte_id,"
            "categoria_id,estado_id,tipos_reporte(codigo),categorias(nombre)"
        ),
        "estado_id": f"eq.{_catalogo_id('estados_reporte', 'activo')}",
        "order": "creado_en.desc",
    }
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    if tipo in ("perdido", "encontrado"):
        params["tipo_reporte_id"] = (
            f"eq.{_catalogo_id('tipos_reporte', tipo)}"
        )
    if categoria:
        categorias = {item["codigo"] for item in _catalogos("categorias")}
        if categoria in categorias:
            params["categoria_id"] = (
                f"eq.{_catalogo_id('categorias', categoria)}"
            )

    reportes = select("reportes", params)
    return jsonify([_normalizar_reporte(reporte) for reporte in reportes])


@reportes_bp.route("/reportes")
@login_requerido
def lista():
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    q = request.args.get("q", "").strip().casefold()
    mios = request.args.get("mios") == "1"

    params = {"select": SELECT_REPORTE, "order": "creado_en.desc"}
    if mios:
        params["usuario_id"] = f"eq.{session['usuario_id']}"
    else:
        params["estado_id"] = (
            f"eq.{_catalogo_id('estados_reporte', 'activo')}"
        )
    if tipo in ("perdido", "encontrado"):
        params["tipo_reporte_id"] = (
            f"eq.{_catalogo_id('tipos_reporte', tipo)}"
        )
    if categoria:
        categorias = {item["codigo"] for item in _catalogos("categorias")}
        if categoria in categorias:
            params["categoria_id"] = (
                f"eq.{_catalogo_id('categorias', categoria)}"
            )

    reportes = [_con_autor(row) for row in select("reportes", params)]
    if q:
        reportes = [
            row for row in reportes
            if any(
                q in (row.get(field) or "").casefold()
                for field in ("titulo", "descripcion", "lugar")
            )
        ]
    return render_template(
        "reportes.html",
        reportes=reportes,
        categorias=_catalogos("categorias"),
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
            return _render_nuevo(request.form, hoy)

        if tipo not in ("perdido", "encontrado") or not titulo or not fecha:
            flash("Completa el tipo, el título y la fecha.", "danger")
            return _render_nuevo(request.form, hoy)

        categorias = {item["codigo"] for item in _catalogos("categorias")}
        if categoria not in categorias:
            categoria = "otro"

        archivo = request.files.get("foto")
        nombre_archivo = None
        ruta_storage = None
        tipo_mime = None
        if archivo and archivo.filename:
            nombre_archivo = secure_filename(archivo.filename)
            if not extension_valida(nombre_archivo):
                flash("La foto debe ser PNG, JPG o WEBP.", "danger")
                return _render_nuevo(request.form, hoy)
            extension = nombre_archivo.rsplit(".", 1)[1].lower()
            content_types = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }
            tipo_mime = content_types[extension]
            ruta_storage = (
                f"{session['usuario_id']}/{uuid.uuid4().hex}.{extension}"
            )
            upload_report_photo(ruta_storage, archivo.read(), tipo_mime)

        rows = insert(
            "reportes",
            {
                "usuario_id": session["usuario_id"],
                "tipo_reporte_id": _catalogo_id("tipos_reporte", tipo),
                "categoria_id": _catalogo_id("categorias", categoria),
                "estado_id": _catalogo_id("estados_reporte", "activo"),
                "titulo": titulo,
                "descripcion": descripcion,
                "lugar": lugar,
                "latitud": latitud,
                "longitud": longitud,
                "fecha": fecha,
            },
        )
        if not rows:
            raise RuntimeError("Supabase did not return the newly created report.")

        if ruta_storage:
            attachment_rows = insert(
                "archivos_adjuntos",
                {
                    "reporte_id": rows[0]["id"],
                    "ruta_storage": ruta_storage,
                    "nombre_archivo": nombre_archivo,
                    "tipo_mime": tipo_mime,
                },
            )
            if not attachment_rows:
                raise RuntimeError("Supabase did not return the uploaded attachment.")

        flash("¡Reporte publicado con éxito!", "success")
        return redirect(url_for("reportes.detalle", reporte_id=rows[0]["id"]))

    return _render_nuevo({}, hoy)


@reportes_bp.route("/reportes/<int:reporte_id>")
@login_requerido
def detalle(reporte_id):
    rows = select(
        "reportes",
        {
            "select": SELECT_REPORTE,
            "id": f"eq.{reporte_id}",
            "limit": 1,
        },
    )
    if not rows:
        abort(404)
    return render_template(
        "detalle_reporte.html", r=_con_autor(rows[0])
    )


@reportes_bp.route("/reportes/<int:reporte_id>/resolver", methods=["POST"])
@login_requerido
def resolver(reporte_id):
    rows = update(
        "reportes",
        {
            "id": f"eq.{reporte_id}",
            "usuario_id": f"eq.{session['usuario_id']}",
        },
        {"estado_id": _catalogo_id("estados_reporte", "resuelto")},
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
            "select": "id,archivos_adjuntos(ruta_storage)",
            "id": f"eq.{reporte_id}",
            "usuario_id": f"eq.{session['usuario_id']}",
            "limit": 1,
        },
    )
    if rows:
        rutas = [
            adjunto["ruta_storage"]
            for adjunto in rows[0].get("archivos_adjuntos", [])
            if adjunto.get("ruta_storage")
        ]
        delete_rows(
            "reportes",
            {
                "id": f"eq.{reporte_id}",
                "usuario_id": f"eq.{session['usuario_id']}",
            },
        )
        for ruta in rutas:
            delete_report_photo(ruta)
        flash("Reporte eliminado.", "success")
    return redirect(url_for("reportes.lista", mios=1))
