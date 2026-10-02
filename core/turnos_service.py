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
    t["estado"] = "pendiente" # Vuelve a pendiente por el cambio de horario
    upsert_turno(t)
    return True, f"Turno reprogramado exitosamente para el {nueva_fecha} a las {nueva_hora}."


def registrar_pago(turno_id: str, monto: float, metodo: str, negocio_id: str) -> tuple[bool, str]:
    t = get_turno_by_id(turno_id, negocio_id)
    if not t:
        return False, "Turno no encontrado."
    if monto <= 0:
        return False, "Monto inválido."
        
    pago = {
        "fecha": datetime.datetime.now().isoformat(),
        "monto": monto,
        "metodo": metodo
    }
    t.setdefault("pagos", []).append(pago)
    upsert_turno(t)
    return True, "Pago registrado correctamente."


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
                
    return {
        "pendientes": pendientes,
        "confirmados": confirmados,
        "cancelados": cancelados,
        "total": len(turnos),
        "ingresos": total_ingresos
    }
