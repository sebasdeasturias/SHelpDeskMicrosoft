"""
Métricas de código del repositorio SHelpDeskMicrosoft (análisis estático local).

  - LOC y ficheros por carpeta y extensión
  - Complejidad aproximada (ramas if/for/while/except) y ficheros más grandes
  - Inventario de endpoints de la API desde openapi.json (test/datos)
  - Tamaño de los estáticos del frontend

Salidas: test/datos/metricas.json, test/datos/endpoints.csv, test/datos/archivos_top.csv
Uso:     python test/scripts/metricas_codigo.py
"""
import csv
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]   # SHelpDeskMicrosoft/
DATOS = RAIZ / "test" / "datos"
DATOS.mkdir(parents=True, exist_ok=True)

IGNORAR = {".git", "node_modules", "__pycache__", "build", "test", ".gradle", ".idea"}
EXT_Lenguaje = {
    ".py": "Python", ".js": "JavaScript", ".css": "CSS", ".html": "HTML",
    ".yml": "YAML", ".yaml": "YAML", ".sql": "SQL", ".json": "JSON",
    ".md": "Markdown", ".ps1": "PowerShell", ".sh": "Shell", ".env": "Env",
}
RAMAS = re.compile(r"^\s*(if|elif|else|for|while|except|try|with|and|or|case)\b")
DEC_RUTA = re.compile(r"^\s*@?(router|app)\.(get|post|patch|delete|put)\(")


def recorrer(raiz):
    for p in raiz.rglob("*"):
        if any(x in p.parts for x in IGNORAR):
            continue
        if p.is_file():
            yield p


def contar_archivo(path):
    try:
        texto = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    lineas = texto.splitlines()
    ramas = sum(1 for l in lineas if RAMAS.match(l))
    return {
        "lineas": len(lineas),
        "no_vacias": sum(1 for l in lineas if l.strip()),
        "ramas": ramas,
        "rutas_deco": sum(1 for l in lineas if DEC_RUTA.match(l)),
    }


def metricas_carpetas():
    out = {}
    for carpeta in sorted(x for x in RAIZ.iterdir() if x.is_dir() and x.name not in IGNORAR):
        acum = {"ficheros": 0, "lineas": 0, "por_extension": {}}
        for f in recorrer(carpeta):
            r = contar_archivo(f)
            if r is None:
                continue
            acum["ficheros"] += 1
            acum["lineas"] += r["lineas"]
            ext = f.suffix.lower() or "(sin)"
            dato = acum["por_extension"].setdefault(
                ext, {"extension": ext, "idioma": EXT_Lenguaje.get(ext, ext),
                      "ficheros": 0, "lineas": 0})
            dato["ficheros"] += 1
            dato["lineas"] += r["lineas"]
        out[carpeta.name] = acum
    return out


def metricas_backend():
    backend = RAIZ / "backend"
    archivos, total_rutas, total_ramas = [], 0, 0
    for f in recorrer(backend):
        if f.suffix != ".py":
            continue
        r = contar_archivo(f)
        r.update({"archivo": f.name, "lineas": r["lineas"]})
        archivos.append(r)
        total_rutas += r["rutas_deco"]
        total_ramas += r["ramas"]
    archivos.sort(key=lambda x: -x["lineas"])
    return {
        "ficheros_py": len(archivos),
        "lineas_py": sum(a["lineas"] for a in archivos),
        "rutas_declaradas": total_rutas,
        "ramas_totales": total_ramas,
        "archivos": archivos,
    }


def metricas_frontend():
    frontend = RAIZ / "frontend"
    res = {"html": 0, "js": 0, "css": 0, "lineas": 0, "bytes": 0, "paginas": []}
    for f in recorrer(frontend):
        ext = f.suffix.lower()
        if ext in (".html", ".js", ".css"):
            r = contar_archivo(f) or {"lineas": 0}
            res[ext[1:]] += 1
            res["lineas"] += r["lineas"]
            res["bytes"] += f.stat().st_size
            if ext == ".html":
                res["paginas"].append(f.name)
    res["paginas"].sort()
    return res


def endpoints_openapi():
    ruta = DATOS / "openapi.json"
    if not ruta.exists():
        return []
    d = json.loads(ruta.read_text(encoding="utf-8"))
    filas = []
    for p, ops in d.get("paths", {}).items():
        for m, o in ops.items():
            seg = p.strip("/").split("/")[1] if p.strip("/") else "(raiz)"
            grupo = seg.split("{")[0] if "{" in seg else seg
            seguridad = o.get("security", d.get("security", []))
            filas.append({
                "metodo": m.upper(), "ruta": p, "grupo": grupo,
                "resumen": (o.get("summary") or "")[:80],
                "requiere_auth": "sí" if seguridad else "no/depende",
                "tags": ",".join(o.get("tags", [])),
            })
    filas.sort(key=lambda x: (x["grupo"], x["ruta"], x["metodo"]))
    return filas


def main():
    datos = {
        "carpetas": metricas_carpetas(),
        "backend": metricas_backend(),
        "frontend": metricas_frontend(),
    }
    (DATOS / "metricas.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    eps = endpoints_openapi()
    if eps:
        with (DATOS / "endpoints.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(eps[0].keys()))
            w.writeheader()
            w.writerows(eps)

    top = []
    for carpeta, acum in datos["carpetas"].items():
        for f in recorrer(RAIZ / carpeta):
            r = contar_archivo(f)
            if r:
                top.append({"carpeta": carpeta, "archivo": str(f.relative_to(RAIZ)),
                            "lineas": r["lineas"], "ramas": r["ramas"]})
    top.sort(key=lambda x: -x["lineas"])
    with (DATOS / "archivos_top.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["carpeta", "archivo", "lineas", "ramas"])
        w.writeheader()
        w.writerows(top[:60])

    print("OK -> metricas.json, endpoints.csv, archivos_top.csv")
    for c, a in datos["carpetas"].items():
        print(f"  {c:15} {a['ficheros']:5} ficheros  {a['lineas']:7} líneas")
    print(f"  backend: {datos['backend']['ficheros_py']} .py, "
          f"{datos['backend']['lineas_py']} líneas, "
          f"{datos['backend']['rutas_declaradas']} rutas declaradas")
    print(f"  frontend: {datos['frontend']['html']} html, "
          f"{datos['frontend']['js']} js, {datos['frontend']['css']} css, "
          f"{datos['frontend']['lineas']} líneas, {datos['frontend']['bytes']} bytes")
    print(f"  endpoints openapi: {len(eps)}")


if __name__ == "__main__":
    main()
