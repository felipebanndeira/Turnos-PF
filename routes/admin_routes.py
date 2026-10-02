import uuid
from datetime import date
import datetime

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from core.auth import require_admin
from core.persistence import (
    load_turnos, get_turno_by_id, upsert_turno,
    load_config, save_config, load_clientes,
    get_cliente_by_id, upsert_cliente
)
from core.turnos_service import (
    get_agenda, confirmar_turno, cancelar_turno, reprogramar_turno,
    get_estadisticas, registrar_pago
)
from core.disponibilidad import get_slots_disponibles_excluyendo

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/")
@require_admin
def dashboard():
    nid = session["negocio_id"]
    cfg = load_config(nid)
    turnos = load_turnos(nid)
    
    hoy_str = date.today().isoformat()
    agenda_hoy = [t for t in turnos if t["fecha"] == hoy_str and t["estado"] != "cancelado"]
    agenda_hoy.sort(key=lambda x: x["hora_inicio"])
    
    stats = get_estadisticas(nid)
    clientes = load_clientes(nid)
    
    return render_template(
        "admin/dashboard.html",
        config=cfg,
        agenda_hoy=agenda_hoy,
        stats=stats,
        total_clientes=len(clientes),
        hoy=hoy_str
    )

@admin_bp.route("/agenda")
@require_admin
def agenda():
    nid = session["negocio_id"]
    cfg = load_config(nid)
    
    fecha_str = request.args.get("fecha")
    if not fecha_str:
        fecha_str = date.today().isoformat()
        
    turnos_dia = get_agenda(fecha_str, nid)
    return render_template(
        "admin/agenda.html",
        config=cfg,
        turnos=turnos_dia,
        fecha_actual=fecha_str
    )

@admin_bp.route("/turnos/<turno_id>")
@require_admin
def detalle_turno(turno_id):
    nid = session["negocio_id"]
    cfg = load_config(nid)
    t = get_turno_by_id(turno_id, nid)
    if not t:
        flash("Turno no encontrado.", "danger")
        return redirect(url_for("admin.agenda"))
    c = get_cliente_by_id(t["cliente_id"], nid)
    return render_template("admin/gestionar_turno.html", config=cfg, turno=t, cliente=c)

@admin_bp.route("/turnos/<turno_id>/estado", methods=["POST"])
@require_admin
def cambiar_estado_turno(turno_id):
    nid = session["negocio_id"]
    accion = request.form.get("accion")
    
    if accion == "confirmar":
        ok, msg = confirmar_turno(turno_id, nid)
    elif accion == "cancelar":
        ok, msg = cancelar_turno(turno_id, nid)
    elif accion == "registrar_pago":
        monto = float(request.form.get("monto_pago", 0))
        ok, msg = registrar_pago(turno_id, monto, "manual_admin", nid)
    else:
        ok, msg = False, "Acción inválida."
        
    if ok:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.detalle_turno", turno_id=turno_id))

@admin_bp.route("/turnos/<turno_id>/reprogramar", methods=["POST"])
@require_admin
def reprogramar(turno_id):
    nid = session["negocio_id"]
    t = get_turno_by_id(turno_id, nid)
    if not t:
        flash("Turno no existe.", "danger")
        return redirect(url_for("admin.agenda"))
        
    n_fecha = request.form.get("nueva_fecha")
    n_hora  = request.form.get("nueva_hora")
    if not n_fecha or not n_hora:
        flash("Faltan datos de fecha/hora.", "warning")
        return redirect(url_for("admin.detalle_turno", turno_id=turno_id))
        
    ok, msg = reprogramar_turno(turno_id, n_fecha, n_hora, nid)
    if ok:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.detalle_turno", turno_id=turno_id))

@admin_bp.route("/api/slots_reprogramar")
@require_admin
def api_slots_reprogramar():
    nid = session["negocio_id"]
    f = request.args.get("fecha")
    sid = request.args.get("servicio_id")
    tid = request.args.get("excluir_turno_id")
    if not (f and sid and tid):
        return jsonify([])
    slots = get_slots_disponibles_excluyendo(f, sid, tid, nid)
    return jsonify(slots)

@admin_bp.route("/clientes")
@require_admin
def clientes():
    nid = session["negocio_id"]
    cfg = load_config(nid)
    lista = load_clientes(nid)
    return render_template("admin/clientes.html", config=cfg, clientes=lista)

@admin_bp.route("/clientes/<cliente_id>/editar", methods=["GET", "POST"])
@require_admin
def editar_cliente(cliente_id):
    nid = session["negocio_id"]
    cfg = load_config(nid)
    cliente = get_cliente_by_id(cliente_id, nid)
    if not cliente:
        flash("Cliente no encontrado.", "danger")
        return redirect(url_for("admin.clientes"))
        
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        
        if nombre:
            cliente["nombre"] = nombre
            cliente["telefono"] = telefono
            upsert_cliente(cliente)
            flash("Cliente actualizado correctamente.", "success")
            return redirect(url_for("admin.clientes"))
        else:
            flash("El nombre es obligatorio.", "warning")
            
    return render_template("admin/editar_cliente.html", config=cfg, cliente=cliente)

@admin_bp.route("/configuracion", methods=["GET", "POST"])
@require_admin
def configuracion():
    nid = session["negocio_id"]
    config = load_config(nid)

    if request.method == "POST":
        config["nombre"]      = request.form.get("nombre", "").strip()
        config["rubro"]       = request.form.get("rubro", "").strip()
        config["descripcion"] = request.form.get("descripcion", "").strip()
        config["intervalo_turno_min"] = int(request.form.get("intervalo_turno_min", 30))
        config["horas_cancelacion"] = int(request.form.get("horas_cancelacion", 24))
        
        import os
        from werkzeug.utils import secure_filename
        logo_file = request.files.get("logo_file")
        if logo_file and logo_file.filename:
            os.makedirs("static", exist_ok=True)
            filename = secure_filename(logo_file.filename)
            filepath = os.path.join("static", filename)
            logo_file.save(filepath)
            config["logo_url"] = f"/static/{filename}"
        elif "eliminar_logo" in request.form:
            config["logo_url"] = ""
        
        config["requiere_senia"]   = request.form.get("requiere_senia") == "1"
        config["porcentaje_senia"] = float(request.form.get("porcentaje_senia", 0))
        config["titular_pago"]     = request.form.get("titular_pago", "").strip()
        config["whatsapp_pago"]    = request.form.get("whatsapp_pago", "").strip()
        
        # Servicios
        s_nombres = request.form.getlist("servicio_nombre[]")
        s_durs = request.form.getlist("servicio_duracion[]")
        s_precios = request.form.getlist("servicio_precio[]")
        servicios = []
        for i in range(len(s_nombres)):
            n = s_nombres[i].strip()
            if n:
                servicios.append({
                    "id": f"s{i+1}",
                    "nombre": n,
                    "duracion_min": int(s_durs[i]) if s_durs[i].isdigit() else 30,
                    "precio": float(s_precios[i]) if s_precios[i] else 0.0
                })
        config["servicios"] = servicios

        # Horarios
        h_dias = request.form.getlist("horario_dia[]")
        h_desdes = request.form.getlist("horario_desde[]")
        h_hastas = request.form.getlist("horario_hasta[]")
        horarios = []
        for i in range(len(h_dias)):
            d = h_dias[i].strip()
            if d:
                horarios.append({
                    "dia": d,
                    "desde": h_desdes[i].strip(),
                    "hasta": h_hastas[i].strip()
                })
        config["horarios_atencion"] = horarios

        # Bloqueos por Fecha
        b_fechas = request.form.getlist("bloqueo_fecha[]")
        b_desdes = request.form.getlist("bloqueo_desde[]")
        b_hastas = request.form.getlist("bloqueo_hasta[]")
        bloqueos = []
        for i in range(len(b_fechas)):
            f = b_fechas[i].strip()
            if f:
                bloqueos.append({
                    "fecha": f,
                    "hora_desde": b_desdes[i].strip(),
                    "hora_hasta": b_hastas[i].strip()
                })
        config["bloqueos"] = bloqueos

        # Bloqueos Recurrentes
        br_dias = request.form.getlist("br_dia[]")
        br_desdes = request.form.getlist("br_desde[]")
        br_hastas = request.form.getlist("br_hasta[]")
        b_recurrentes = []
        for i in range(len(br_dias)):
            dia = br_dias[i].strip()
            if dia:
                b_recurrentes.append({
                    "dia": dia,
                    "hora_desde": br_desdes[i].strip(),
                    "hora_hasta": br_hastas[i].strip()
                })
        config["bloqueos_recurrentes"] = b_recurrentes

        save_config(nid, config)
        flash("Configuración guardada correctamente.", "success")
        return redirect(url_for("admin.configuracion"))

    dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return render_template("admin/configuracion.html", config=config, dias_semana=dias_semana)

@admin_bp.route("/reportes")
@require_admin
def reportes():
    nid = session["negocio_id"]
    cfg = load_config(nid)
    stats = get_estadisticas(nid)
    return render_template("admin/reportes.html", config=cfg, stats=stats)
