from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "database" / "db_logic.sql").read_text(encoding="utf-8")
AUTH = (ROOT / "backend" / "auth.py").read_text(encoding="utf-8")
COORD = (ROOT / "backend" / "coordinator.py").read_text(encoding="utf-8")
CHAT = (ROOT / "backend" / "chat_global.py").read_text(encoding="utf-8")


def test_equivalencia_roles():
    roles = ("solicitante", "agente", "coordinador", "administrador")
    for rol in roles:
        assert rol in SQL
        assert rol in AUTH or rol in COORD


def test_equivalencia_prioridades_y_sla_semilla():
    assert "crítica" in SQL and "alta" in SQL and "media" in SQL and "baja" in SQL
    assert "(1, 'crítica', '#FF0000', 15, 60)" in SQL
    assert "(2, 'alta', '#FFA500', 30, 240)" in SQL
    assert "(3, 'media', '#FFFF00', 60, 480)" in SQL
    assert "(4, 'baja', '#00FF00', 120, 1440)" in SQL


def test_limite_password_8():
    assert "len(password) < 8" in COORD
    assert "al menos 8" in COORD.lower() or "al menos 8" in COORD


def test_limite_mensaje_chat_1000():
    assert "LIMITE_MENSAJE = 1000" in CHAT


def test_tabla_decision_ultimo_admin():
    assert "último administrador activo" in COORD or "ultimo administrador activo" in COORD.lower()
    assert "_admins_activos" in COORD


def test_categorias_servicio_itil():
    for cat in ("Hardware", "Software", "Red/Internet", "Cuentas/Accesos", "Otros"):
        assert cat in SQL
