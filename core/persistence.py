import os
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializar Firebase si aún no se inicializó
# Buscamos el archivo de credenciales en el directorio principal
CRED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase-credentials.json")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
    except FileNotFoundError:
        print(f"⚠️ ADVERTENCIA: No se encontró el archivo de credenciales de Firebase en: {CRED_PATH}")
        print("El sistema podría fallar al intentar conectar con la base de datos.")

# Referencia a Firestore
def get_db():
    return firestore.client()

# ─── Negocios (SaaS) ─────────────────────────────────────────────────────────

def load_negocios() -> list:
    db = get_db()
    docs = db.collection("negocios").stream()
    return [doc.to_dict() for doc in docs]

def get_negocio_by_id(url_id: str) -> dict | None:
    db = get_db()
    doc = db.collection("negocios").document(url_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

def get_negocio_by_email(email: str) -> dict | None:
    db = get_db()
    email = email.strip().lower()
    docs = db.collection("negocios").where("email", "==", email).limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None

def upsert_negocio(negocio: dict) -> None:
    db = get_db()
    db.collection("negocios").document(negocio["id"]).set(negocio)

# Helper para cargar config específica de un negocio
def load_config(url_id: str) -> dict:
    negocio = get_negocio_by_id(url_id)
    if negocio and "config" in negocio:
        return negocio["config"]
    return {}

def save_config(url_id: str, new_config: dict) -> None:
    db = get_db()
    db.collection("negocios").document(url_id).update({"config": new_config})


# ─── Clientes ────────────────────────────────────────────────────────────────

def load_clientes(negocio_id: str) -> list:
    db = get_db()
    docs = db.collection("clientes").where("negocio_id", "==", negocio_id).stream()
    return [doc.to_dict() for doc in docs]

def get_cliente_by_id(cliente_id: str, negocio_id: str) -> dict | None:
    db = get_db()
    doc = db.collection("clientes").document(cliente_id).get()
    if doc.exists:
        data = doc.to_dict()
        if data.get("negocio_id") == negocio_id:
            return data
    return None

def get_cliente_by_email(email: str, negocio_id: str) -> dict | None:
    db = get_db()
    email = email.strip().lower()
    docs = db.collection("clientes").where("negocio_id", "==", negocio_id).where("email", "==", email).limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None

def get_cliente_by_telefono(telefono: str, negocio_id: str) -> dict | None:
    db = get_db()
    telefono = telefono.strip()
    docs = db.collection("clientes").where("negocio_id", "==", negocio_id).where("telefono", "==", telefono).limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None

def upsert_cliente(cliente: dict) -> None:
    db = get_db()
    db.collection("clientes").document(cliente["id"]).set(cliente)


# ─── Turnos ──────────────────────────────────────────────────────────────────

def load_turnos(negocio_id: str) -> list:
    db = get_db()
    docs = db.collection("turnos").where("negocio_id", "==", negocio_id).stream()
    return [doc.to_dict() for doc in docs]

def get_turno_by_id(turno_id: str, negocio_id: str) -> dict | None:
    db = get_db()
    doc = db.collection("turnos").document(turno_id).get()
    if doc.exists:
        data = doc.to_dict()
        if data.get("negocio_id") == negocio_id:
            return data
    return None

def upsert_turno(turno: dict) -> None:
    db = get_db()
    db.collection("turnos").document(turno["id"]).set(turno)
