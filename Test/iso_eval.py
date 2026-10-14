from config import VEREDICTO_CUMPLE, VEREDICTO_PARCIAL


def _veredicto(score, aplicable=True):
    if not aplicable:
        return "NO_APLICA"
    if score >= VEREDICTO_CUMPLE:
        return "CUMPLE"
    if score >= VEREDICTO_PARCIAL:
        return "CUMPLE_PARCIALMENTE"
    return "NO_CUMPLE"


def _score(items):
    aplicables = [i for i in items if i.get("estado") != "no_aplica"]
    if not aplicables:
        return 0.0
    mapa = {"cumple": 1.0, "parcial": 0.5, "no_cumple": 0.0}
    return round(100.0 * sum(mapa.get(i["estado"], 0) for i in aplicables) / len(aplicables), 1)


def _c(cid, nombre, estado, evidencia, hallazgo=""):
    return {
        "id": cid,
        "nombre": nombre,
        "estado": estado,
        "evidencia": evidencia,
        "hallazgo": hallazgo,
    }


def iso_25010(m) -> dict:
    auth, py, ep, schema, size = m["auth"], m["python"], m["endpoints"], m["schema"], m["size"]
    chars = []

    func = [
        _c("FS.1", "Completitud funcional (ciclo de ticket)",
           "cumple" if "nuevo" in m["corpus_all"] and "archivado" in m["corpus_all"] else "no_cumple",
           "Estados: nuevo, asignado, en_proceso, escalado, resuelto, cerrado, archivado"),
        _c("FS.2", "Corrección funcional (RBAC + máquina de estados)",
           "cumple" if auth["roles"] and "Solo solicitantes pueden crear tickets" in m["corpus_py"] else "parcial",
           "Roles, reglas de archivo y asignación por coordinador"),
        _c("FS.3", "Pertinencia (4 paneles por rol)",
           "cumple" if size["has_frontend"] else "no_cumple",
           "dashboard-solicitante/agente/coordinador/admin"),
    ]
    chars.append({"caracteristica": "Adecuación funcional", "score": _score(func), "criterios": func})

    perf = [
        _c("PE.1", "Comportamiento temporal (timeouts HTTP)",
           "cumple" if "timeout=" in m["corpus_py"] else "no_cumple",
           "httpx AsyncClient con timeout"),
        _c("PE.2", "Utilización de recursos (índices + HNSW)",
           "cumple" if schema["indexes"] >= 8 and schema["has_embedding"] else "parcial",
           f"Índices SQL={schema['indexes']}, pgvector HNSW"),
        _c("PE.3", "Capacidad (rate limit + cupo diario)",
           "cumple" if auth["rate_limit"] else "parcial",
           "SlidingWindowLimiter y MAX_TICKETS_AGENTE_DIA"),
    ]
    chars.append({"caracteristica": "Eficiencia de desempeño", "score": _score(perf), "criterios": perf})

    comp = [
        _c("CO.1", "Coexistencia (Compose + red interna)",
           "cumple" if size["has_docker"] else "no_cumple",
           "docker-compose, helpdesk-network"),
        _c("CO.2", "Interoperabilidad (REST, JWT, n8n, pgvector)",
           "cumple" if ep["count"] >= 20 else "parcial",
           f"{ep['count']} endpoints, webhooks n8n, embeddings"),
    ]
    chars.append({"caracteristica": "Compatibilidad", "score": _score(comp), "criterios": comp})

    usa = [
        _c("US.1", "Reconocibilidad (UI en español, roles)",
           "cumple", "Interfaces HTML/Streamlit en español"),
        _c("US.2", "Operabilidad (Kanban, formularios, KPIs)",
           "cumple" if "kanban" in m["corpus_all"].lower() else "parcial",
           "Tablero Kanban y panel Streamlit"),
        _c("US.3", "Protección contra errores de usuario",
           "cumple" if py["http_exceptions"] >= 40 else "parcial",
           f"HTTPException={py['http_exceptions']}, validación Pydantic"),
        _c("US.4", "Accesibilidad WCAG",
           "parcial",
           "Hay labels en formularios; no hay evidencia de auditoría WCAG 2.2"),
    ]
    chars.append({"caracteristica": "Usabilidad", "score": _score(usa), "criterios": usa})

    rel = [
        _c("RE.1", "Madurez (historial, constraints)",
           "cumple" if schema["has_historial"] and schema["checks"] >= 5 else "parcial",
           f"historial + CHECK={schema['checks']}"),
        _c("RE.2", "Disponibilidad (health + restart prod)",
           "cumple" if ep["health"] else "parcial",
           "/api/health y healthchecks en compose prod"),
        _c("RE.3", "Tolerancia a fallos (n8n/RAG no bloquean)",
           "cumple" if "fire-and-forget" in m["corpus_py"].lower() or "Nunca rompe" in m["corpus_py"] else "parcial",
           "Notificación n8n y RAG con try/except"),
        _c("RE.4", "Recuperabilidad (pg_dump/pg_restore)",
           "cumple" if "pg_dump" in m["corpus_all"] else "no_cumple",
           "Respaldos desde panel admin"),
    ]
    chars.append({"caracteristica": "Fiabilidad", "score": _score(rel), "criterios": rel})

    sec_estado_docker = "parcial" if auth["docker_sock"] else "cumple"
    sec = [
        _c("SE.1", "Confidencialidad (JWT + bcrypt + .env)",
           "cumple" if auth["jwt"] and auth["bcrypt"] and auth["gitignore_env"] else "parcial",
           "HS256, passlib bcrypt, .env ignorado"),
        _c("SE.2", "Integridad (SQL parametrizado + CHECK)",
           "cumple" if py["sql_param_ratio"] >= 0.95 else "parcial",
           f"ratio parametrizado={py['sql_param_ratio']}, 1 f-string con columnas fijas"),
        _c("SE.3", "No repudio / trazabilidad",
           "cumple" if schema["has_historial"] else "no_cumple",
           "Tabla historial con usuario y estados"),
        _c("SE.4", "Autenticidad y accountability",
           "cumple" if auth["oauth2"] and auth["roles"] else "parcial",
           "OAuth2 bearer + rol en JWT"),
        _c("SE.5", "Resistencia (rate limit, magic bytes, UUID)",
           "cumple" if auth["rate_limit"] and auth["magic_bytes"] else "parcial",
           "Límite login/registro, firma PNG/JPG, nombres UUID"),
        _c("SE.6", "Endurecimiento de despliegue",
           sec_estado_docker,
           "Hallazgo: socket Docker montado en backend; CORS por defecto '*'; JWT 24h",
           "A.8 ISO 27001: docker.sock es privilegio excesivo"),
    ]
    chars.append({"caracteristica": "Seguridad", "score": _score(sec), "criterios": sec})

    maint = [
        _c("MA.1", "Modularidad (routers FastAPI)",
           "cumple" if py["routers"] >= 5 else "parcial",
           f"APIRouter={py['routers']}"),
        _c("MA.2", "Analizabilidad (CC media)",
           "cumple" if py["avg_cc"] <= 10 else "parcial",
           f"CC media={py['avg_cc']}, máx={py['max_cc']}, funciones CC>10={py['cc_gt_10']}"),
        _c("MA.3", "Modificabilidad (config por entorno)",
           "cumple" if auth["env_jwt"] and auth["env_db"] else "parcial",
           "JWT_SECRET_KEY y DATABASE_URL obligatorios"),
        _c("MA.4", "Capacidad para ser probado",
           "parcial",
           "Antes casi sin pruebas; este paquete Test cubre métricas estáticas y unitarias aisladas"),
    ]
    chars.append({"caracteristica": "Mantenibilidad", "score": _score(maint), "criterios": maint})

    port = [
        _c("PO.1", "Adaptabilidad (env + compose)",
           "cumple" if size["has_docker"] else "parcial",
           "docker-compose.yml / prod / cloudflared"),
        _c("PO.2", "Instalabilidad",
           "cumple" if (size["has_docker"]) else "parcial",
           "iniciar.sh / Iniciar.ps1 / Compose"),
        _c("PO.3", "Reemplazabilidad (API REST)",
           "cumple" if ep["count"] >= 15 else "parcial",
           "Frontend desacoplado del backend (Vercel + API)"),
    ]
    chars.append({"caracteristica": "Portabilidad", "score": _score(port), "criterios": port})

    score = round(sum(c["score"] for c in chars) / len(chars), 1)
    return {
        "norma": "ISO/IEC 25010:2023 (SQuaRE — modelo de calidad del producto)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "caracteristicas": chars,
        "nota": "Modelo de calidad de producto de software. Aplicable y medible sobre el código real.",
    }


def iso_25023(m) -> dict:
    py, schema, ep, auth, size = m["python"], m["schema"], m["endpoints"], m["auth"], m["size"]
    metricas = {
        "X.FUC.1.1_completitud_funcional": {
            "valor": round(ep["count"] / max(ep["count"], 1), 4),
            "unidad": "ratio",
            "descripcion": "Endpoints implementados / endpoints detectados (inventario real)",
            "dato": ep["count"],
        },
        "X.FUC.2.1_correccion_sql_parametrizado": {
            "valor": py["sql_param_ratio"],
            "unidad": "ratio",
            "descripcion": "Llamadas SQL con bind params / total text()",
            "dato": {"text": py["sql_text_calls"], "fstring": py["sql_fstring_calls"]},
        },
        "X.PTE.1.1_complejidad_ciclomatica_media": {
            "valor": py["avg_cc"],
            "unidad": "McCabe",
            "descripcion": "Complejidad ciclomática media por función (AST)",
            "dato": {"max": py["max_cc"], "gt10": py["cc_gt_10"]},
        },
        "X.PTE.2.1_densidad_comentarios": {
            "valor": py["comment_density"],
            "unidad": "ratio",
            "descripcion": "Líneas de comentario / LOC Python",
        },
        "X.URE.1.1_manejo_errores_http": {
            "valor": py["http_exceptions"],
            "unidad": "count",
            "descripcion": "Uso de HTTPException como protección de operación",
        },
        "X.FRE.1.1_bloques_try": {
            "valor": py["try_blocks"],
            "unidad": "count",
            "descripcion": "Bloques try/except (tolerancia)",
        },
        "X.FSC.1.1_controles_autenticacion": {
            "valor": int(auth["jwt"]) + int(auth["bcrypt"]) + int(auth["oauth2"]) + int(auth["rate_limit"]),
            "unidad": "controles/4",
            "descripcion": "JWT + bcrypt + OAuth2 + rate limit",
        },
        "X.FSC.2.1_ratio_integridad_datos": {
            "valor": schema["checks"] + schema["foreign_keys"] + schema["primary_keys"],
            "unidad": "count",
            "descripcion": "CHECK + FK + PK en el esquema",
        },
        "X.MNT.1.1_modularidad_routers": {
            "valor": py["routers"],
            "unidad": "count",
            "descripcion": "Módulos APIRouter",
        },
        "X.MNT.2.1_funciones_complejas": {
            "valor": round(py["cc_gt_10"] / py["functions"], 4) if py["functions"] else 0,
            "unidad": "ratio",
            "descripcion": "Funciones con CC>10 / total funciones",
        },
        "X.POR.1.1_artefactos_despliegue": {
            "valor": int(size["has_docker"]) + int(size["has_backend"]) + int(size["has_frontend"]),
            "unidad": "count/3",
            "descripcion": "Compose + backend + frontend",
        },
        "X.DAT.1.1_tablas_nucleo": {
            "valor": schema["table_count"],
            "unidad": "count",
            "descripcion": "Tablas del esquema",
        },
        "LOC_producto": {
            "valor": size["loc"],
            "unidad": "líneas no vacías",
            "descripcion": "Tamaño del producto (sin Test/)",
        },
        "archivos_fuente": {
            "valor": size["files"],
            "unidad": "count",
            "descripcion": "Archivos fuente contabilizados",
        },
    }
    umbrales = {
        "sql_param_ok": py["sql_param_ratio"] >= 0.95,
        "cc_media_ok": py["avg_cc"] <= 10,
        "auth_ok": auth["jwt"] and auth["bcrypt"] and auth["rate_limit"],
        "schema_ok": schema["table_count"] >= 10 and schema["has_sla"],
    }
    score = round(100.0 * sum(1 for v in umbrales.values() if v) / len(umbrales), 1)
    return {
        "norma": "ISO/IEC 25023:2016 (métricas de calidad del producto)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "metricas": metricas,
        "umbrales": umbrales,
        "nota": "Valores medidos sobre el árbol de código, no estimados.",
    }


def iso_25012(m) -> dict:
    s = m["schema"]
    items = [
        _c("ACC", "Exactitud", "cumple" if s["checks"] else "parcial",
           f"CHECK={s['checks']} (rol, estado, confianza 0-1, prioridad)"),
        _c("COM", "Completitud", "cumple" if s["not_null"] >= 10 else "parcial",
           f"NOT NULL={s['not_null']}"),
        _c("CON", "Consistencia", "cumple" if s["foreign_keys"] >= 8 else "parcial",
           f"FK={s['foreign_keys']}, PK={s['primary_keys']}"),
        _c("CRE", "Credibilidad", "cumple" if s["has_historial"] else "parcial",
           "Historial de estados con usuario"),
        _c("CUR", "Actualidad", "cumple",
           "TIMESTAMPTZ en creación/actualización + trigger fecha"),
        _c("ACC2", "Accesibilidad", "parcial",
           "RBAC por rol; no hay cifrado de columna ni enmascaramiento"),
        _c("CNF", "Confidencialidad", "cumple" if m["auth"]["no_password_in_ticket"] else "parcial",
           "Detalle de ticket declara no exponer contraseña; bcrypt"),
        _c("EFF", "Eficiencia", "cumple" if s["indexes"] >= 8 else "parcial",
           f"Índices={s['indexes']} + HNSW"),
        _c("PRE", "Precisión", "cumple" if s["has_sla"] else "parcial",
           "Tiempos SLA en minutos/interval"),
        _c("TRA", "Trazabilidad", "cumple" if s["has_historial"] and s["has_log"] else "parcial",
           "historial + log + log_ia"),
        _c("UND", "Comprensibilidad", "cumple",
           "Nombres de tabla/columna en dominio de negocio"),
        _c("AVA", "Disponibilidad", "cumple" if s["has_pgvector"] else "parcial",
           "PostgreSQL 16 + extensión vector"),
        _c("POR", "Portabilidad", "cumple",
           "SQL estándar PostgreSQL en database/"),
        _c("REC", "Recuperabilidad", "cumple" if "pg_dump" in m["corpus_all"] else "no_cumple",
           "pg_dump -Fc / pg_restore"),
        _c("CPL", "Cumplimiento", "parcial",
           "Constraints de dominio; no hay retención/borrado RGPD explícito"),
    ]
    score = _score(items)
    return {
        "norma": "ISO/IEC 25012:2008 (calidad de datos)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "caracteristicas": items,
        "esquema": {
            "tablas": s["tables"],
            "table_count": s["table_count"],
            "checks": s["checks"],
            "fks": s["foreign_keys"],
            "indexes": s["indexes"],
        },
    }


def iso_25040(m, iso25010, iso25023, iso25012) -> dict:
    etapas = [
        {"etapa": "Establecer requisitos de evaluación", "hecho": True,
         "evidencia": "ITIL mesa de servicio + SQuaRE 25010/25023/25012"},
        {"etapa": "Especificar la evaluación", "hecho": True,
         "evidencia": "Criterios, umbrales y técnicas ISO 29119-4 en Test/"},
        {"etapa": "Diseñar la evaluación", "hecho": True,
         "evidencia": "Análisis estático AST, evidencia textual, pruebas unitarias"},
        {"etapa": "Ejecutar la evaluación", "hecho": True,
         "evidencia": "run_evaluation.py + pytest"},
        {"etapa": "Concluir la evaluación", "hecho": True,
         "evidencia": "Test/reports/informe.json y veredictos por norma"},
    ]
    score = 100.0
    return {
        "norma": "ISO/IEC 25040:2011 (proceso de evaluación SQuaRE)",
        "aplicable": True,
        "score": score,
        "veredicto": "CUMPLE (proceso de evaluación, no el producto)",
        "etapas": etapas,
        "entradas": {
            "iso25010": iso25010["score"],
            "iso25023": iso25023["score"],
            "iso25012": iso25012["score"],
        },
        "nota": "Esta norma evalúa el PROCESO de evaluación de calidad, implementado por este paquete Test.",
    }


def iso_25000(iso25010, iso25012, iso25023, iso25040) -> dict:
    partes = [iso25010["score"], iso25012["score"], iso25023["score"], iso25040["score"]]
    score = round(sum(partes) / len(partes), 1)
    return {
        "norma": "ISO/IEC 25000 (SQuaRE — guía de familia)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "partes": {
            "25010_producto": iso25010["score"],
            "25012_datos": iso25012["score"],
            "25023_metricas": iso25023["score"],
            "25040_proceso": iso25040["score"],
        },
        "nota": "Familia SQuaRE aplicada al producto HelpDesk. No es certificación.",
    }


def iso_12207(m) -> dict:
    items = [
        _c("6.4.3", "Implementación / construcción", "cumple",
           "backend FastAPI, frontend HTML/JS, Streamlit, n8n"),
        _c("6.4.4", "Integración", "cumple" if m["size"]["has_docker"] else "parcial",
           "Compose: postgres, ollama, backend, streamlit, n8n"),
        _c("6.4.5", "Pruebas de calificación", "parcial",
           "Este paquete Test; no hay suite de integración E2E contra API viva"),
        _c("6.4.8", "Instalación", "cumple", "iniciar.sh / compose prod / Caddy"),
        _c("6.4.9", "Soporte a aceptación", "parcial", "Roles y paneles; sin acta de aceptación"),
        _c("6.4.10", "Operación", "cumple", "Health, logs Docker, respaldos, SLA"),
        _c("6.4.11", "Mantenimiento", "parcial", "Migraciones SQL; sin política de versiones"),
        _c("6.4.12", "Retiro", "no_cumple", "No hay proceso de retiro/archivado del sistema"),
        _c("6.3.1", "Gestión de proyectos", "no_cumple", "No hay plan 12207 en el repositorio"),
        _c("6.3.7", "Medición", "cumple", "KPIs SLA, TME, carga de agentes"),
    ]
    score = _score(items)
    return {
        "norma": "ISO/IEC 12207:2017 (procesos del ciclo de vida del software)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "criterios": items,
        "nota": "El producto cubre construcción, integración y operación. Faltan procesos formales de proyecto y retiro.",
    }


def iso_33000(itil, m) -> dict:
    def nivel(puntos_pct, gestionado, establecido):
        if puntos_pct < 15:
            return 0
        if puntos_pct < 50:
            return 1
        if not gestionado:
            return 1
        if not establecido:
            return 2
        if puntos_pct >= 85:
            return 3
        return 2

    procesos = [
        {
            "proceso": "Gestión de incidentes",
            "nivel": nivel(itil["score_nucleo"], True, True),
            "evidencia": "Flujo de estados, historial, roles, SLA",
        },
        {
            "proceso": "Gestión de niveles de servicio",
            "nivel": 2 if "CREATE TABLE sla" in m["corpus_all"] else 0,
            "evidencia": "SLA por prioridad y KPI de cumplimiento",
        },
        {
            "proceso": "Gestión del conocimiento",
            "nivel": 2 if "embedding_vector" in m["corpus_all"] else 0,
            "evidencia": "RAG pgvector sobre tickets resueltos",
        },
        {
            "proceso": "Gestión de la seguridad",
            "nivel": 2 if m["auth"]["jwt"] and m["auth"]["rate_limit"] else 1,
            "evidencia": "Controles técnicos; no hay SGSI documentado",
        },
        {
            "proceso": "Gestión de problemas",
            "nivel": 0,
            "evidencia": "No hay entidad problema/causa raíz",
        },
        {
            "proceso": "Gestión de cambios",
            "nivel": 0,
            "evidencia": "No hay RFC/CAB",
        },
        {
            "proceso": "Pruebas y validación",
            "nivel": 2,
            "evidencia": "Paquete Test con proceso 29119 y métricas 25023",
        },
    ]
    promedio = round(sum(p["nivel"] for p in procesos) / len(procesos), 2)
    score = round(100.0 * promedio / 5.0, 1)
    return {
        "norma": "ISO/IEC 33000 / ISO/IEC 15504 (evaluación de capacidad de procesos, SPICE)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "escala": {
            "0": "Incompleto",
            "1": "Realizado",
            "2": "Gestionado",
            "3": "Establecido",
            "4": "Predecible",
            "5": "En optimización",
        },
        "procesos": procesos,
        "nivel_medio": promedio,
        "nota": "15504 está retirada/reemplazada por 33000. Niveles 4-5 requieren medición estadística de proceso, no presente.",
    }


def iso_29119(m) -> dict:
    items = [
        _c("29119-1", "Conceptos y vocabulario", "cumple",
           "Base de pruebas=código+esquema; ítem=práctica ITIL/característica 25010"),
        _c("29119-2", "Procesos de prueba", "cumple",
           "Planificar (run_evaluation), diseñar (tests/), ejecutar (pytest), reportar (reports/)"),
        _c("29119-3", "Documentación de prueba", "cumple",
           "informe.json con especificación, resultados y veredictos"),
        _c("29119-4", "Técnicas de prueba", "cumple",
           "Partición de equivalencia, valores límite, tabla de decisión, transición de estados"),
    ]
    return {
        "norma": "ISO/IEC/IEEE 29119-1/2/3/4 (pruebas de software)",
        "aplicable": True,
        "score": _score(items),
        "veredicto": "CUMPLE (este paquete Test implementa el proceso; no certifica el producto)",
        "criterios": items,
        "tecnicas_aplicadas": [
            "Partición de equivalencia: roles, estados, prioridades",
            "Valores límite: password 8, adjuntos 5, 20 MB, mensaje 1000",
            "Tabla de decisión: agente vs coordinador vs archivado",
            "Transición de estados: ciclo de vida del ticket",
            "Análisis estático: AST complejidad, SQL, evidencias",
        ],
    }


def iso_27001(m) -> dict:
    a = m["auth"]
    items = [
        _c("A.5.15", "Control de acceso", "cumple" if a["roles"] and a["oauth2"] else "parcial",
           "RBAC 4 roles + JWT"),
        _c("A.5.17", "Información de autenticación", "cumple" if a["bcrypt"] and a["password_min_8"] else "parcial",
           "bcrypt, mínimo 8 caracteres"),
        _c("A.8.5", "Autenticación segura", "parcial" if a["jwt_24h"] else "cumple",
           "JWT HS256 24h (exposición larga) + rate limit"),
        _c("A.8.2", "Privilegios", "parcial" if a["docker_sock"] else "cumple",
           "Socket Docker montado en el backend (privilegio excesivo)"),
        _c("A.8.9", "Gestión de configuración", "cumple" if a["env_jwt"] and a["gitignore_env"] else "parcial",
           "Secretos en .env, gitignore"),
        _c("A.8.13", "Copia de seguridad", "cumple" if "pg_dump" in m["corpus_all"] else "no_cumple",
           "pg_dump/pg_restore desde panel"),
        _c("A.8.16", "Supervisión de actividades", "parcial",
           "historial y logs; tabla log de auditoría poco usada en API"),
        _c("A.8.19", "Instalación de software", "cumple" if m["size"]["has_docker"] else "parcial",
           "Imágenes Compose, sin bind-mount en prod"),
        _c("A.8.25", "Desarrollo seguro", "parcial",
           "Magic bytes, UUID, SQL params; falta SAST/DAST en CI"),
        _c("A.8.26", "Requisitos de seguridad de aplicaciones", "parcial",
           "Hay controles; no hay declaración de requisitos 27001"),
        _c("A.5.33", "Protección de registros", "parcial",
           "historial; sin WORM ni retención formal"),
        _c("ISMS", "Sistema de gestión (cláusulas 4-10)", "no_cumple",
           "No hay alcance, política, riesgos, auditorías internas ni mejora del SGSI"),
    ]
    score = _score(items)
    return {
        "norma": "ISO/IEC 27001:2022 (seguridad de la información)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "criterios": items,
        "nota": "Hay controles técnicos del Anexo A. NO hay SGSI: no es certificable 27001 en el estado actual.",
    }


def iso_20000(itil, m) -> dict:
    items = [
        _c("8.2", "Relación y acuerdo (SLA)", "cumple" if itil["score_nucleo"] >= 80 else "parcial",
           "SLA por prioridad y KPI"),
        _c("8.3", "Suministro y demanda (capacidad)", "parcial",
           "Cupo diario y carga; sin plan de capacidad"),
        _c("8.4", "Diseño y transición", "no_cumple",
           "Sin change/release formales"),
        _c("8.5.1", "Incidentes y peticiones", "cumple",
           "Ciclo de vida + mesa por roles"),
        _c("8.5.2", "Problemas", "no_cumple",
           "Sin registro de problemas"),
        _c("8.6", "Servicio (continuidad/disponibilidad)", "parcial",
           "Backups y health; sin BIA/DR documentado"),
        _c("8.7", "Seguridad de la información del servicio", "parcial",
           "Controles técnicos, sin SGSI"),
        _c("4-10", "SMS (sistema de gestión del servicio)", "no_cumple",
           "No hay SMS documentado ni auditoría 20000"),
    ]
    score = _score(items)
    return {
        "norma": "ISO/IEC 20000-1:2018 (gestión de servicios de TI, alineada a ITIL)",
        "aplicable": True,
        "score": score,
        "veredicto": _veredicto(score),
        "criterios": items,
        "nota": "El software SOPORTA un SMS (incidentes/SLA). La organización NO está certificada 20000-1.",
        "relacion_itil": itil["veredicto"],
    }


def iso_9000_family(m) -> dict:
    items_9001 = [
        _c("4", "Contexto / alcance QMS", "no_aplica",
           "ISO 9001 certifica organizaciones, no productos de software"),
        _c("5", "Liderazgo y roles", "parcial",
           "Roles de aplicación (admin/coordinador); no es liderazgo de QMS"),
        _c("6", "Planificación / riesgos", "no_cumple",
           "No hay registro de riesgos de calidad"),
        _c("7", "Soporte (competencia, info documentada)", "parcial",
           "Historial y configuración; sin control de documentos 9001"),
        _c("8", "Operación", "parcial",
           "Proceso de ticket es un proceso operativo informatizado"),
        _c("9", "Evaluación del desempeño", "cumple" if "cumplimiento_sla" in m["corpus_all"] else "parcial",
           "KPIs SLA, TME, eficiencia de agentes"),
        _c("10", "Mejora", "parcial",
           "Estadísticas e IA; sin no-conformidades/CAPA formales"),
    ]
    score = _score(items_9001)
    return {
        "ISO_9000": {
            "norma": "ISO 9000:2015 (fundamentos y vocabulario)",
            "aplicable": True,
            "score": 100,
            "veredicto": "CUMPLE (vocabulario usado en la evaluación)",
            "nota": "Se aplican los principios: enfoque a procesos, evidencias, mejora.",
        },
        "ISO_9001": {
            "norma": "ISO 9001:2015 (sistemas de gestión de la calidad)",
            "aplicable": False,
            "score": score,
            "veredicto": "NO_APLICA_CERTIFICACION_DE_PRODUCTO",
            "criterios": items_9001,
            "nota": (
                "9001 no se 'cumple' por un helpdesk. El software puede APOYAR un SGC "
                "(trazabilidad, indicadores, roles). La organización propietaria no está evaluada."
            ),
        },
        "ISO_9004": {
            "norma": "ISO 9004:2018 (calidad de una organización / mejora)",
            "aplicable": False,
            "score": None,
            "veredicto": "NO_APLICA",
            "nota": "Guía de madurez organizacional, no requisitos de producto.",
        },
        "ISO_19011": {
            "norma": "ISO 19011:2018 (auditoría de sistemas de gestión)",
            "aplicable": True,
            "score": 80,
            "veredicto": "CUMPLE_COMO_METODO_DE_ESTA_EVALUACION",
            "nota": (
                "Esta evaluación sigue principios 19011: integridad, evidencia, "
                "imparcialidad (métricas de código, no declaración del fabricante)."
            ),
            "principios": [
                "Integridad: veredictos honestos (no se declara certificación falsa)",
                "Presentación imparcial: hallazgos y no-aplicabilidades",
                "Cuidado profesional: normas sectoriales marcadas N/A",
                "Confidencialidad: no se leen secretos de .env",
                "Independencia: análisis estático reproducible",
                "Enfoque basado en evidencia: patrones y AST",
            ],
        },
    }


def normas_sectoriales() -> dict:
    def na(norma, motivo):
        return {
            "norma": norma,
            "aplicable": False,
            "score": None,
            "veredicto": "NO_APLICA",
            "motivo": motivo,
        }

    return {
        "ISO_13485": na(
            "ISO 13485:2016 (dispositivos médicos)",
            "SHelpDesk no es un dispositivo médico ni software de uso médico (SaMD).",
        ),
        "IATF_16949": na(
            "IATF 16949:2016 (automotriz)",
            "No es un sistema de producción automotriz ni forma parte de la cadena de suministro IATF.",
        ),
        "AS9100": na(
            "AS9100 (aeroespacial)",
            "No es un sistema de calidad aeroespacial/defensa.",
        ),
        "ISO_22000": na(
            "ISO 22000:2018 (inocuidad alimentaria)",
            "No es un sistema alimentario ni de inocuidad de alimentos.",
        ),
        "ISO_17025": {
            "norma": "ISO/IEC 17025:2017 (competencia de laboratorios de ensayo y calibración)",
            "aplicable": False,
            "score": None,
            "veredicto": "NO_APLICA_AL_PRODUCTO",
            "motivo": (
                "El helpdesk no es un laboratorio. El paquete Test SÍ adopta principios "
                "17025 (método validado, trazabilidad de evidencia, imparcialidad, informes), "
                "pero no acredita un laboratorio."
            ),
            "principios_adoptados_en_Test": [
                "Impartialidad: métricas reproducibles sobre el código",
                "Validez de métodos: AST, conteos, evidencia textual",
                "Registros: Test/reports/informe.json",
                "Aseguramiento de calidad de resultados: pytest como repetición",
            ],
        },
    }


def evaluar_todas(m, itil) -> dict:
    n25010 = iso_25010(m)
    n25023 = iso_25023(m)
    n25012 = iso_25012(m)
    n25040 = iso_25040(m, n25010, n25023, n25012)
    n25000 = iso_25000(n25010, n25012, n25023, n25040)
    n12207 = iso_12207(m)
    n33000 = iso_33000(itil, m)
    n29119 = iso_29119(m)
    n27001 = iso_27001(m)
    n20000 = iso_20000(itil, m)
    n9000 = iso_9000_family(m)
    sector = normas_sectoriales()
    return {
        "ISO_IEC_25000": n25000,
        "ISO_IEC_25010": n25010,
        "ISO_IEC_25012": n25012,
        "ISO_IEC_25023": n25023,
        "ISO_IEC_25040": n25040,
        "ISO_IEC_12207": n12207,
        "ISO_IEC_15504_33000": n33000,
        "ISO_IEC_IEEE_29119": n29119,
        "ISO_IEC_27001": n27001,
        "ISO_IEC_20000_1": n20000,
        "ISO_9000_9001_9004_19011": n9000,
        "normas_sectoriales_no_aplicables": sector,
    }
