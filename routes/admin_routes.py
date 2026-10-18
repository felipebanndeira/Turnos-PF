import uuid
from datetime import date
import datetime

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from core.auth import require_admin
from core.persistence import (
    load_turnos, get_turno_by_id, upsert_turno,
    load_config, save_config, load_clientes,
    get_cliente_by_id, upsert_cliente, delete_cliente, load_cierres_caja
)
from core.turnos_service import (
    get_agenda, confirmar_turno, cancelar_turno, reprogramar_turno,
    get_estadisticas, registrar_pago, cobrar_turno,
    get_balance_caja_hoy, cerrar_caja_diaria
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
    
    hoy_str = date.today().isoformat()
    filtro_vista = request.args.get("filtro", "").lower()
    filtro_estado = request.args.get("estado", "todos").lower()
    fecha_param = request.args.get("fecha")
    
    # Determinar vista por defecto
    if not filtro_vista:
        if fecha_param and fecha_param != hoy_str:
            filtro_vista = "fecha"
        else:
            filtro_vista = "hoy"
            
    fecha_actual = fecha_param if (filtro_vista == "fecha" and fecha_param) else hoy_str
    
    todos_turnos = load_turnos(nid)
    # Enriquecer turnos con datos de cliente
    for t in todos_turnos:
        if "cliente" not in t and t.get("cliente_id"):
            c = get_cliente_by_id(t["cliente_id"], nid)
            if c:
                t["cliente"] = c
                
    # 1. Filtrar por Vista (Hoy | Próximos | Todos | Por Fecha)
    if filtro_vista == "hoy":
        turnos_filtrados = [t for t in todos_turnos if t.get("fecha") == hoy_str]
        turnos_filtrados.sort(key=lambda x: x.get("hora_inicio", ""))
    elif filtro_vista == "proximos":
        turnos_filtrados = [t for t in todos_turnos if t.get("fecha", "") >= hoy_str and t.get("estado") != "cancelado"]
        turnos_filtrados.sort(key=lambda x: (x.get("fecha", ""), x.get("hora_inicio", "")))
    elif filtro_vista == "todos":
        turnos_filtrados = list(todos_turnos)
        turnos_filtrados.sort(key=lambda x: (x.get("fecha", ""), x.get("hora_inicio", "")), reverse=True)
    elif filtro_vista == "fecha":
        turnos_filtrados = [t for t in todos_turnos if t.get("fecha") == fecha_actual]
        turnos_filtrados.sort(key=lambda x: x.get("hora_inicio", ""))
    else:
        turnos_filtrados = [t for t in todos_turnos if t.get("fecha") == hoy_str]
        turnos_filtrados.sort(key=lambda x: x.get("hora_inicio", ""))
        filtro_vista = "hoy"

    # Conteo de estados sobre la vista actual (antes de filtrar por estado específico)
    total_vista = len(turnos_filtrados)
    conteo_estados = {
        "todos": total_vista,
        "confirmado": sum(1 for t in turnos_filtrados if t.get("estado") == "confirmado"),
        "pendiente": sum(1 for t in turnos_filtrados if t.get("estado") == "pendiente"),
        "cancelado": sum(1 for t in turnos_filtrados if t.get("estado") == "cancelado"),
        "cobrado": sum(1 for t in turnos_filtrados if t.get("estado") == "cobrado"),
    }

    # 2. Filtrar por Estado específico si fue solicitado
    if filtro_estado and filtro_estado != "todos":
        turnos_filtrados = [t for t in turnos_filtrados if t.get("estado") == filtro_estado]

    return render_template(
        "admin/agenda.html",
        config=cfg,
        turnos=turnos_filtrados,
        fecha_actual=fecha_actual,
        fecha=fecha_actual,
        filtro_vista=filtro_vista,
        filtro_estado=filtro_estado,
        conteo_estados=conteo_estados,
        hoy=hoy_str
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

@admin_bp.route("/turnos/<turno_id>/confirmar", methods=["POST"])
@require_admin
def confirmar(turno_id):
    nid = session["negocio_id"]
    t = get_turno_by_id(turno_id, nid)
    if not t:
        flash("Turno no encontrado.", "danger")
        return redirect(url_for("admin.agenda"))
    
    # Confirmar turno
    ok, msg = confirmar_turno(turno_id, nid)
    
    # Si tiene seña requerida y no fue abonada aún, marcar la seña como recibida
    if ok and t.get("monto_senia", 0) > 0 and t.get("monto_abonado", 0) == 0:
        registrar_pago(turno_id, float(t["monto_senia"]), "transferencia", nid, "Seña verificada y aprobada por el dueño")

    if ok:
        flash("¡Turno y comprobante de seña aprobados con éxito!", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.detalle_turno", turno_id=turno_id))

@admin_bp.route("/turnos/<turno_id>/cancelar", methods=["POST"])
@require_admin
def cancelar(turno_id):
    nid = session["negocio_id"]
    ok, msg = cancelar_turno(turno_id, nid)
    if ok:
        flash("Turno cancelado exitosamente.", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.agenda"))

@admin_bp.route("/turnos/<turno_id>/estado", methods=["POST"])
@require_admin
def cambiar_estado_turno(turno_id):
    nid = session["negocio_id"]
    accion = request.form.get("accion")
    
    if accion == "confirmar":
        t = get_turno_by_id(turno_id, nid)
        ok, msg = confirmar_turno(turno_id, nid)
        if ok and t and t.get("monto_senia", 0) > 0 and t.get("monto_abonado", 0) == 0:
            registrar_pago(turno_id, float(t["monto_senia"]), "transferencia", nid, "Seña verificada")
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
    
    next_url = request.form.get("next") or request.referrer or url_for("admin.detalle_turno", turno_id=turno_id)
    return redirect(next_url)

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

@admin_bp.route("/horarios")
@require_admin
def admin_horarios():
    nid = session["negocio_id"]
    fecha = request.args.get("fecha")
    turno_id = request.args.get("turno_id")
    servicio_id = request.args.get("servicio_id")
    
    if not fecha:
        return jsonify({"slots": []})
        
    if turno_id:
        t = get_turno_by_id(turno_id, nid)
        if t:
            s_id = servicio_id or t.get("servicio_id")
            slots = get_slots_disponibles_excluyendo(fecha, s_id, turno_id, nid)
            return jsonify({"slots": slots})
            
    if servicio_id:
        from core.disponibilidad import get_slots_disponibles
        slots = get_slots_disponibles(fecha, servicio_id, nid)
        return jsonify({"slots": slots})
        
    return jsonify({"slots": []})

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
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        activo = request.form.get("activo") == "1"
        
        if nombre:
            cliente["nombre"] = nombre
            cliente["email"] = email
            cliente["telefono"] = telefono
            cliente["activo"] = activo
            upsert_cliente(cliente)
            flash("Cliente actualizado correctamente.", "success")
            return redirect(url_for("admin.clientes"))
        else:
            flash("El nombre es obligatorio.", "warning")
            
    return render_template("admin/editar_cliente.html", config=cfg, cliente=cliente)

@admin_bp.route("/clientes/<cliente_id>/eliminar", methods=["POST"])
@require_admin
def eliminar_cliente(cliente_id):
    nid = session["negocio_id"]
    ok = delete_cliente(cliente_id, nid)
    if ok:
        flash("Cliente eliminado correctamente.", "success")
    else:
        flash("No se pudo eliminar el cliente o no fue encontrado.", "danger")
    return redirect(url_for("admin.clientes"))

@admin_bp.route("/configuracion", methods=["GET", "POST"])
@require_admin
def configuracion():
    nid = session["negocio_id"]
    config = load_config(nid)

    if request.method == "POST":
        # Safe int/float helpers to prevent ValueError on empty strings
        def safe_int(val, default):
            try:
                s = str(val).strip()
                return int(s) if s else default
            except Exception:
                return default

        def safe_float(val, default):
            try:
                s = str(val).strip()
                return float(s) if s else default
            except Exception:
                return default

        config["nombre"]              = request.form.get("nombre", "").strip()
        config["rubro"]               = request.form.get("rubro", "").strip()
        config["descripcion"]         = request.form.get("descripcion", "").strip()
        config["intervalo_turno_min"] = safe_int(request.form.get("intervalo_turno_min"), 30)
        config["horas_cancelacion"]   = safe_int(request.form.get("horas_cancelacion"), 24)
        
        import base64

        logo_file = request.files.get("logo_file")
        if logo_file and logo_file.filename:
            try:
                file_bytes = logo_file.read()
                if file_bytes:
                    mime = logo_file.mimetype or "image/png"
                    b64_str = base64.b64encode(file_bytes).decode('utf-8')
                    config["logo_url"] = f"data:{mime};base64,{b64_str}"
            except Exception as e:
                print(f"Error procesando logo: {e}")
        elif "eliminar_logo" in request.form:
            config["logo_url"] = ""
        
        config["requiere_senia"]   = request.form.get("requiere_senia") == "1"
        config["porcentaje_senia"] = safe_float(request.form.get("porcentaje_senia"), 0.0)
        config["titular_pago"]     = request.form.get("titular_pago", "").strip()
        config["datos_pago"]       = request.form.get("datos_pago", "").strip()
        config["whatsapp_pago"]    = request.form.get("whatsapp_pago", "").strip()
        
        # Helper para parsear precios argentinos (ej: 10.000 o 10000 o 10,50)
        def parse_precio(raw):
            if not raw: return 0.0
            s = str(raw).strip().replace('$', '').replace(' ', '')
            if '.' in s and ',' in s:
                s = s.replace('.', '').replace(',', '.')
            elif '.' in s:
                parts = s.split('.')
                if all(len(p) == 3 for p in parts[1:]):
                    s = s.replace('.', '')
            elif ',' in s:
                s = s.replace(',', '.')
            try:
                return float(s)
            except Exception:
                return 0.0

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
                    "duracion_min": int(s_durs[i]) if str(s_durs[i]).isdigit() else 30,
                    "precio": parse_precio(s_precios[i])
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

        try:
            save_config(nid, config)
            flash("Configuración guardada correctamente.", "success")
        except Exception as e:
            print(f"Error al guardar configuracion: {e}")
            flash(f"Error al guardar en base de datos: {e}", "danger")
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


# ─── Módulo de Caja y Arqueo Diario ──────────────────────────────────────────

@admin_bp.route("/turnos/<turno_id>/cobrar", methods=["POST"])
@require_admin
def cobrar_turno_view(turno_id):
    nid = session["negocio_id"]
    metodo = request.form.get("metodo", "efectivo")
    monto_raw = request.form.get("monto", "0")
    detalle = request.form.get("detalle", "").strip()

    try:
        monto = float(str(monto_raw).replace("$", "").replace(" ", "").replace(".", "").replace(",", "."))
    except Exception:
        monto = 0.0

    ok, msg = cobrar_turno(turno_id, metodo, monto, detalle, nid)
    if ok:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    # Si la petición vino con origen específico o desde la agenda
    redirect_to = request.form.get("next") or request.referrer or url_for("admin.agenda")
    return redirect(redirect_to)


@admin_bp.route("/caja")
@require_admin
def caja_view():
    nid = session["negocio_id"]
    cfg = load_config(nid)
    balance = get_balance_caja_hoy(nid)
    historial_cierres = load_cierres_caja(nid)
    return render_template(
        "admin/caja.html",
        config=cfg,
        balance=balance,
        cierres=historial_cierres[:10],
        hoy=date.today().isoformat()
    )


@admin_bp.route("/caja/reiniciar", methods=["POST"])
@require_admin
def reiniciar_caja_view():
    nid = session["negocio_id"]
    usuario = session.get("nombre") or "Administrador"
    ok, msg, cierre = cerrar_caja_diaria(nid, usuario)
    if ok:
        flash(f"Arqueo cerrado con éxito. Total archivado: ${cierre['total_recaudado']:,.0f}. Caja reiniciada.", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.caja_view"))
