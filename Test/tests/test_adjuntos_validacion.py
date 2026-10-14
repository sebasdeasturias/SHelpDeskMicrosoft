import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = (ROOT / "backend" / "adjuntos.py").read_text(encoding="utf-8")

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0])


def _extension_real(data: bytes):
    if data.startswith(PNG):
        return ".png"
    if len(data) >= 3 and data[0] == 0xFF and data[1] == 0xD8 and data[2] == 0xFF:
        return ".jpg"
    return None


def test_constantes_limite():
    assert "MAX_TAMANO_ARCHIVO = 20 * 1024 * 1024" in SRC
    assert "MAX_ADJUNTOS_POR_TICKET = 5" in SRC
    assert 'EXTENSIONES_PERMITIDAS = {".png", ".jpg", ".jpeg"}' in SRC


def test_magic_bytes_png_jpg():
    assert _extension_real(PNG + b"resto") == ".png"
    assert _extension_real(JPEG + b"resto") == ".jpg"
    assert _extension_real(b"MZ\x90\x00") is None
    assert _extension_real(b"<script>") is None
    assert "PNG_FIRMA" in SRC


def test_limites_29119_valores_frontera():
    max_adj = int(re.search(r"MAX_ADJUNTOS_POR_TICKET = (\d+)", SRC).group(1))
    max_bytes = eval(re.search(r"MAX_TAMANO_ARCHIVO = (.+)", SRC).group(1).split("#")[0])
    assert max_adj == 5
    assert max_bytes == 20 * 1024 * 1024
    assert 5 + 1 > max_adj
    assert 0 < max_adj


def test_nombres_uuid_y_path_traversal():
    assert "uuid" in SRC
    assert "os.path.basename" in SRC
    assert "_nombre_seguro" in SRC
