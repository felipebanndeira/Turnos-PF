"""
core/auth.py
============
Autenticación multi-tenant.
"""
import uuid
from functools import wraps
from datetime import date

from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from core.persistence import (
    get_cliente_by_email,
    get_cliente_by_id,
    upsert_cliente,
    get_negocio_by_email,
    upsert_negocio
)
import config


def hash_password(plain: str) -> str:
    return generate_password_hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return check_password_hash(hashed, plain)


# ─── Registro e Ingreso de Negocios (SaaS) ────────────────────────────────────

def registrar_negocio(nombre: str, url_id: str, email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    url_id = url_id.strip().lower()
    if get_negocio_by_email(email):
        return False, "Ya existe un negocio registrado con este email."
    
    negocio = {
        "id": url_id,
        "nombre": nombre.strip(),
        "email": email,
        "password_hash": hash_password(password),
        "config": {
            "nombre": nombre.strip(),
            "rubro": "general",
            "descripcion": "",
            "servicios": [],
            "horarios_atencion": [],
            "intervalo_turno_min": 30,
            "logo_url": ""
        }
    }
    upsert_negocio(negocio)
    return True, negocio["id"]


def login_admin(email: str, password: str) -> tuple[bool, str]:
    negocio = get_negocio_by_email(email)
    # Soporte legacy por si es el primer usuario o entra con config viejo
    if not negocio and email == config.ADMIN_USERNAME:
        if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
            # Crear el negocio default automáticamente
            negocio = {
                "id": "mi-negocio",
                "nombre": "Mi Negocio",
                "email": config.ADMIN_USERNAME,
                "password_hash": config.ADMIN_PASSWORD_HASH,
                "config": {}
            }
            upsert_negocio(negocio)
        else:
            return False, "Credenciales incorrectas."
            
    if not negocio or not verify_password(password, negocio["password_hash"]):
        return False, "Credenciales incorrectas."

    session.clear()
    session["rol"] = "admin"
    session["negocio_id"] = negocio["id"]
    session["nombre"] = negocio["nombre"]
    return True, ""


def logout():
    session.clear()


# ─── Decoradores y Helpers ────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("rol") != "admin" or not session.get("negocio_id"):
            session.clear()
            flash("Acceso restringido al administrador del negocio.", "warning")
            return redirect(url_for("auth.login_admin_view"))
        return f(*args, **kwargs)
    return decorated


def get_current_cliente() -> dict | None:
    if session.get("rol") != "cliente":
        return None
    return get_cliente_by_id(session["cliente_id"], session.get("negocio_id"))
