"""
core/disponibilidad.py
======================
Lógica de cálculo de horarios disponibles.
Dado un servicio y una fecha, retorna la lista de slots libres
tomando en cuenta:
  - Horarios de atención configurados para ese día de semana.
  - Turnos ya ocupados (estado pendiente o confirmado).
  - Duración del servicio.
  - Bloqueos de agenda (Excepciones).
  - Horarios pasados si la fecha solicitada es hoy.
"""
from datetime import datetime, timedelta, date as date_type
from core.persistence import load_config, load_turnos

# Mapeo español → número de semana (weekday())
DIA_A_NUM = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5,
    "domingo": 6,
}


def _parse_time(t: str) -> datetime:
    """Convierte 'HH:MM' a datetime (fecha base 2000-01-01)."""
    return datetime.strptime(t, "%H:%M")


def _slots_del_dia(desde: str, hasta: str, intervalo_min: int) -> list[str]:
    """Genera todos los slots HH:MM dentro de [desde, hasta)."""
    inicio = _parse_time(desde)
    fin    = _parse_time(hasta)
    delta  = timedelta(minutes=intervalo_min)
    slots  = []
    current = inicio
    while current < fin:
        slots.append(current.strftime("%H:%M"))
        current += delta
    return slots


def get_slots_disponibles(fecha_str: str, servicio_id: str, negocio_id: str) -> list[str]:
    """
    Retorna lista de horarios ('HH:MM') disponibles para la fecha y servicio dados.
    """
    config    = load_config(negocio_id)
    servicios = {s["id"]: s for s in config.get("servicios", [])}
    servicio  = servicios.get(servicio_id)
    if not servicio:
        return []

    duracion_min = int(servicio.get("duracion_min", config.get("intervalo_turno_min", 30)))
    intervalo    = int(config.get("intervalo_turno_min", 30))

    try:
        fecha = date_type.fromisoformat(fecha_str)
    except ValueError:
        return []
    dia_num = fecha.weekday()

    # Horario de atención para ese día
    horario_dia = None
    for h in config.get("horarios_atencion", []):
        if DIA_A_NUM.get(h["dia"].lower()) == dia_num:
            horario_dia = h
            break

    if not horario_dia:
        return []

    todos_slots  = _slots_del_dia(horario_dia["desde"], horario_dia["hasta"], intervalo)
    cierre       = _parse_time(horario_dia["hasta"])
    
    # 1. Filtramos slots que por duración se pasan del cierre
    slots_validos = []
    for slot in todos_slots:
        slot_dt = _parse_time(slot)
        if slot_dt + timedelta(minutes=duracion_min) <= cierre:
            slots_validos.append(slot)
            
    # 2. Prevenir reservar turnos pasados (si la fecha es hoy)
    hoy = datetime.now()
    if fecha_str == hoy.strftime("%Y-%m-%d"):
        hora_actual = hoy.strftime("%H:%M")
        slots_validos = [s for s in slots_validos if s > hora_actual]

    # 3. Filtrar Excepciones / Bloqueos Manuales y Recurrentes
    dias_inv = {v: k for k, v in DIA_A_NUM.items() if k not in ["miércoles", "sábado"]}
    dia_nombre = dias_inv.get(dia_num, "")

    bloqueos_rec = config.get("bloqueos_recurrentes", [])
    bloqueos_rec_hoy = [b for b in bloqueos_rec if b.get("dia", "").lower() == dia_nombre]
    
    for b in bloqueos_rec_hoy:
        b_desde = b.get("hora_desde", "")
        b_hasta = b.get("hora_hasta", "")
        if b_desde and b_hasta:
            b_inicio_dt = _parse_time(b_desde)
            b_fin_dt    = _parse_time(b_hasta)
            slots_no_bloqueados = []
            for slot in slots_validos:
                s_ini = _parse_time(slot)
                s_fin = s_ini + timedelta(minutes=duracion_min)
                if not (s_ini < b_fin_dt and s_fin > b_inicio_dt):
                    slots_no_bloqueados.append(slot)
            slots_validos = slots_no_bloqueados

    # Bloqueos específicos por fecha
    bloqueos = config.get("bloqueos", [])
    bloqueos_del_dia = [b for b in bloqueos if b.get("fecha") == fecha_str]
    
    for b in bloqueos_del_dia:
        b_desde = b.get("hora_desde", "")
        b_hasta = b.get("hora_hasta", "")
        if not b_desde and not b_hasta:
            return []
            
        b_inicio_dt = _parse_time(b_desde)
        b_fin_dt    = _parse_time(b_hasta)
        
        slots_no_bloqueados = []
        for slot in slots_validos:
            s_ini = _parse_time(slot)
            s_fin = s_ini + timedelta(minutes=duracion_min)
            if not (s_ini < b_fin_dt and s_fin > b_inicio_dt):
                slots_no_bloqueados.append(slot)
        slots_validos = slots_no_bloqueados

    # 4. Filtrar los turnos ya ocupados (pendientes o confirmados)
    turnos_ocupados = [
        t for t in load_turnos(negocio_id)
        if t["fecha"] == fecha_str and t["estado"] in ("pendiente", "confirmado")
    ]
    ocupados_bloques = [
        (_parse_time(t["hora_inicio"]), _parse_time(t["hora_fin"]))
        for t in turnos_ocupados
    ]

    disponibles = []
    for slot in slots_validos:
        s_ini = _parse_time(slot)
        s_fin = s_ini + timedelta(minutes=duracion_min)
        solapado = any(s_ini < tf and s_fin > ti for ti, tf in ocupados_bloques)
        if not solapado:
            disponibles.append(slot)

    return disponibles


def get_slots_disponibles_excluyendo(fecha_str: str, servicio_id: str, excluir_turno_id: str, negocio_id: str) -> list[str]:
    """
    Igual que get_slots_disponibles pero excluye un turno específico (usado al Reprogramar).
    """
    config    = load_config(negocio_id)
    servicios = {s["id"]: s for s in config.get("servicios", [])}
    servicio  = servicios.get(servicio_id)
    if not servicio:
        return []

    duracion_min = int(servicio.get("duracion_min", config.get("intervalo_turno_min", 30)))
    intervalo    = int(config.get("intervalo_turno_min", 30))

    try:
        fecha = date_type.fromisoformat(fecha_str)
    except ValueError:
        return []
    dia_num = fecha.weekday()

    horario_dia = None
    for h in config.get("horarios_atencion", []):
        if DIA_A_NUM.get(h["dia"].lower()) == dia_num:
            horario_dia = h
            break
    if not horario_dia:
        return []

    todos_slots  = _slots_del_dia(horario_dia["desde"], horario_dia["hasta"], intervalo)
    cierre       = _parse_time(horario_dia["hasta"])
    
    slots_validos = []
    for slot in todos_slots:
        slot_dt = _parse_time(slot)
        if slot_dt + timedelta(minutes=duracion_min) <= cierre:
            slots_validos.append(slot)
            
    hoy = datetime.now()
    if fecha_str == hoy.strftime("%Y-%m-%d"):
        hora_actual = hoy.strftime("%H:%M")
        slots_validos = [s for s in slots_validos if s > hora_actual]

    # Bloqueos Recurrentes
    dias_inv = {v: k for k, v in DIA_A_NUM.items() if k not in ["miércoles", "sábado"]}
    dia_nombre = dias_inv.get(dia_num, "")

    bloqueos_rec = config.get("bloqueos_recurrentes", [])
    bloqueos_rec_hoy = [b for b in bloqueos_rec if b.get("dia", "").lower() == dia_nombre]
    for b in bloqueos_rec_hoy:
        b_desde = b.get("hora_desde", "")
        b_hasta = b.get("hora_hasta", "")
        if b_desde and b_hasta:
            b_inicio_dt = _parse_time(b_desde)
            b_fin_dt    = _parse_time(b_hasta)
            slots_no_bloqueados = []
            for slot in slots_validos:
                s_ini = _parse_time(slot)
                s_fin = s_ini + timedelta(minutes=duracion_min)
                if not (s_ini < b_fin_dt and s_fin > b_inicio_dt):
                    slots_no_bloqueados.append(slot)
            slots_validos = slots_no_bloqueados

    # Bloqueos manuales
    bloqueos = config.get("bloqueos", [])
    bloqueos_del_dia = [b for b in bloqueos if b.get("fecha") == fecha_str]
    for b in bloqueos_del_dia:
        b_desde = b.get("hora_desde", "")
        b_hasta = b.get("hora_hasta", "")
        if not b_desde and not b_hasta:
            return []
        b_inicio_dt = _parse_time(b_desde)
        b_fin_dt    = _parse_time(b_hasta)
        slots_no_bloqueados = []
        for slot in slots_validos:
            s_ini = _parse_time(slot)
            s_fin = s_ini + timedelta(minutes=duracion_min)
            if not (s_ini < b_fin_dt and s_fin > b_inicio_dt):
                slots_no_bloqueados.append(slot)
        slots_validos = slots_no_bloqueados

    turnos_ocupados = [
        t for t in load_turnos(negocio_id)
        if t["fecha"] == fecha_str
        and t["estado"] in ("pendiente", "confirmado")
        and t["id"] != excluir_turno_id
    ]

    ocupados_bloques = [
        (_parse_time(t["hora_inicio"]), _parse_time(t["hora_fin"]))
        for t in turnos_ocupados
    ]

    disponibles = []
    for slot in slots_validos:
        s_ini = _parse_time(slot)
        s_fin = s_ini + timedelta(minutes=duracion_min)
        if not any(s_ini < tf and s_fin > ti for ti, tf in ocupados_bloques):
            disponibles.append(slot)
    return disponibles
