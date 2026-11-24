# backend/balanceo.py
# Reglas de balanceo de tickets del panel de coordinación.
#
# Política (única fuente de verdad, sin dependencias de BD para poder probarla
# de forma aislada):
#   1. Los tickets se reparten primero entre AGENTES activos con cupo diario.
#   2. Cuando todos los agentes alcanzan su cupo, el excedente ("rebalse") se
#      deriva a COORDINADORES activos con cupo.
#   3. Los ADMINISTRADORES nunca reciben tickets por balanceo.
#
# El cupo diario (`max_diario`) es el mismo para agentes y coordinadores y se
# controla con MAX_TICKETS_AGENTE_DIA. Un usuario inactivo nunca es candidato.
from typing import Dict, Iterable, List, Optional

# Orden de preferencia del balanceo: agente primero, coordinador como rebalse.
ROL_PRIMARIO = "agente"
ROL_REBALSE = "coordinador"
ROLES_BALANCEO = (ROL_PRIMARIO, ROL_REBALSE)

# El administrador queda fuera a propósito (regla de negocio).
ROLES_EXCLUIDOS = ("administrador",)

AFINIDAD_BASE = 95.0
AFINIDAD_MINIMA = 60.0


def _entero(valor) -> int:
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def afinidad(carga_trabajo, asignados_hoy) -> float:
    """Afinidad orientativa para la UI: penaliza carga actual y cupo consumido."""
    valor = AFINIDAD_BASE - _entero(carga_trabajo) * 5 - _entero(asignados_hoy) * 2
    return round(max(AFINIDAD_MINIMA, valor), 1)


def _candidatos(
    agentes: Iterable[Dict],
    rol: str,
    max_diario: int,
    excluir: set,
) -> List[Dict]:
    """Usuarios del rol indicado que pueden recibir un ticket ahora mismo."""
    return [
        a
        for a in agentes
        if a.get("rol") == rol
        and (a.get("estado") or "activo") == "activo"
        and a.get("id_usuario") not in excluir
        and _entero(a.get("asignados_hoy")) < max_diario
    ]


def _clave_orden(agente: Dict):
    # Menos asignados hoy, luego menor carga viva, luego nombre (estable).
    return (
        _entero(agente.get("asignados_hoy")),
        _entero(agente.get("carga_trabajo")),
        str(agente.get("nombre") or "").lower(),
    )


def recomendar(
    agentes: Iterable[Dict],
    max_diario: int = 3,
    excluir: Optional[Iterable] = None,
) -> Optional[Dict]:
    """Devuelve el destino recomendado para UN ticket.

    `agentes` son diccionarios con al menos: id_usuario, nombre, rol, estado,
    carga_trabajo y asignados_hoy. Devuelve None si no hay nadie con cupo.
    """
    agentes = list(agentes or [])
    if not agentes:
        return None
    excluir = set(excluir or ())

    for rol in ROLES_BALANCEO:
        disponibles = _candidatos(agentes, rol, max_diario, excluir)
        if not disponibles:
            continue
        elegido = min(disponibles, key=_clave_orden)
        return {
            "id_usuario": elegido["id_usuario"],
            "nombre": elegido.get("nombre"),
            "rol": rol,
            "rebalse": rol == ROL_REBALSE,
            "afinidad": afinidad(
                elegido.get("carga_trabajo"), elegido.get("asignados_hoy")
            ),
        }
    return None


def recomendar_lote(
    agentes: Iterable[Dict],
    cantidad: int,
    max_diario: int = 3,
) -> List[Optional[Dict]]:
    """Recomienda destinos para varios tickets pendientes a la vez.

    Trabaja sobre una copia de la carga y la incrementa con cada recomendación,
    de modo que una cola de N tickets se reparte entre los candidatos en vez de
    apuntar todos al mismo agente. Así el balanceo que muestra la UI coincide
    con el que termina aplicándose ticket a ticket.
    """
    snapshot = [dict(a) for a in (agentes or [])]
    recomendaciones: List[Optional[Dict]] = []

    for _ in range(max(0, _entero(cantidad))):
        rec = recomendar(snapshot, max_diario)
        recomendaciones.append(rec)
        if not rec:
            # Sin capacidad: el resto de la cola tampoco tiene destino.
            continue
        for agente in snapshot:
            if agente.get("id_usuario") == rec["id_usuario"]:
                agente["asignados_hoy"] = _entero(agente.get("asignados_hoy")) + 1
                agente["carga_trabajo"] = _entero(agente.get("carga_trabajo")) + 1
                break

    return recomendaciones


def capacidad(agentes: Iterable[Dict], max_diario: int = 3) -> Dict[str, int]:
    """Usuarios con cupo disponible por nivel (0 = ese nivel está al límite)."""
    agentes = list(agentes or [])
    return {
        f"{rol}_libres": len(_candidatos(agentes, rol, max_diario, set()))
        for rol in ROLES_BALANCEO
    }
