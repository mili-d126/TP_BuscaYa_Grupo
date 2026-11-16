import os
import unittest
from unittest.mock import patch

from supabase_client import SupabaseError

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-publishable-key")

from app import app


class AdminPanelTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def iniciar_sesion(self):
        with self.client.session_transaction() as usuario_session:
            usuario_session["usuario_id"] = "usuario-de-prueba"

    @patch("admin.select")
    def test_usuario_no_administrador_es_redirigido(self, select):
        self.iniciar_sesion()
        select.return_value = [{"roles": {"codigo": "usuario"}}]

        response = self.client.get("/admin/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/perfil")
        select.assert_called_once()

    @patch("app.select")
    @patch("admin.select")
    def test_enlace_de_admin_solo_aparece_para_administradores(
        self, select_rol, select_perfil
    ):
        self.iniciar_sesion()
        select_perfil.return_value = [
            {"nombre": "Prueba", "email": "prueba@example.com"}
        ]

        select_rol.return_value = [{"roles": {"codigo": "usuario"}}]
        usuario_response = self.client.get("/perfil")
        self.assertNotIn(b"Administraci\xc3\xb3n", usuario_response.data)

        select_rol.return_value = [{"roles": {"codigo": "administrador"}}]
        admin_response = self.client.get("/perfil")
        self.assertIn(b"Administraci\xc3\xb3n", admin_response.data)

    @patch("admin.select")
    def test_administrador_puede_ver_dashboard(self, select):
        self.iniciar_sesion()
        select.side_effect = [
            [{"roles": {"codigo": "administrador"}}],
            [
                {"estados_reporte": {"codigo": "activo"}},
                {"estados_reporte": {"codigo": "resuelto"}},
            ],
            [{"id": "usuario-de-prueba"}],
            [],
            [],
        ]

        response = self.client.get("/admin/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Panel de administraci\xc3\xb3n", response.data)
        self.assertIn(b"Moderaci\xc3\xb3n de reportes recientes", response.data)

    @patch("admin.rpc")
    @patch("admin.select")
    def test_admin_puede_actualizar_estado_de_reporte(self, select, rpc):
        self.iniciar_sesion()
        select.return_value = [{"roles": {"codigo": "administrador"}}]
        rpc.return_value = True

        response = self.client.post(
            "/admin/reportes/10/estado", data={"estado": "resuelto"}
        )

        self.assertEqual(response.status_code, 302)
        rpc.assert_called_once_with(
            "admin_set_report_state",
            {"p_reporte_id": 10, "p_estado_codigo": "resuelto"},
        )

    @patch("admin.rpc")
    @patch("admin.select")
    def test_estado_no_permitido_no_se_envia_a_supabase(self, select, rpc):
        self.iniciar_sesion()
        select.return_value = [{"roles": {"codigo": "administrador"}}]

        response = self.client.post(
            "/admin/reportes/10/estado", data={"estado": "eliminado"}
        )

        self.assertEqual(response.status_code, 302)
        select.assert_called_once()
        rpc.assert_not_called()

    @patch("admin.rpc")
    @patch("admin.select")
    def test_fallo_de_actualizacion_muestra_error_en_vez_de_404(
        self, select, rpc
    ):
        self.iniciar_sesion()
        select.return_value = [{"roles": {"codigo": "administrador"}}]
        rpc.return_value = False

        response = self.client.post(
            "/admin/reportes/10/estado", data={"estado": "resuelto"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/dashboard")
        with self.client.session_transaction() as usuario_session:
            mensajes = usuario_session["_flashes"]
        self.assertIn("No se encontró el reporte", mensajes[0][1])

    @patch("admin.rpc")
    @patch("admin.select")
    def test_funcion_rpc_no_cargada_muestra_error_de_migracion(
        self, select, rpc
    ):
        self.iniciar_sesion()
        select.return_value = [{"roles": {"codigo": "administrador"}}]
        rpc.side_effect = SupabaseError(
            404, "Function missing from schema cache", "PGRST202"
        )

        response = self.client.post(
            "/admin/reportes/10/estado", data={"estado": "resuelto"}
        )

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as usuario_session:
            mensajes = usuario_session["_flashes"]
        self.assertIn("migración admin_panel_rls", mensajes[0][1])


if __name__ == "__main__":
    unittest.main()
