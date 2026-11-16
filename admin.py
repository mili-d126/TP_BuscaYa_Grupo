from functools import wraps

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from supabase_client import SupabaseError, rpc, select

admin_bp = Blueprint("admin", __name__)


def usuario_es_administrador():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return False

    if not hasattr(g, "usuario_es_administrador"):
        rows = select(
            "usuarios",
            {
                "select": "roles(codigo)",
                "id": f"eq.{usuario_id}",
                "limit": 1,
            },
        )
        rol = (rows[0].get("roles") or {}).get("codigo") if rows else None
        g.usuario_es_administrador = rol == "administrador"

    return g.usuario_es_administrador


def administrador_requerido(view):
    @wraps(view)
    def decorada(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Inicia sesión para continuar.", "danger")
            return redirect(url_for("login"))
        if not usuario_es_administrador():
            flash(
                "No tienes permisos para acceder al panel de administración.",
                "danger",
            )
            return redirect(url_for("perfil"))
        return view(*args, **kwargs)

    return decorada


@admin_bp.app_context_processor
def inyectar_permiso_administrador():
    return {"es_administrador": usuario_es_administrador()}


@admin_bp.route("/admin/dashboard")
@administrador_requerido
def dashboard():
    reportes = select(
        "reportes",
        {
            "select": "id,estado_id,estados_reporte(codigo)",
        },
    )
    usuarios = select("usuarios", {"select": "id"})
    reportes_recientes = select(
        "reportes",
        {
            "select": (
                "id,titulo,fecha,creado_en,usuarios(nombre),"
                "tipos_reporte(nombre),categorias(nombre),"
                "estados_reporte(codigo,nombre)"
            ),
            "order": "creado_en.desc",
            "limit": 20,
        },
    )
    usuarios_recientes = select(
        "usuarios",
        {
            "select": "id,nombre,email,roles(nombre)",
            "order": "nombre.asc",
            "limit": 10,
        },
    )

    reportes_activos = sum(
        1
        for reporte in reportes
        if (reporte.get("estados_reporte") or {}).get("codigo") == "activo"
    )
    reportes_resueltos = sum(
        1
        for reporte in reportes
        if (reporte.get("estados_reporte") or {}).get("codigo") == "resuelto"
    )

    return render_template(
        "admin.html",
        estadisticas={
            "usuarios": len(usuarios),
            "reportes": len(reportes),
            "activos": reportes_activos,
            "resueltos": reportes_resueltos,
        },
        reportes=reportes_recientes,
        usuarios=usuarios_recientes,
    )


@admin_bp.route("/admin/reportes/<int:reporte_id>/estado", methods=["POST"])
@administrador_requerido
def actualizar_estado_reporte(reporte_id):
    codigo_estado = request.form.get("estado", "")
    if codigo_estado not in {"activo", "resuelto"}:
        flash("El estado seleccionado no es válido.", "danger")
        return redirect(url_for("admin.dashboard"))

    try:
        actualizado = rpc(
            "admin_set_report_state",
            {
                "p_reporte_id": reporte_id,
                "p_estado_codigo": codigo_estado,
            },
        )
    except SupabaseError as error:
        if error.code != "PGRST202":
            raise
        flash(
            "Supabase todavía no tiene cargada la función de moderación. "
            "Ejecuta la migración admin_panel_rls en este proyecto.",
            "danger",
        )
        return redirect(url_for("admin.dashboard"))

    if not actualizado:
        flash("No se encontró el reporte para actualizar.", "danger")
        return redirect(url_for("admin.dashboard"))

    flash("El estado del reporte se actualizó.", "success")
    return redirect(url_for("admin.dashboard"))
