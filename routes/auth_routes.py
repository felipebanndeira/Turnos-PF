from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import core.auth as auth
from core.persistence import get_negocio_by_id

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/")
def index():
    return render_template("auth/landing_saas.html")

@auth_bp.route("/admin/login", methods=["GET", "POST"])
def login_admin_view():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        ok, msg = auth.login_admin(email, password)
        if ok:
            return redirect(url_for("admin.dashboard"))
        flash(msg, "danger")
    return render_template("auth/login_admin.html")

@auth_bp.route("/registro", methods=["GET", "POST"])
def registro_negocio_view():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        url_id = request.form.get("url_id")
        email = request.form.get("email")
        password = request.form.get("password")
        
        ok, msg = auth.registrar_negocio(nombre, url_id, email, password)
        if ok:
            flash("Negocio registrado exitosamente. Ahora podés iniciar sesión.", "success")
            return redirect(url_for("auth.login_admin_view"))
        flash(msg, "danger")
    return render_template("auth/registro_negocio.html")

@auth_bp.route("/logout")
def logout():
    auth.logout()
    return redirect("/")
