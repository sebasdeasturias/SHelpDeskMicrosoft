"""
Auditoría TLS de los dominios (solo lectura): versión mínima/máxima aceptada,
cipher negociada, cadena de certificados y rechazo de TLS antiguo.

Salida: test/datos/tls.json
Uso:    python test/scripts/tls.py
"""
import datetime
import json
import pathlib
import socket
import ssl

BASE = pathlib.Path(__file__).resolve().parents[1]
DATOS = BASE / "datos"
DATOS.mkdir(parents=True, exist_ok=True)

HOSTS = [
    ("sistemahelpdesk.online", 443),
    ("www.sistemahelpdesk.online", 443),
    ("api.sistemahelpdesk.online", 443),
]


def negociar(host, puerto, minimo=None, maximo=None):
    ctx = ssl.create_default_context()
    if minimo:
        ctx.minimum_version = minimo
    if maximo:
        ctx.maximum_version = maximo
    with socket.create_connection((host, puerto), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
            return {
                "protocolo": tls.version(),
                "cipher": tls.cipher()[0],
                "cipher_bits": tls.cipher()[1],
                "alpn": tls.selected_alpn_protocol(),
                "cert_subjetivo": dict(x[0] for x in cert.get("subject", ())),
                "cert_emiisor": dict(x[0] for x in cert.get("issuer", ())),
                "cert_desde": cert.get("notBefore"),
                "cert_hasta": cert.get("notAfter"),
                "cert_san": [v for k, v in cert.get("subjectAltName", ())],
                "dias_restantes": dias_restantes(cert.get("notAfter")),
            }


def dias_restantes(no_after):
    if not no_after:
        return None
    fin = datetime.datetime.strptime(no_after, "%b %d %H:%M:%S %Y %Z")
    return (fin - datetime.datetime.utcnow()).days


def probar_version(host, puerto, etiqueta, minimo, maximo):
    try:
        negociar(host, puerto, minimo=minimo, maximo=maximo)
        return {"version": etiqueta, "aceptada": True}
    except Exception as e:  # noqa: BLE001
        return {"version": etiqueta, "aceptada": False,
                "error": f"{type(e).__name__}: {str(e)[:140]}"}


def main():
    informe = {"hostes": {}, "versiones_antiguas": {}}
    for host, puerto in HOSTS:
        try:
            informe["hostes"][host] = negociar(host, puerto)
        except Exception as e:  # noqa: BLE001
            informe["hostes"][host] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    host = "api.sistemahelpdesk.online"
    informe["versiones_antiguas"] = [
        probar_version(host, 443, "TLS 1.0", ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1),
        probar_version(host, 443, "TLS 1.1", ssl.TLSVersion.TLSv1_1, ssl.TLSVersion.TLSv1_1),
        probar_version(host, 443, "TLS 1.2", ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2),
        probar_version(host, 443, "TLS 1.3", ssl.TLSVersion.TLSv1_3, ssl.TLSVersion.TLSv1_3),
    ]
    destino = DATOS / "tls.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK ->", destino)
    for h, d in informe["hostes"].items():
        if "error" in d:
            print(f"  {h}: ERROR {d['error']}")
        else:
            print(f"  {h}: {d['protocolo']} {d['cipher']} ({d['cipher_bits']} bits) "
                  f"ALPN={d['alpn']} caduca={d['cert_hasta']} dias={d['dias_restantes']}")
    for v in informe["versiones_antiguas"]:
        estado = "ACEPTADA (!)" if v["aceptada"] else "rechazada (ok)"
        print(f"  {v['version']}: {estado}")


if __name__ == "__main__":
    main()
