"""Reglas de balanceo de tickets del panel de coordinación.

Política esperada:
  1. Primero agentes activos con cupo diario.
  2. El excedente (rebalse) va a coordinadores activos con cupo.
  3. Los administradores nunca reciben tickets.
"""
from collections import Counter
from pathlib import Path

from balanceo import (
    ROLES_BALANCEO,
    ROLES_EXCLUIDOS,
    capacidad,
    recomendar,
    recomendar_lote,
)

ROOT = Path(__file__).resolve().parents[2]
COORDINATOR = (ROOT / "backend" / "coordinator.py").read_text(encoding="utf-8")


def usuario(id_usuario, rol="agente", carga=0, hoy=0, estado="activo", nombre=None):
    return {
        "id_usuario": id_usuario,
        "nombre": nombre or f"{rol}-{id_usuario}",
        "rol": rol,
        "estado": estado,
        "carga_trabajo": carga,
        "asignados_hoy": hoy,
    }


# --------------------------------------------------------------------------
# Reglas de negocio
# --------------------------------------------------------------------------
def test_orden_de_roles_y_admin_excluido():
    assert ROLES_BALANCEO == ("agente", "coordinador")
    assert "administrador" in ROLES_EXCLUIDOS
    assert "administrador" not in ROLES_BALANCEO


def test_prefiere_agente_aunque_el_coordinador_este_mas_libre():
    agentes = [
        usuario(1, "coordinador", carga=0, hoy=0),
        usuario(2, "agente", carga=5, hoy=0),
    ]
    rec = recomendar(agentes, max_diario=3)
    assert rec["id_usuario"] == 2
    assert rec["rol"] == "agente"
    assert rec["rebalse"] is False


def test_administrador_nunca_es_candidato():
    assert recomendar([usuario(1, "administrador")], max_diario=3) is None


def test_rebalse_a_coordinador_cuando_los_agentes_estan_al_cupo():
    agentes = [
        usuario(1, "agente", carga=2, hoy=3),
        usuario(2, "agente", carga=1, hoy=4),
        usuario(3, "coordinador", carga=0, hoy=0),
    ]
    rec = recomendar(agentes, max_diario=3)
    assert rec["id_usuario"] == 3
    assert rec["rol"] == "coordinador"
    assert rec["rebalse"] is True


def test_sin_capacidad_devuelve_none():
    agentes = [
        usuario(1, "agente", hoy=3),
        usuario(2, "coordinador", hoy=3),
        usuario(3, "administrador", hoy=0),
    ]
    assert recomendar(agentes, max_diario=3) is None


def test_usuario_inactivo_no_recibe_tickets():
    agentes = [usuario(1, "agente", estado="inactivo")]
    assert recomendar(agentes, max_diario=3) is None


def test_prioriza_menos_asignados_hoy_y_menor_carga():
    agentes = [
        usuario(1, "agente", carga=4, hoy=2),
        usuario(2, "agente", carga=1, hoy=0),
        usuario(3, "agente", carga=1, hoy=1),
    ]
    assert recomendar(agentes, max_diario=3)["id_usuario"] == 2


# --------------------------------------------------------------------------
# Balanceo en lote (la cola se reparte, no apunta toda al mismo destino)
# --------------------------------------------------------------------------
def test_lote_reparte_entre_agentes():
    agentes = [usuario(i, "agente") for i in range(1, 5)]
    recs = recomendar_lote(agentes, cantidad=8, max_diario=3)
    assert len(recs) == 8
    assert Counter(r["id_usuario"] for r in recs) == {1: 2, 2: 2, 3: 2, 4: 2}


def test_lote_derrama_el_excedente_a_coordinadores():
    agentes = [
        usuario(1, "agente"),
        usuario(2, "agente"),
        usuario(3, "coordinador"),
        usuario(4, "coordinador"),
        usuario(5, "administrador"),
    ]
    recs = recomendar_lote(agentes, cantidad=8, max_diario=3)
    por_rol = Counter(r["rol"] for r in recs)
    # 2 agentes x 3 = 6 al nivel primario; 2 al rebalse.
    assert por_rol == {"agente": 6, "coordinador": 2}
    assert all(r["id_usuario"] != 5 for r in recs)


def test_lote_respeta_cupo_ya_consumido():
    agentes = [
        usuario(1, "agente", hoy=2),
        usuario(2, "coordinador", hoy=0),
    ]
    recs = recomendar_lote(agentes, cantidad=3, max_diario=3)
    assert [r["id_usuario"] for r in recs] == [1, 2, 2]


def test_capacidad_cuenta_libres_por_nivel():
    agentes = [
        usuario(1, "agente", hoy=0),
        usuario(2, "agente", hoy=3),
        usuario(3, "coordinador", hoy=1),
        usuario(4, "administrador", hoy=0),
    ]
    assert capacidad(agentes, max_diario=3) == {
        "agente_libres": 1,
        "coordinador_libres": 1,
    }


# --------------------------------------------------------------------------
# Contrato del endpoint de coordinación
# --------------------------------------------------------------------------
def test_asignacion_usa_el_modulo_de_balanceo():
    assert "from balanceo import" in COORDINATOR
    assert "recomendar_balanceo_lote" in COORDINATOR


def test_asignacion_solo_consulta_agentes_y_coordinadores_activos():
    assert "WHERE u.rol IN ('agente','coordinador')" in COORDINATOR
    assert "u.estado = 'activo'" in COORDINATOR


def test_asignar_limita_destino_a_roles_de_balanceo():
    assert "agente[1] not in ROLES_BALANCEO" in COORDINATOR


def test_cola_solo_incluye_estados_abiertos():
    assert "s.estado IN ('nuevo','asignado','en_proceso','escalado')" in COORDINATOR
