# SHelpDesk

**Mesa de ayuda (service desk) con clasificación automática por IA y búsqueda semántica (RAG) sobre su propio histórico de tickets. Self-hosted, privado y ejecutable en hardware de consumo.**

SHelpDesk es un sistema de gestión de incidencias TI orientado a equipos de soporte. Combina un flujo de tickets clásico (alta, asignación, seguimiento por estados, SLA y archivado) con una capa de inteligencia artificial que corre **localmente**: clasifica cada ticket nuevo, responde consultas del personal de soporte y **aprende de los tickets resueltos** para sugerir soluciones.

El objetivo de diseño es claro: obtener las ventajas de un helpdesk asistido por IA **sin enviar datos de la empresa a servicios de terceros** ni depender de APIs de pago.

---

## Tabla de contenidos

- [Descripción general](#descripción-general)
- [Características principales](#características-principales)
- [Qué nos diferencia](#qué-nos-diferencia)
- [Retos encontrados](#retos-encontrados)
- [Arquitectura](#arquitectura)
- [Stack tecnológico](#stack-tecnológico)
- [Puesta en marcha](#puesta-en-marcha)
- [Seguridad](#seguridad)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Documentación extendida](#documentación-extendida)
- [Estado del proyecto](#estado-del-proyecto)

---

## Descripción general

SHelpDesk cubre el ciclo completo de una incidencia: un **solicitante** abre un ticket; el sistema lo **clasifica con IA** (categoría, prioridad y nivel de confianza); un **coordinador** lo asigna a un **agente** respetando un cupo diario; y el agente lo resuelve sobre un tablero Kanban. Cuando un ticket se resuelve o cierra, se **indexa en un motor de búsqueda semántica** que después permite al equipo reutilizar ese conocimiento.

Todo el sistema es **autoalojado**: frontend estático, backend, base de datos, motor de IA y automatizaciones viven en infraestructura propia, y la IA se ejecuta en una GPU local mediante Ollama.

---

## Características principales

### Gestión de tickets
- **Tablero Kanban** con estados `nuevo`, `asignado`, `en_proceso`, `escalado`, `resuelto`, `cerrado` y `archivado` (estado terminal que retira el ticket del tablero sin borrar datos ni historial).
- **Alta de tickets** con asunto, descripción, categoría y prioridad, más **adjuntos** (PNG/JPG) con validación real del contenido.
- **Historial de auditoría** de cada cambio de estado (quién, cuándo, de qué estado a cuál).
- **Vista de detalle** con datos del solicitante, agente asignado, análisis IA e historial.
- **SLA** por prioridad (tiempo de respuesta y de solución) y **reportes** exportables.
- **Archivado** de tickets completados como forma de limpieza, conservando datos y conocimiento.

### IA y gestión del conocimiento
- **Clasificación automática de tickets**: al crearse un ticket, un flujo de n8n consulta al modelo local y estima categoría, prioridad y confianza, devolviendo el resultado al backend.
- **RAG (Retrieval-Augmented Generation)**: los tickets resueltos/cerrados se indexan como vectores (embeddings `bge-m3`, 1024 dimensiones) en PostgreSQL con **pgvector** e índice **HNSW** de similitud coseno. El equipo busca por significado ("impresora atascada") y reutiliza soluciones.
- **Chat IA de soporte** para agentes, coordinadores y administradores, con contexto del ticket cuando aplica.
- **Contexto operacional en vivo**: para coordinadores y administradores, el chat IA recibe un resumen real de la operación (tickets por estado, carga por agente vs. cupo, categorías más reportadas, críticos sin resolver) con caché de corta duración.

### Coordinación y operación
- **Asignación asistida** con cola de tickets, recomendación por IA y **cupo diario configurable por agente**.
- **Balanceo** de carga y control de sobrecarga.
- **Estadísticas** de tickets, categorías, prioridades, tiempos y desempeño por agente.
- **Chat global** del equipo (todos los roles) con control de flood.

### Administración
- **Panel web de administración** (integrado en el frontend) y **panel de analítica** (Streamlit) con control total.
- **Gestión de usuarios y roles** con ascensos temporales a administrador (auto-degradación al vencer), activación/desactivación, restablecimiento de contraseñas y **protección anti-encierro** (no se puede eliminar ni degradar al último administrador).
- **Respaldos de base de datos** (`pg_dump`/`pg_restore`) con creación, descarga, restauración y borrado desde el panel.
- **Logs de contenedores** y **consola SQL** (con usuario de mínimo privilegio).
- **Gestión de modelos IA**: listado, cambio de modelo activo, ajuste de parámetros de generación (temperatura, longitud, top-p) y descarga de modelos.
- **Gestión de workflows de n8n** (listar, activar/desactivar) desde el panel del administrador.

### Seguridad
- **Autenticación JWT revalidada contra la base de datos** (rol y estado vigentes en cada petición; desactivar o degradar una cuenta surte efecto de inmediato).
- **MFA (TOTP)** opcional por usuario, con código de segundo factor en el login.
- **Control de acceso por rol** y por pertenencia (un agente solo accede a sus tickets asignados; el solicitante, a los suyos).
- **Rate limiting** en login, registro y chats.
- **Endurecimiento**: adjuntos servidos por endpoint autenticado, subida por streaming con límite, cabeceras CSP/HSTS en el frontend, auditoría append-only y aislamiento de servicios.

### Despliegue
- **Docker Compose** con servicios independientes y healthchecks.
- **Frontend estático** desplegable en cualquier CDN (Vercel usado en producción).
- **Exposición del backend** mediante **Cloudflare Tunnel** (conexión saliente, sin abrir puertos) o cualquier reverse proxy.
- **Aceleración por GPU** para el motor de IA.

---

## Qué nos diferencia

| Aspecto | SHelpDesk | Helpdesk "típico" en la nube |
| --- | --- | --- |
| Privacidad de datos | IA **local**; los tickets no salen de tu infraestructura | Datos y prompts enviados a APIs de terceros |
| Coste de IA | Sin coste por token; corre en GPU propia | Suscripción / pago por uso |
| Conocimiento | **RAG sobre tu propio histórico** de tickets resueltos | Base de conocimiento manual |
| Clasificación | **Automática** (categoría/prioridad/confianza) | Manual o de pago |
| Automatizaciones | **n8n** editable y autoalojado | Limitadas al proveedor |
| Control total | Acceso a BD, respaldos, logs y modelos desde el panel | Caja negra gestionada por el proveedor |
| Modelo operativo | Cupo diario por agente, asignación asistida, SLA | Genérico |
| Hardware | Funciona en **hardware de consumo** (GPU de 12 GB) | — |

En una frase: **privacidad de la IA local + conocimiento que se acumula solo + control administrativo total, en una arquitectura ligera y autoalojada.**

---

## Retos encontrados

- **Conectar un backend local con un frontend en la nube.** El navegador bloquea llamadas directas a direcciones privadas (Local Network Access de Chrome), y un túnel cuya DNS falla de forma intermitente rompía el login. Se resolvió con un **rewrite de Vercel** (mismo origen) hacia un hostname fijo publicado por **Cloudflare Tunnel**.
- **Consistencia del RAG.** Garantizar la dimensión correcta de los embeddings (1024) y **no mezclar modelos** en la misma columna vectorial, además de mantener el índice HNSW alineado.
- **Integración con n8n 2.x.** Cambios de API (activación por endpoints dedicados en lugar de `PATCH`), autenticación del callback del backend mediante credencial de cabecera, y **aislar n8n en su propia base de datos y usuario**.
- **Validación de archivos subidos.** Verificar el contenido real (magic bytes), limitar el tamaño sin cargar el archivo entero en memoria y evitar rutas maliciosas.
- **Construir la base de datos de forma reproducible.** Esquema, migraciones idempotentes, roles de mínimo privilegio y datos semilla coherentes.
- **Endurecer la seguridad de forma progresiva.** Corregir accesos indebidos entre agentes, hacer revocables los tokens, eliminar el acceso directo al socket de Docker y añadir cabeceras y controles anti-XSS.
- **Aceleración por GPU en Docker.** Habilitar la GPU NVIDIA para Ollama (runtime, dispositivos) y confirmar que el modelo se carga realmente en CUDA.

---

## Arquitectura

```
┌───────────────────────────────────────┐
│  Frontend (HTML + CSS + JS)           │
│  Desplegado como sitio estático       │
└──────────────────┬────────────────────┘
                   │  rewrite /api/*  (mismo origen, sin CORS)
                   v
┌───────────────────────────────────────┐
│  Cloudflare Tunnel                    │
│  api.<dominio>  ->  backend:8000      │
└──────────────────┬────────────────────┘
                   │
                   v
┌──────────────────────────────────────────────────────────────┐
│  Docker (host o servidor propio)                              │
│                                                               │
│   backend (FastAPI)      streamlit (panel admin/analitica)    │
│   postgres + pgvector    ollama (modelos, GPU)                │
│   n8n (automatizacion)   docker-socket-proxy (solo lectura)   │
└──────────────────────────────────────────────────────────────┘

Flujo de IA:
  ticket nuevo ──> n8n (webhook) ──> Ollama (clasifica)
        ──> n8n (callback con cabecera de autenticacion) ──> backend

Flujo de RAG:
  ticket resuelto/cerrado ──> embeddings (bge-m3) ──> pgvector (HNSW)
        <── busqueda semantica del equipo <──
```

---

## Stack tecnológico

| Capa | Tecnología |
| --- | --- |
| Frontend | HTML, CSS y JavaScript (sin framework) |
| Backend | Python 3.12 + FastAPI (async), SQLAlchemy, Pydantic |
| Base de datos | PostgreSQL 16 + pgvector |
| IA / LLM | Ollama (`llama3.2:3b` para generación, `bge-m3` para embeddings) |
| Automatización | n8n 2.x |
| Panel de analítica | Streamlit + Plotly + pandas |
| Autenticación | JWT (HS256), bcrypt, TOTP (MFA) |
| Contenedores | Docker + Docker Compose |
| Exposición pública | Cloudflare Tunnel |
| Hosting del frontend | Vercel (o cualquier CDN estático) |

---

## Puesta en marcha

> [!IMPORTANT]
> El proyecto requiere Docker y, para la IA local, **GPU NVIDIA** (opcional pero muy recomendable). Sin GPU, Ollama usa CPU y las respuestas son mucho más lentas.

> [!NOTE]
> Los archivos de entorno (`.env`) y la carpeta de base de datos (`database/`) **no se versionan** por seguridad. Hay que aportarlos en el destino (por canal seguro) o generarlos de nuevo.

Pasos de alto nivel:

1. Clonar el repositorio.
2. Crear el archivo `.env` con las claves necesarias (ver la sección [Documentación extendida](#documentación-extendida)).
3. Ejecutar el arranque de la infraestructura (script de inicio idempotente).
4. Descargar los modelos de IA.
5. Publicar el backend (túnel o proxy) y apuntar el frontend a su API.
6. Verificar el flujo completo y activar MFA en las cuentas privilegiadas.

---

## Seguridad

> [!WARNING]
> Antes de exponer el sistema en producción: cambia las contraseñas de las cuentas de prueba, activa MFA en administradores y coordinadores, y revisa las reglas de firewall y del túnel. El acceso a la API está protegido por JWT, pero el sistema es público por diseño.

Garantías del diseño actual:

- Tokens revocables en la práctica (revalidación contra la base de datos).
- Control de acceso por rol y por pertenencia al recurso.
- Archivos adjuntos servidos solo a usuarios con acceso al ticket.
- Base de datos de la aplicación con usuario de mínimo privilegio y tablas de auditoría append-only.
- Servicios internos (base de datos, motor de IA, n8n, panel) accesibles únicamente desde el host.
- Backend sin acceso directo al socket de Docker (solo un proxy de lectura para logs).

---

## Estructura del repositorio

| Ruta | Contenido |
| --- | --- |
| `backend/` | API FastAPI (autenticación, tickets, chat IA, coordinación, adjuntos) |
| `frontend/` | Frontend estático (páginas por rol, estilos y scripts) |
| `streamlit_app/` | Panel de analítica y control administrativo |
| `AIEngine/` | Plantillas de workflows de n8n (importables) |
| `database/` | Esquema, migraciones y datos semilla (no versionado) |
| `docker/` | Archivos Docker Compose y configuración de proxy |
| `Iniciar.ps1` / `iniciar.sh` | Arranque de la infraestructura (Windows / Linux) |

---

## Documentación extendida

> **Documentación extendida**:
>
> [!NOTE]
> **Arranque y operación diaria.** Scripts de inicio idempotentes que levantan la infraestructura, aplican el esquema y migraciones, configuran roles de base de datos y cargan los datos semilla.
>
> [!TIP]
> **Variables de entorno.** El archivo `.env` centraliza todos los secretos (credenciales de base de datos, firma de tokens, claves de callback de IA, token del túnel). Genera valores fuertes y transfiérelos por canal seguro.
>
> [!IMPORTANT]
> **IA local y RAG.** Regla de oro: no mezclar modelos de embeddings en la misma columna vectorial. Si cambias de modelo, ajusta la dimensión, recrea el índice HNSW y reindexa.
>
> [!WARNING]
> **n8n.** La autenticación del callback del backend se realiza mediante una credencial de cabecera; no incrustes la clave en el workflow. n8n usa su propia base de datos y usuario.
>
> [!NOTE]
> **Respaldos.** El panel de administración permite crear, descargar, restaurar y eliminar respaldos de la base de datos. Automatízalos con el programador de tareas del sistema.
>
> [!TIP]
> **Roles.** Solicitante, agente, coordinador y administrador. El cupo diario de asignación por agente y los parámetros de generación de IA son configurables.

---

## Estado del proyecto

Proyecto en desarrollo activo. La arquitectura, la seguridad y la integración de IA se han ido endureciendo conforme se detectaban y resolvían problemas reales de despliegue y de seguridad.

Para detalles de operación, accesos, comandos y guías de despliegue en otra máquina o servidor, consulta el runbook interno del proyecto.
