import uuid
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from core.auth import get_current_cliente
from core.persistence import load_config, upsert_turno, load_turnos, get_negocio_by_id
from core.disponibilidad import get_slots_disponibles
from core.turnos_service import cancelar_turno

cliente_bp = Blueprint("cliente", __name__, url_prefix="/b/<url_id>")


@cliente_bp.before_request
def check_negocio_exists():
    url_id = request.view_args.get('url_id')
    if url_id:
        negocio = get_negocio_by_id(url_id)
        if not negocio:
            return "Negocio no encontrado", 404


@cliente_bp.route("/")
def dashboard(url_id):
    c = get_current_cliente()
    if not c or session.get("negocio_id") != url_id:
        return redirect(url_for("cliente.solicitar_turno", url_id=url_id))
        
    cfg = load_config(url_id)
    return render_template("cliente/dashboard.html", config=cfg, cliente=c, url_id=url_id)


@cliente_bp.route("/solicitar", methods=["GET", "POST"])
def solicitar_turno(url_id):
    cfg = load_config(url_id)
    c = get_current_cliente()
    # Check if the session is from a different business, if so, clear client info
    if c and session.get("negocio_id") != url_id:
        c = None

    if request.method == "POST":
        servicio_id = request.form.get("servicio_id")
        fecha       = request.form.get("fecha")
        hora        = request.form.get("hora_inicio") or request.form.get("hora")

        if not all([servicio_id, fecha, hora]):
            flash("Faltan datos para confirmar el turno.", "danger")
            return redirect(url_for("cliente.solicitar_turno", url_id=url_id))
            
        # Si no hay cliente en sesión, capturamos Nombre y Teléfono (igual que Alejo Barber)
        if not c:
            nombre = request.form.get("cliente_nombre", "").strip()
            telefono = request.form.get("cliente_telefono", "").strip()
            
            if not nombre or not telefono:
                flash("Tu Nombre y Teléfono son obligatorios para reservar.", "warning")
                return redirect(url_for("cliente.solicitar_turno", url_id=url_id))
                
            from core.persistence import get_cliente_by_telefono, upsert_cliente
            # Buscar por teléfono si ya existe en este negocio
            c = get_cliente_by_telefono(telefono, url_id)
            if not c:
                import uuid
                c = {
                    "id": str(uuid.uuid4()),
                    "negocio_id": url_id,
                    "nombre": nombre,
                    "telefono": telefono,
                    "email": request.form.get("cliente_email", "").strip()
                }
                upsert_cliente(c)
            else:
                # Si cambió el nombre, actualizarlo
                if c.get("nombre") != nombre:
                    c["nombre"] = nombre
                    upsert_cliente(c)
            
            session["rol"] = "cliente"
            session["cliente_id"] = c["id"]
            session["negocio_id"] = url_id

        servicios = {s["id"]: s for s in cfg.get("servicios", [])}
        srv = servicios.get(servicio_id)
        if not srv:
            flash("Servicio inválido.", "danger")
            return redirect(url_for("cliente.solicitar_turno", url_id=url_id))

        import uuid
        from datetime import datetime as dt, timedelta
        from core.persistence import upsert_turno

        duracion_min = int(srv.get("duracion_min", cfg.get("intervalo_turno_min", 30)))
        try:
            h_ini_dt = dt.strptime(hora, "%H:%M")
            hora_fin = (h_ini_dt + timedelta(minutes=duracion_min)).strftime("%H:%M")
        except Exception:
            hora_fin = hora

        precio_total = float(srv.get("precio", 0.0))
        requiere_senia = bool(cfg.get("requiere_senia", False))
        pct_senia = float(cfg.get("porcentaje_senia", 0.0) or 0.0)
        monto_senia = round((precio_total * pct_senia) / 100.0, 2) if (requiere_senia and pct_senia > 0) else 0.0

        # Procesar archivo comprobante si fue adjuntado
        import base64
        comprobante_b64 = ""
        comprobante_file = request.files.get("comprobante_file")
        if comprobante_file and comprobante_file.filename:
            try:
                f_bytes = comprobante_file.read()
                if f_bytes:
                    mime = comprobante_file.mimetype or "image/png"
                    comprobante_b64 = f"data:{mime};base64,{base64.b64encode(f_bytes).decode('utf-8')}"
            except Exception as e:
                print(f"Error procesando comprobante: {e}")

        nuevo_turno = {
            "id": str(uuid.uuid4()),
            "negocio_id": url_id,
            "cliente_id": c["id"],
            "cliente_nombre": c.get("nombre", ""),
            "servicio_id": srv["id"],
            "servicio_nombre": srv["nombre"],
            "fecha": fecha,
            "hora_inicio": hora,
            "hora_fin": hora_fin,
            "duracion_min": duracion_min,
            "precio": precio_total,
            "precio_total": precio_total,
            "monto_senia": monto_senia,
            "monto_abonado": 0.0,
            "estado_pago": "pendiente",
            "comprobante_url": comprobante_b64,
            "estado": "pendiente",
            "creado_el": date.today().isoformat(),
            "pagos": []
        }
        upsert_turno(nuevo_turno)
        flash("Turno solicitado con éxito.", "success")
        return redirect(url_for("cliente.estado_turno", url_id=url_id, turno_id=nuevo_turno["id"]))

    hoy_str = date.today().isoformat()
    return render_template(
        "cliente/solicitar_turno.html", 
        config=cfg, 
        servicios=cfg.get("servicios", []),
        cliente=c, 
        hoy=hoy_str, 
        url_id=url_id
    )


@cliente_bp.route("/horarios")
def horarios_disponibles(url_id):
    fecha = request.args.get("fecha")
    servicio_id = request.args.get("servicio_id")
    if not fecha or not servicio_id:
        return jsonify([])
    from core.disponibilidad import get_slots_disponibles
    slots = get_slots_disponibles(fecha, servicio_id, url_id)
    return jsonify({"slots": slots})


@cliente_bp.route("/mis-turnos", methods=["GET", "POST"])
def mis_turnos(url_id):
    cfg = load_config(url_id)
    turnos_encontrados = None
    telefono_buscado = ""
    cliente_encontrado = None

    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        telefono_buscado = telefono
        if telefono:
            from core.persistence import get_cliente_by_telefono, load_turnos
            c = get_cliente_by_telefono(telefono, url_id)
            if c:
                cliente_encontrado = c
                todos = load_turnos(url_id)
                turnos_encontrados = [t for t in todos if t["cliente_id"] == c["id"]]
                turnos_encontrados.sort(key=lambda x: (x["fecha"], x["hora_inicio"]), reverse=True)
                
                # Calcular cancelaciones
                from datetime import datetime
                horas_minimas = int(cfg.get("horas_cancelacion", 24))
                for t in turnos_encontrados:
                    try:
                        f_h = datetime.strptime(f"{t['fecha']} {t['hora_inicio']}", "%Y-%m-%d %H:%M")
                        horas_restantes = (f_h - datetime.now()).total_seconds() / 3600.0
                        t["puede_cancelar"] = (horas_restantes >= horas_minimas)
                    except:
                        t["puede_cancelar"] = False
            else:
                flash("No se encontraron turnos con ese número de teléfono.", "warning")
        else:
            flash("Ingresá un número de teléfono.", "warning")

    horas_minimas = int(cfg.get("horas_cancelacion", 24))
    
    return render_template(
        "cliente/mis_turnos.html", 
        config=cfg, 
        url_id=url_id,
        turnos=turnos_encontrados,
        telefono_buscado=telefono_buscado,
        cliente=cliente_encontrado,
        horas_minimas=horas_minimas
    )


@cliente_bp.route("/turno/<turno_id>")
def estado_turno(url_id, turno_id):
    cfg = load_config(url_id)
    from core.persistence import get_turno_by_id, get_cliente_by_id
    t = get_turno_by_id(turno_id, url_id)
    
    if not t:
        return "Turno no encontrado", 404
        
    c = get_cliente_by_id(t["cliente_id"], url_id)
    
    # Calcular si se puede cancelar
    from core.disponibilidad import ahora_argentina
    
    try:
        fecha_hora_turno = datetime.strptime(f"{t['fecha']} {t['hora_inicio']}", "%Y-%m-%d %H:%M")
        hoy_naive = ahora_argentina().replace(tzinfo=None)
        horas_restantes = (fecha_hora_turno - hoy_naive).total_seconds() / 3600.0
    except Exception:
        horas_restantes = 0
        
    horas_minimas = int(cfg.get("horas_cancelacion", 24))
    puede_cancelar = horas_restantes >= horas_minimas
    
    return render_template(
        "cliente/estado_turno.html", 
        config=cfg, 
        turno=t, 
        cliente=c, 
        url_id=url_id,
        puede_cancelar=puede_cancelar,
        horas_minimas=horas_minimas
    )


@cliente_bp.route("/turno/<turno_id>/cancelar", methods=["POST"])
def cancelar(url_id, turno_id):
    from core.turnos_service import cancelar_turno
    ok, msg = cancelar_turno(turno_id, url_id)
    if ok:
        flash("Turno cancelado.", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("cliente.estado_turno", url_id=url_id, turno_id=turno_id))


@cliente_bp.route("/turno/<turno_id>/comprobante", methods=["POST"])
def subir_comprobante(url_id, turno_id):
    from core.persistence import get_turno_by_id, upsert_turno
    import base64
    t = get_turno_by_id(turno_id, url_id)
    if not t:
        flash("Turno no encontrado.", "danger")
        return redirect(url_for("cliente.solicitar_turno", url_id=url_id))
        
    comp_file = request.files.get("comprobante_file")
    if comp_file and comp_file.filename:
        try:
            f_bytes = comp_file.read()
            if f_bytes:
                mime = comp_file.mimetype or "image/png"
                t["comprobante_url"] = f"data:{mime};base64,{base64.b64encode(f_bytes).decode('utf-8')}"
                upsert_turno(t)
                flash("¡Comprobante adjuntado con éxito! El establecimiento lo verificará a la brevedad.", "success")
        except Exception as e:
            flash(f"Error al subir comprobante: {e}", "danger")
    else:
        flash("Por favor seleccioná una imagen para subir.", "warning")
        
    return redirect(url_for("cliente.estado_turno", url_id=url_id, turno_id=turno_id))
