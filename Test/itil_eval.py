from scan import evidence_level, has_any

CORE = "nucleo_mesa_servicio"
COMPLEMENTARIA = "complementaria"
FUERA_ALCANCE = "fuera_de_alcance_tipico"


PRACTICAS_ITIL4 = [
    {
        "id": "incident_management",
        "nombre": "Gestión de incidentes",
        "grupo": CORE,
        "patrones": [
            "ESTADOS_TICKET",
            "escalado",
            "INSERT INTO historial",
            "create_ticket",
            "en_proceso",
            "resuelto",
        ],
        "esperado": "Un helpdesk ITIL debe registrar, clasificar, asignar, escalar, resolver y cerrar incidentes con historial.",
    },
    {
        "id": "service_request",
        "nombre": "Gestión de peticiones de servicio",
        "grupo": CORE,
        "patrones": [
            "formulario-ticket",
            "id_categoria",
            "solicitante",
            "CREATE TABLE solicitud",
        ],
        "esperado": "El usuario reporta solicitudes/incidentes por canal formal con categoría y prioridad.",
    },
    {
        "id": "service_desk",
        "nombre": "Mesa de servicio",
        "grupo": CORE,
        "patrones": [
            "dashboard-agente",
            "dashboard-coordinador",
            "dashboard-solicitante",
            "dashboard-admin",
        ],
        "esperado": "Punto único de contacto con vistas por rol.",
    },
    {
        "id": "service_level",
        "nombre": "Gestión de niveles de servicio (SLA)",
        "grupo": CORE,
        "patrones": [
            "CREATE TABLE sla",
            "tiempo_solucion_min",
            "cumplimiento_sla",
            "tiempo_respuesta_min",
            "/sla",
        ],
        "esperado": "SLA por prioridad, medición de cumplimiento y configuración.",
    },
    {
        "id": "knowledge",
        "nombre": "Gestión del conocimiento",
        "grupo": CORE,
        "patrones": [
            "embedding_vector",
            "indexar_ticket",
            "search_rag",
            "bge-m3",
        ],
        "esperado": "Reutilización de soluciones (RAG sobre tickets resueltos).",
    },
    {
        "id": "measurement",
        "nombre": "Medición e informes",
        "grupo": CORE,
        "patrones": [
            "get_estadisticas",
            "cumplimiento_sla",
            "tiempo_medio",
            "get_reportes",
        ],
        "esperado": "KPIs operativos y reportes filtrados.",
    },
    {
        "id": "monitoring",
        "nombre": "Supervisión y gestión de eventos",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "health_check",
            "/logs/",
            "docker_api",
        ],
        "esperado": "Salud de servicios, logs y observabilidad.",
    },
    {
        "id": "continual_improvement",
        "nombre": "Mejora continua",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "clasificacion_ia",
            "confianza",
            "vista_estadisticas_agentes",
            "revision_manual",
        ],
        "esperado": "Uso de datos e IA para mejorar clasificación y rendimiento.",
    },
    {
        "id": "information_security",
        "nombre": "Gestión de la seguridad de la información",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "OAuth2PasswordBearer",
            "bcrypt",
            "SlidingWindowLimiter",
            "JWT_SECRET_KEY",
        ],
        "esperado": "Controles técnicos de autenticación, cifrado de secretos y abuso.",
    },
    {
        "id": "deployment",
        "nombre": "Gestión de implantación",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "docker-compose",
            "docker-compose.prod.yml",
            "healthcheck",
        ],
        "esperado": "Despliegue reproducible (dev/prod) con salud.",
    },
    {
        "id": "capacity",
        "nombre": "Gestión de capacidad y rendimiento",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "carga_trabajo",
            "MAX_TICKETS_AGENTE_DIA",
            "asignados_hoy",
        ],
        "esperado": "Control de carga de agentes y cupo diario.",
    },
    {
        "id": "continuity",
        "nombre": "Continuidad del servicio",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "pg_dump",
            "pg_restore",
            "crear_respaldo",
            "db_backups",
        ],
        "esperado": "Respaldos y restauración de la BD.",
    },
    {
        "id": "workforce",
        "nombre": "Gestión de personal y talento (soporte)",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "especialidad",
            "permisos_supervision",
            "cambiar_rol",
            "nivel_jerarquia",
        ],
        "esperado": "Roles, especialidad, permisos y jerarquía.",
    },
    {
        "id": "availability",
        "nombre": "Gestión de la disponibilidad",
        "grupo": COMPLEMENTARIA,
        "patrones": [
            "restart:",
            "health_check",
            "healthcheck",
        ],
        "esperado": "Reinicio automático y comprobaciones de salud.",
    },
    {
        "id": "problem_management",
        "nombre": "Gestión de problemas",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE problema",
            "causa_raiz",
            "error_conocido",
            "known_error",
        ],
        "esperado": "Registro de problemas, causa raíz y errores conocidos (no tickets).",
    },
    {
        "id": "change_enablement",
        "nombre": "Habilitación del cambio",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE cambio",
            "CAB",
            "change_advisory",
            "ventana_cambio",
        ],
        "esperado": "RFC, evaluación de riesgo y aprobación de cambios.",
    },
    {
        "id": "configuration",
        "nombre": "Gestión de la configuración (CMDB)",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE ci ",
            "cmdb",
            "elemento_configuracion",
            "configuration_item",
        ],
        "esperado": "Inventario de CIs y relaciones.",
    },
    {
        "id": "release",
        "nombre": "Gestión de versiones",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE release",
            "release_management",
            "versionado_servicio",
        ],
        "esperado": "Plan de release y paquete de versión.",
    },
    {
        "id": "asset",
        "nombre": "Gestión de activos de TI",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE activo",
            "it_asset",
            "inventario_hardware",
        ],
        "esperado": "Ciclo de vida de activos TI.",
    },
    {
        "id": "catalogue",
        "nombre": "Gestión del catálogo de servicios",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE catalogo_servicio",
            "service_catalogue",
            "oferta_servicio",
        ],
        "esperado": "Catálogo publicado de servicios.",
    },
    {
        "id": "supplier",
        "nombre": "Gestión de proveedores",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE proveedor",
            "supplier_management",
        ],
        "esperado": "Contratos y proveedores.",
    },
    {
        "id": "financial",
        "nombre": "Gestión financiera de servicios",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE coste",
            "chargeback",
            "presupuesto_ti",
        ],
        "esperado": "Coste y presupuestación del servicio.",
    },
    {
        "id": "risk",
        "nombre": "Gestión del riesgo",
        "grupo": FUERA_ALCANCE,
        "patrones": [
            "CREATE TABLE riesgo",
            "risk_register",
            "matriz_riesgo",
        ],
        "esperado": "Registro y tratamiento de riesgos.",
    },
]


def _estado(nivel: str, grupo: str) -> str:
    if grupo == FUERA_ALCANCE and nivel == "ninguna":
        return "no_implementada"
    if nivel == "completa":
        return "cumple"
    if nivel == "parcial":
        return "parcial"
    return "no_cumple"


def _puntos(estado: str, grupo: str) -> float:
    if estado == "cumple":
        return 1.0
    if estado == "parcial":
        return 0.5
    if estado == "no_implementada":
        return 0.0
    return 0.0


def evaluar(corpus_all: str) -> dict:
    resultados = []
    for p in PRACTICAS_ITIL4:
        nivel = evidence_level(corpus_all, p["patrones"])
        estado = _estado(nivel, p["grupo"])
        hits = [pat for pat in p["patrones"] if pat in corpus_all]
        resultados.append({
            "id": p["id"],
            "nombre": p["nombre"],
            "grupo": p["grupo"],
            "esperado": p["esperado"],
            "nivel_evidencia": nivel,
            "estado": estado,
            "evidencias": hits,
            "faltantes": [pat for pat in p["patrones"] if pat not in corpus_all],
            "puntos": _puntos(estado, p["grupo"]),
        })

    nucleo = [r for r in resultados if r["grupo"] == CORE]
    comp = [r for r in resultados if r["grupo"] == COMPLEMENTARIA]
    fuera = [r for r in resultados if r["grupo"] == FUERA_ALCANCE]

    def pct(items):
        if not items:
            return 0.0
        return round(100.0 * sum(i["puntos"] for i in items) / len(items), 1)

    score_nucleo = pct(nucleo)
    score_comp = pct(comp)
    score_producto = round(0.7 * score_nucleo + 0.3 * score_comp, 1)
    score_itil_completo = pct(resultados)

    if score_nucleo >= 80 and score_producto >= 70:
        veredicto = "CUMPLE ITIL como mesa de servicio (incidentes, peticiones, SLA, conocimiento, medición)"
        cumple_mesa = True
    elif score_nucleo >= 50:
        veredicto = "CUMPLE PARCIALMENTE ITIL (núcleo de mesa de servicio presente, prácticas avanzadas incompletas)"
        cumple_mesa = False
    else:
        veredicto = "NO CUMPLE el perfil ITIL de mesa de servicio"
        cumple_mesa = False

    return {
        "norma": "ITIL 4",
        "cumple_mesa_servicio": cumple_mesa,
        "cumple_itil_completo": False,
        "score_nucleo": score_nucleo,
        "score_complementarias": score_comp,
        "score_producto_helpdesk": score_producto,
        "score_itil4_34_practicas": score_itil_completo,
        "veredicto": veredicto,
        "nota": (
            "SHelpDesk está alineado con las prácticas ITIL de mesa de servicio. "
            "No es una implementación ITIL 4 completa ni un SGSI/SGSTI certificable: "
            "faltan Problemas, Cambios, CMDB, Activos, Catálogo, Proveedores y Riesgo."
        ),
        "practicas": resultados,
        "resumen": {
            "nucleo_ok": sum(1 for r in nucleo if r["estado"] == "cumple"),
            "nucleo_total": len(nucleo),
            "complementarias_ok": sum(1 for r in comp if r["estado"] in ("cumple", "parcial")),
            "complementarias_total": len(comp),
            "fuera_no_implementadas": sum(1 for r in fuera if r["estado"] == "no_implementada"),
            "fuera_total": len(fuera),
        },
        "tiene_chat_ia": has_any(corpus_all, ["chat_ai", "SYSTEM_PROMPT"]),
        "tiene_kanban": has_any(corpus_all, ["kanban", "ESTADOS_TICKET"]),
    }
