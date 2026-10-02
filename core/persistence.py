import os
import firebase_admin
from firebase_admin import credentials, firestore

import json

# Inicializar Firebase si aún no se inicializó
CRED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase-credentials.json")

if not firebase_admin._apps:
    try:
        # 1. Intentar leer desde variable de entorno (Vercel)
        if "FIREBASE_CREDENTIALS" in os.environ:
            raw_env = os.environ["FIREBASE_CREDENTIALS"]
            # Vercel a veces escapa los saltos de línea en el private_key
            cred_dict = json.loads(raw_env)
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')
            
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        # 2. Intentar leer desde archivo local (Desarrollo)
        elif os.path.exists(CRED_PATH):
            cred = credentials.Certificate(CRED_PATH)
            firebase_admin.initialize_app(cred)
        else:
            print(f"⚠️ ADVERTENCIA: No se encontró credenciales de Firebase ni en entorno ni en {CRED_PATH}")
    except json.JSONDecodeError as e:
        print(f"⚠️ ERROR de formato JSON en la variable de entorno FIREBASE_CREDENTIALS: {e}")
    except Exception as e:
        print(f"⚠️ ERROR al inicializar Firebase: {e}")

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
