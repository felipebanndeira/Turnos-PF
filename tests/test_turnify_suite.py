"""
tests/test_turnify_suite.py
===========================
Suite de Pruebas Automatizadas para Turnify SaaS.
Valida:
1. Rutas y Seguridad (Acceso público, protección privada /admin, hash de contraseñas, login).
2. Motor de Reservas y Disponibilidad (No superposición matemática, duraciones dinámicas, bloqueos).
3. Módulo de Caja y Arqueo (Registro de cobros Efectivo vs Transferencia, balance acumulado y cierre/reinicio).
"""

import unittest
from unittest.mock import patch, MagicMock
import datetime
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

import app as main_app
from app import app
from core import auth
from core import turnos_service
from core import disponibilidad


class TestTurnifySuite(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key-12345"
        self.client = app.test_client()
        self.negocio_id = "negocio-test-suite"

    # ──────────────────────────────────────────────────────────────────────────
    # 1. RUTAS Y SEGURIDAD
    # ──────────────────────────────────────────────────────────────────────────

    def test_01_seguridad_hash_criptografico(self):
        """Verifica generación y validación de contraseñas mediante hashing criptográfico."""
        password_plano = "ClaveSegura123!"
        hashed = auth.hash_password(password_plano)
        
        self.assertNotEqual(password_plano, hashed)
        self.assertTrue(auth.verify_password(password_plano, hashed))
        self.assertFalse(auth.verify_password("PasswordErroneo", hashed))

    @patch("routes.cliente_routes.get_negocio_by_id")
    @patch("routes.cliente_routes.load_config")
    def test_02_ruta_publica_solicitar_turno_200(self, mock_cfg, mock_neg):
        """Verifica que la vista pública de reservas cargue exitosamente (HTTP 200)."""
        mock_neg.return_value = {"id": "barberia-elite", "nombre": "Barbería Elite"}
        mock_cfg.return_value = {
            "nombre": "Barbería Elite",
            "servicios": [{"id": "s1", "nombre": "Corte Clásico", "precio": 3500, "duracion_min": 30}],
            "horarios_atencion": [{"dia": "lunes", "desde": "09:00", "hasta": "18:00"}]
        }
        res = self.client.get("/b/barberia-elite/solicitar")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Barber", res.data)

    def test_03_proteccion_rutas_privadas_admin(self):
        """Verifica que rutas privadas /admin/... redirijan al login si no hay sesión activa."""
        rutas_protegidas = [
            "/admin/",
            "/admin/agenda",
            "/admin/caja",
            "/admin/reportes",
            "/admin/configuracion",
            "/admin/clientes"
        ]
        for ruta in rutas_protegidas:
            res = self.client.get(ruta, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"La ruta {ruta} no está protegida")
            self.assertIn("/admin/login", res.headers.get("Location", ""))

    @patch("core.auth.get_negocio_by_email")
    def test_04_login_admin_exitoso(self, mock_get_neg):
        """Verifica el flujo de autenticación exitosa del administrador con variables de sesión."""
        pwd_hash = generate_password_hash("AdminPass2026!")
        mock_get_neg.return_value = {
            "id": self.negocio_id,
            "nombre": "SaaS Test Studio",
            "email": "admin@turnify.com",
            "password_hash": pwd_hash
        }
        
        with self.client as c:
            res = c.post("/admin/login", data={
                "email": "admin@turnify.com",
                "password": "AdminPass2026!"
            }, follow_redirects=False)
            
            self.assertEqual(res.status_code, 302)
            self.assertIn("/admin/", res.headers.get("Location", ""))
            with c.session_transaction() as sess:
                self.assertEqual(sess.get("rol"), "admin")
                self.assertEqual(sess.get("negocio_id"), self.negocio_id)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. MOTOR DE RESERVAS Y DISPONIBILIDAD
    # ──────────────────────────────────────────────────────────────────────────

    @patch("core.disponibilidad.load_turnos")
    @patch("core.disponibilidad.load_config")
    def test_05_no_superposicion_turnos(self, mock_cfg, mock_turnos):
        """Comprobación matemática: dos reservas no pueden coexistir en el mismo slot horario."""
        mock_cfg.return_value = {
            "intervalo_turno_min": 30,
            "servicios": [{"id": "s1", "duracion_min": 30}],
            "horarios_atencion": [{"dia": "martes", "desde": "10:00", "hasta": "12:00"}]
        }
        # Martes futuro
        fecha_martes = "2026-10-20"
        # Turno confirmado ocupando 10:00 - 10:30
        mock_turnos.return_value = [
            {"fecha": fecha_martes, "hora_inicio": "10:00", "hora_fin": "10:30", "estado": "confirmado"}
        ]
        
        slots = disponibilidad.get_slots_disponibles(fecha_martes, "s1", self.negocio_id)
        # 10:00 no debe estar disponible, 10:30 y 11:00 y 11:30 sí
        self.assertNotIn("10:00", slots)
        self.assertIn("10:30", slots)
        self.assertIn("11:00", slots)

    @patch("core.disponibilidad.load_turnos")
    @patch("core.disponibilidad.load_config")
    def test_06_duraciones_dinamicas_bloque_multiple(self, mock_cfg, mock_turnos):
        """Valida que un servicio de duración mayor (ej. 60 min) ocupe múltiples intervalos y no se solape."""
        mock_cfg.return_value = {
            "intervalo_turno_min": 30,
            "servicios": [
                {"id": "corte_largo", "duracion_min": 60}
            ],
            "horarios_atencion": [{"dia": "miércoles", "desde": "14:00", "hasta": "16:00"}]
        }
        fecha_test = "2026-10-21"
        # Turno de 30 min ocupando 14:30 a 15:00
        mock_turnos.return_value = [
            {"fecha": fecha_test, "hora_inicio": "14:30", "hora_fin": "15:00", "estado": "confirmado"}
        ]
        slots = disponibilidad.get_slots_disponibles(fecha_test, "corte_largo", self.negocio_id)
        # Un servicio de 60m no puede empezar a las 14:00 (llegaría a 15:00 solapando 14:30-15:00)
        self.assertNotIn("14:00", slots)
        # A las 14:30 no puede empezar
        self.assertNotIn("14:30", slots)
        # A las 15:00 dura hasta las 16:00 (cierre) -> Válido
        self.assertIn("15:00", slots)

    @patch("core.disponibilidad.load_config")
    def test_07_dia_cerrado_y_bloqueo_agenda(self, mock_cfg):
        """Valida que días no laborables o franjas de bloqueo no retornen horarios."""
        mock_cfg.return_value = {
            "intervalo_turno_min": 30,
            "servicios": [{"id": "s1", "duracion_min": 30}],
            "horarios_atencion": [{"dia": "lunes", "desde": "09:00", "hasta": "13:00"}],
            "bloqueos": [
                {"fecha": "2026-10-26", "hora_desde": "10:00", "hora_hasta": "12:00"}
            ]
        }
        # Domingo (día sin horario)
        slots_domingo = disponibilidad.get_slots_disponibles("2026-10-25", "s1", self.negocio_id)
        self.assertEqual(slots_domingo, [])

        # Lunes con bloqueo entre 10:00 y 12:00
        slots_lunes = disponibilidad.get_slots_disponibles("2026-10-26", "s1", self.negocio_id)
        self.assertIn("09:00", slots_lunes)
        self.assertIn("09:30", slots_lunes)
        self.assertNotIn("10:00", slots_lunes)
        self.assertNotIn("10:30", slots_lunes)
        self.assertNotIn("11:00", slots_lunes)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. MÓDULO DE CAJA Y ARQUEO DIARIO
    # ──────────────────────────────────────────────────────────────────────────

    @patch("core.turnos_service.upsert_turno")
    @patch("core.turnos_service.get_turno_by_id")
    def test_08_cobro_efectivo_y_transferencia(self, mock_get_turno, mock_upsert):
        """Verifica que el cobro registre correctamente el método de pago (Efectivo vs Transferencia)."""
        mock_get_turno.return_value = {
            "id": "t1",
            "precio_total": 4500,
            "estado": "confirmado",
            "pagos": []
        }
        
        # Cobro Efectivo
        ok_ef, msg_ef = turnos_service.cobrar_turno("t1", "efectivo", 4500, "Pago en mano", self.negocio_id)
        self.assertTrue(ok_ef)
        self.assertEqual(mock_get_turno.return_value["estado"], "cobrado")
        self.assertEqual(mock_get_turno.return_value["cobrado_metodo"], "efectivo")
        self.assertEqual(mock_get_turno.return_value["cobrado_monto"], 4500)

        # Cobro Transferencia
        mock_get_turno.return_value["estado"] = "confirmado"
        ok_tr, msg_tr = turnos_service.cobrar_turno("t1", "transferencia", 5000, "Alias banco", self.negocio_id)
        self.assertTrue(ok_tr)
        self.assertEqual(mock_get_turno.return_value["cobrado_metodo"], "transferencia")
        self.assertEqual(mock_get_turno.return_value["cobrado_monto"], 5000)

    @patch("core.persistence.load_cierres_caja")
    @patch("core.persistence.load_turnos")
    def test_09_calculo_balance_acumulado_caja(self, mock_turnos, mock_cierres):
        """Valida el cálculo de totales en efectivo, transferencia y balance general."""
        mock_cierres.return_value = []
        hoy_str = date.today().isoformat()
        
        mock_turnos.return_value = [
            {
                "id": "t10", "fecha": hoy_str, "estado": "cobrado",
                "pagos": [{"fecha": f"{hoy_str}T10:15:00", "monto": 3000, "metodo": "efectivo"}]
            },
            {
                "id": "t11", "fecha": hoy_str, "estado": "cobrado",
                "pagos": [{"fecha": f"{hoy_str}T11:30:00", "monto": 4500, "metodo": "transferencia"}]
            },
            {
                "id": "t12", "fecha": hoy_str, "estado": "confirmado",
                "pagos": []
            }
        ]
        
        balance = turnos_service.get_balance_caja_hoy(self.negocio_id)
        self.assertEqual(balance["total_efectivo"], 3000)
        self.assertEqual(balance["total_transferencia"], 4500)
        self.assertEqual(balance["total_recaudado"], 7500)
        self.assertEqual(len(balance["movimientos"]), 2)
        self.assertEqual(balance["pendientes_cobro_count"], 1)

    @patch("core.persistence.registrar_cierre_caja")
    @patch("core.persistence.load_cierres_caja")
    @patch("core.persistence.load_turnos")
    def test_10_cierre_y_reinicio_caja(self, mock_turnos, mock_cierres, mock_reg_cierre):
        """Verifica que el cierre genere el snapshot de auditoría y permita reiniciar la caja."""
        hoy_str = date.today().isoformat()
        mock_cierres.return_value = []
        mock_turnos.return_value = [
            {
                "id": "t20", "fecha": hoy_str, "estado": "cobrado",
                "pagos": [{"fecha": f"{hoy_str}T12:00:00", "monto": 6000, "metodo": "efectivo"}]
            }
        ]
        
        ok, msg, snapshot = turnos_service.cerrar_caja_diaria(self.negocio_id, "Admin User")
        self.assertTrue(ok)
        self.assertEqual(snapshot["total_recaudado"], 6000)
        self.assertEqual(snapshot["total_efectivo"], 6000)
        mock_reg_cierre.assert_called_once()


if __name__ == "__main__":
    unittest.main()
