import datetime
from core.persistence import (
    load_turnos, upsert_turno, get_turno_by_id, load_config, get_cliente_by_id
)
from core.disponibilidad import get_slots_disponibles_excluyendo


def get_agenda(fecha_str: str, negocio_id: str) -> list[dict]:
    turnos = load_turnos(negocio_id)
    dia = [t for t in turnos if t["fecha"] == fecha_str and t["estado"] != "cancelado"]
    for t in dia:
        c = get_cliente_by_id(t["cliente_id"], negocio_id)
        if c:
            t["cliente"] = c
    dia.sort(key=lambda x: x["hora_inicio"])
    return dia


def confirmar_turno(turno_id: str, negocio_id: str) -> tuple[bool, str]:
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if t["estado"] != "pendiente":
        return False, f"El turno no está pendiente (estado actual: {t['estado']})."
    
    t["estado"] = "confirmado"
    upsert_turno(t)
    return True, "Turno confirmado con éxito."


def cancelar_turno(turno_id: str, negocio_id: str) -> tuple[bool, str]:
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if t["estado"] == "cancelado":
        return False, "El turno ya estaba cancelado."
    
    t["estado"] = "cancelado"
    upsert_turno(t)
    return True, "Turno cancelado."


def reprogramar_turno(turno_id: str, nueva_fecha: str, nueva_hora: str, negocio_id: str) -> tuple[bool, str]:
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if t["estado"] == "cancelado":
        return False, "No se puede reprogramar un turno cancelado."

    slots_libres = get_slots_disponibles_excluyendo(nueva_fecha, t["servicio_id"], t["id"], negocio_id)
    if nueva_hora not in slots_libres:
        return False, "El horario seleccionado ya no está disponible o el negocio está cerrado."

    t["fecha"] = nueva_fecha
    t["hora_inicio"] = nueva_hora
    cfg = load_config(negocio_id)
    servicios = {s["id"]: s for s in cfg.get("servicios", [])}
    dur_min = int(servicios.get(t.get("servicio_id"), {}).get("duracion_min", cfg.get("intervalo_turno_min", 30)))
    try:
        from datetime import datetime as dt, timedelta
        h_ini_dt = dt.strptime(nueva_hora, "%H:%M")
        t["hora_fin"] = (h_ini_dt + timedelta(minutes=dur_min)).strftime("%H:%M")
    except Exception:
        pass
    t["estado"] = "pendiente" # Vuelve a pendiente por el cambio de horario
    upsert_turno(t)
    return True, f"Turno reprogramado exitosamente para el {nueva_fecha} a las {nueva_hora}."


def registrar_pago(turno_id: str, monto: float, metodo: str, negocio_id: str, detalle: str = "") -> tuple[bool, str]:
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if monto <= 0:
        return False, "Monto inválido."
        
    pago = {
        "fecha": datetime.datetime.now().isoformat(),
        "monto": monto,
        "metodo": metodo,
        "detalle": detalle
    }
    t.setdefault("pagos", []).append(pago)
    t["monto_abonado"] = sum(float(p.get("monto", 0.0)) for p in t.get("pagos", []))
    if t["monto_abonado"] >= float(t.get("precio_total", 0.0)):
        t["estado_pago"] = "completado"
    elif t["monto_abonado"] > 0:
        t["estado_pago"] = "senia_pagada"
    upsert_turno(t)
    return True, "Pago registrado correctamente."


def cobrar_turno(turno_id: str, metodo: str, monto: float, detalle: str, negocio_id: str) -> tuple[bool, str]:
    """
    Registra el cobro completo de un turno, asignando estado 'cobrado',
    registrando el pago con timestamp, monto y método (efectivo/transferencia).
    """
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if t.get("estado") == "cancelado":
        return False, "No se puede cobrar un turno cancelado."
    
    if monto < 0:
        return False, "El monto a cobrar no puede ser negativo."

    metodo_normalizado = "transferencia" if "transf" in metodo.lower() or "mp" in metodo.lower() or "mercado" in metodo.lower() else "efectivo"
    
    pago = {
        "fecha": datetime.datetime.now().isoformat(),
        "monto": float(monto),
        "metodo": metodo_normalizado,
        "detalle": detalle.strip() if detalle else ""
    }
    t.setdefault("pagos", []).append(pago)
    t["monto_abonado"] = sum(float(p.get("monto", 0.0)) for p in t.get("pagos", []))
    t["estado"] = "cobrado"
    t["estado_pago"] = "completado"
    t["cobrado_en"] = pago["fecha"]
    t["cobrado_metodo"] = metodo_normalizado
    t["cobrado_monto"] = float(monto)
    t["cobrado_detalle"] = detalle.strip() if detalle else ""
    
    upsert_turno(t)
    return True, "Turno cobrado y registrado en caja exitosamente."


def get_balance_caja_hoy(negocio_id: str) -> dict:
    """
    Calcula los totales de caja para la jornada activa (o desde el último reinicio/cierre).
    Muestra:
    - total_recaudado
    - total_efectivo
    - total_transferencia
    - pendientes_cobro (turnos confirmados/atendidos aún no cobrados)
    - movimientos: lista de transacciones del día
    """
    from core.persistence import load_turnos, load_cierres_caja, get_cliente_by_id
    hoy_str = datetime.date.today().isoformat()
    cierres = load_cierres_caja(negocio_id)
    ultimo_cierre_dt = None
    if cierres:
        # El primer elemento es el más reciente
        ultimo_cierre_dt = cierres[0].get("fecha_hora")

    turnos = load_turnos(negocio_id)
    
    total_efectivo = 0.0
    total_transferencia = 0.0
    movimientos = []
    pendientes_cobro = []

    for t in turnos:
        # Cargar cliente si no está
        if "cliente" not in t and t.get("cliente_id"):
            c = get_cliente_by_id(t["cliente_id"], negocio_id)
            if c:
                t["cliente"] = c

        # Pagos registrados hoy y posteriores al último cierre
        for p in t.get("pagos", []):
            p_fecha_iso = p.get("fecha", "")
            if not p_fecha_iso:
                continue
            p_dia = p_fecha_iso.split("T")[0]
            if p_dia != hoy_str:
                continue
            if ultimo_cierre_dt and p_fecha_iso <= ultimo_cierre_dt:
                continue

            monto = float(p.get("monto", 0.0))
            metodo = str(p.get("metodo", "efectivo")).lower()
            if "transf" in metodo or "mp" in metodo or "mercado" in metodo:
                total_transferencia += monto
                metodo_fmt = "transferencia"
            else:
                total_efectivo += monto
                metodo_fmt = "efectivo"

            hora = p_fecha_iso.split("T")[1][:5] if "T" in p_fecha_iso else ""
            movimientos.append({
                "turno_id": t.get("id"),
                "fecha_hora": p_fecha_iso,
                "hora": hora,
                "cliente_nombre": t.get("cliente", {}).get("nombre") or t.get("cliente_nombre") or "Cliente",
                "servicio_nombre": t.get("servicio_nombre", "Servicio"),
                "metodo": metodo_fmt,
                "monto": monto,
                "detalle": p.get("detalle", ""),
                "estado_turno": t.get("estado", "")
            })

        # Turnos de hoy pendientes de cobro
        if t.get("fecha") == hoy_str and t.get("estado") in ("confirmado", "pendiente", "atendido"):
            if t.get("estado") != "cobrado" and t.get("estado") != "cancelado":
                pendientes_cobro.append(t)

    # Ordenar movimientos del más reciente al más antiguo
    movimientos.sort(key=lambda x: x["fecha_hora"], reverse=True)
    total_recaudado = total_efectivo + total_transferencia

    return {
        "fecha": hoy_str,
        "total_recaudado": total_recaudado,
        "total_efectivo": total_efectivo,
        "total_transferencia": total_transferencia,
        "pendientes_cobro_count": len(pendientes_cobro),
        "pendientes_cobro": pendientes_cobro,
        "movimientos": movimientos,
        "ultimo_cierre": cierres[0] if cierres else None
    }


def cerrar_caja_diaria(negocio_id: str, usuario: str = "Admin") -> tuple[bool, str, dict]:
    """
    Genera un snapshot histórico del arqueo actual y reinicia los contadores activos.
    """
    from core.persistence import registrar_cierre_caja
    balance = get_balance_caja_hoy(negocio_id)
    
    ahora = datetime.datetime.now().isoformat()
    cierre_registro = {
        "id": f"cierre_{negocio_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "negocio_id": negocio_id,
        "fecha_hora": ahora,
        "fecha": datetime.date.today().isoformat(),
        "cerrado_por": usuario,
        "total_recaudado": balance["total_recaudado"],
        "total_efectivo": balance["total_efectivo"],
        "total_transferencia": balance["total_transferencia"],
        "cantidad_movimientos": len(balance["movimientos"])
    }
    registrar_cierre_caja(cierre_registro)
    return True, "Caja cerrada y reiniciada correctamente para una nueva jornada.", cierre_registro


def get_estadisticas(negocio_id: str) -> dict:
    turnos = load_turnos(negocio_id)
    pendientes = sum(1 for t in turnos if t["estado"] == "pendiente")
    confirmados = sum(1 for t in turnos if t["estado"] == "confirmado")
    cancelados = sum(1 for t in turnos if t["estado"] == "cancelado")
    
    total_ingresos = 0.0
    for t in turnos:
        if t["estado"] in ("confirmado", "pendiente"):
            for p in t.get("pagos", []):
                total_ingresos += p.get("monto", 0.0)
                
    por_dia: dict = {}
    por_servicio: dict = {}
    for t in turnos:
        if t.get("estado") == "cancelado":
            continue
        f = t.get("fecha") or ""
        if f:
            por_dia[f] = por_dia.get(f, 0) + 1
        s = t.get("servicio_nombre") or "Sin servicio"
        por_servicio[s] = por_servicio.get(s, 0) + 1
    por_dia = dict(sorted(por_dia.items())[-30:])

    return {
        "pendientes": pendientes,
        "confirmados": confirmados,
        "cancelados": cancelados,
        "total": len(turnos),
        "ingresos": total_ingresos,
        "por_dia": por_dia,
        "por_servicio": por_servicio,
    }
