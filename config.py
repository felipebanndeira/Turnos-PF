import os
from werkzeug.security import generate_password_hash

# ─── Flask ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "cambiar-en-produccion-por-clave-segura")

# ─── Rutas de datos ───────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")

CLIENTES_FILE = os.path.join(DATA_DIR, "clientes.json")
TURNOS_FILE   = os.path.join(DATA_DIR, "turnos.json")
NEGOCIOS_FILE = os.path.join(DATA_DIR, "negocios.json")

# ─── Administrador ────────────────────────────────────────────────────────────
# Para cambiar la contraseña del admin: modificá ADMIN_PASSWORD_PLAIN
# En producción, mové estas credenciales a variables de entorno.
ADMIN_USERNAME      = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_PLAIN = os.environ.get("ADMIN_PASSWORD", "admin123")
ADMIN_PASSWORD_HASH  = generate_password_hash(ADMIN_PASSWORD_PLAIN)
