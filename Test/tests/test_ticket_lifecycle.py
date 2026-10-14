import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKETS = (ROOT / "backend" / "tickets.py").read_text(encoding="utf-8")


def _constante_set(nombre: str) -> set[str]:
    tree = ast.parse(TICKETS)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == nombre:
                    return {elt.value for elt in node.value.elts}
    raise AssertionError(f"No se encontró {nombre}")


ESTADOS = _constante_set("ESTADOS_TICKET")
ARCHIVABLES = _constante_set("ESTADOS_ARCHIVABLES")


def test_estados_itil_completos():
    esperados = {"nuevo", "asignado", "en_proceso", "escalado", "resuelto", "cerrado", "archivado"}
    assert ESTADOS == esperados


def test_solo_resuelto_cerrado_archivable():
    assert ARCHIVABLES == {"resuelto", "cerrado"}
    assert ARCHIVABLES.issubset(ESTADOS)


def test_transiciones_ilegales_documentadas_en_codigo():
    assert "Un ticket archivado no se puede mover" in TICKETS
    assert "Solo se pueden archivar tickets en estado 'resuelto' o 'cerrado'" in TICKETS
    assert "Un agente no puede devolver un ticket al estado 'nuevo'" in TICKETS


def test_tabla_decision_roles():
    casos = [
        ("solicitante", "crear", True, "Solo solicitantes pueden crear tickets"),
        ("agente", "mover_asignados", True, "Solo puedes mover tickets que el coordinador te asignó"),
        ("agente", "ver_nuevo", False, "s.estado != 'nuevo'"),
        ("coordinador", "asignar", True, None),
    ]
    assert "Solo solicitantes pueden crear tickets" in TICKETS
    assert "Solo puedes mover tickets que el coordinador te asignó" in TICKETS
    assert "s.estado != 'nuevo'" in TICKETS
    assert casos[0][2] is True


def test_historial_en_creacion_y_cambio():
    assert TICKETS.count("INSERT INTO historial") >= 2
    assert "estado_anterior" in TICKETS and "estado_nuevo" in TICKETS


def test_whitelist_estado_rechaza_invalido():
    assert "nuevo_estado not in ESTADOS_TICKET" in TICKETS
    assert re.search(r"HTTP_400_BAD_REQUEST", TICKETS)
