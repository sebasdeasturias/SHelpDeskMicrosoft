from scan import collect_all
from itil_eval import evaluar as evaluar_itil
from iso_eval import evaluar_todas, normas_sectoriales

_CACHE = None


def _eval():
    global _CACHE
    if _CACHE is None:
        bruto = collect_all()
        itil = evaluar_itil(bruto["corpus_all"])
        iso = evaluar_todas(bruto, itil)
        _CACHE = (itil, iso)
    return _CACHE


def test_itil_nucleo_mesa_servicio():
    itil, _ = _eval()
    assert itil["score_nucleo"] >= 80
    assert itil["cumple_mesa_servicio"] is True
    ids = {p["id"]: p for p in itil["practicas"]}
    for pid in ("incident_management", "service_desk", "service_level", "knowledge", "measurement"):
        assert ids[pid]["estado"] == "cumple", pid


def test_itil_completo_no_se_declara():
    itil, _ = _eval()
    assert itil["cumple_itil_completo"] is False
    ids = {p["id"]: p for p in itil["practicas"]}
    for pid in ("problem_management", "change_enablement", "configuration", "catalogue"):
        assert ids[pid]["estado"] == "no_implementada", pid


def test_iso25010_aplicable_y_medido():
    _, iso = _eval()
    n = iso["ISO_IEC_25010"]
    assert n["aplicable"] is True
    assert n["score"] >= 50
    nombres = [c["caracteristica"] for c in n["caracteristicas"]]
    assert "Seguridad" in nombres
    assert "Fiabilidad" in nombres
    assert "Adecuación funcional" in nombres


def test_iso27001_no_es_sgis_certificable():
    _, iso = _eval()
    n = iso["ISO_IEC_27001"]
    isms = [c for c in n["criterios"] if c["id"] == "ISMS"][0]
    assert isms["estado"] == "no_cumple"
    assert "NO hay SGSI" in n["nota"]


def test_iso20000_incidentes_si_sms_no():
    _, iso = _eval()
    n = iso["ISO_IEC_20000_1"]
    by_id = {c["id"]: c for c in n["criterios"]}
    assert by_id["8.5.1"]["estado"] == "cumple"
    assert by_id["8.5.2"]["estado"] == "no_cumple"
    assert by_id["4-10"]["estado"] == "no_cumple"


def test_sectoriales_no_aplican():
    sector = normas_sectoriales()
    for clave in ("ISO_13485", "IATF_16949", "AS9100", "ISO_22000", "ISO_17025"):
        assert sector[clave]["aplicable"] is False
        assert sector[clave]["veredicto"].startswith("NO_APLICA")


def test_9001_no_se_certifica_el_producto():
    _, iso = _eval()
    n = iso["ISO_9000_9001_9004_19011"]["ISO_9001"]
    assert n["aplicable"] is False
    assert "NO_APLICA" in n["veredicto"]


def test_29119_proceso_de_este_paquete():
    _, iso = _eval()
    n = iso["ISO_IEC_IEEE_29119"]
    assert n["score"] >= 80
    assert len(n["tecnicas_aplicadas"]) >= 4
