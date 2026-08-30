#!/usr/bin/env bash
# ============================================
# iniciar.sh — SHelpDesk Microsoft
# Monta toda la infraestructura del proyecto de un tirón:
#   PostgreSQL (pgvector) + Ollama + n8n + Backend FastAPI + Streamlit
# Uso:
#   chmod +x iniciar.sh
#   ./iniciar.sh
# ============================================
set -u

# Colores
CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; GREEN='\033[0;32m'; GRAY='\033[0;90m'; NC='\033[0m'

say()  { echo -e "${CYAN}${1}${NC}"; }
warn() { echo -e "${YELLOW}${1}${NC}"; }
err()  { echo -e "${RED}${1}${NC}"; }
ok()   { echo -e "${GREEN}${1}${NC}"; }
dim()  { echo -e "${GRAY}${1}${NC}"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

echo ""
say "🚀 Iniciando HelpDesk (Contenedores + Backend)..."

# ============================================
# 0. REQUISITOS PREVIOS (Docker + .env)
# ============================================
if ! command -v docker >/dev/null 2>&1; then
    err "❌ Docker no está instalado o no está en el PATH."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    err "❌ El demonio de Docker no está corriendo. Arranca Docker y vuelve a intentarlo."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    err "❌ No se encontró el plugin 'docker compose'. Instala Docker Compose v2."
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    err "❌ No se encontró docker-compose.yml en: $COMPOSE_FILE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    err "❌ No se encontró el archivo .env en: $ENV_FILE"
    warn "   Es obligatorio: contiene las credenciales (POSTGRES_*, JWT_SECRET_KEY, N8N_*)."
    exit 1
fi

faltan=""
for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB JWT_SECRET_KEY N8N_BASIC_AUTH_USER N8N_BASIC_AUTH_PASSWORD; do
    grep -qE "^[[:space:]]*${var}[[:space:]]*=" "$ENV_FILE" || faltan="$faltan $var"
done
if [ -n "$faltan" ]; then
    err "❌ Faltan variables obligatorias en .env:$faltan"
    exit 1
fi

# Usuario de PostgreSQL leído del .env (por si no es 'postgres')
PG_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d ' \t\r\"')"
PG_USER="${PG_USER:-postgres}"

# ============================================
# 1. DOCKER COMPOSE - Construir y levantar TODO
# ============================================
say "🐳 Construyendo y levantando contenedores (postgres, ollama, n8n, backend, streamlit)..."
docker compose -f "$COMPOSE_FILE" up -d --build
if [ $? -ne 0 ]; then
    err "❌ Error al iniciar los contenedores"
    exit 1
fi

# ============================================
# 2. Esperar a que PostgreSQL esté listo
# ============================================
say "⏳ Esperando a que PostgreSQL esté disponible..."
max_attempts=30
attempt=0
pg_ready=false
while [ "$pg_ready" = false ] && [ "$attempt" -lt "$max_attempts" ]; do
    attempt=$((attempt + 1))
    sleep 2
    if docker exec helpdesk-db pg_isready -U "$PG_USER" >/dev/null 2>&1; then
        pg_ready=true
        break
    fi
    dim "   Intento $attempt/$max_attempts - PostgreSQL aún no está listo..."
done

if [ "$pg_ready" = false ]; then
    err "❌ PostgreSQL no respondió después de $((max_attempts * 2)) segundos"
    warn "📋 Revisa los logs con: docker logs helpdesk-db"
    exit 1
fi

ok "✅ PostgreSQL está listo y aceptando conexiones"

# ============================================
# 3. HEALTH CHECKS (no fatales)
# ============================================
wait_http_ok() {
    # $1 = url  $2 = nombre  $3 = intentos
    if ! command -v curl >/dev/null 2>&1; then
        warn "   (curl no disponible: se omite la espera activa de $2)"
        return 0
    fi
    local url="$1" nombre="$2" intentos="${3:-30}" i=0 code
    while [ "$i" -lt "$intentos" ]; do
        i=$((i + 1))
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || true)"
        if [ "$code" = "200" ]; then
            return 0
        fi
        dim "   Intento $i/$intentos - $nombre aún no responde..."
        sleep 2
    done
    return 1
}

say "⏳ Esperando al backend (FastAPI :8000)..."
if wait_http_ok "http://localhost:8000/api/health" "Backend"; then
    ok "✅ Backend respondiendo en :8000"
else
    warn "⚠️ El backend no respondió a tiempo; revisa: docker logs helpdesk-backend"
fi

say "⏳ Esperando a Streamlit (:8501)..."
if wait_http_ok "http://localhost:8501" "Streamlit"; then
    ok "✅ Streamlit respondiendo en :8501"
else
    warn "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit"
fi

# ============================================
# 4. RESUMEN
# ============================================
say "📊 Estado de los servicios Docker:"
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

ok "✅ Infraestructura de SHelpDesk levantada"
dim "   Backend API : http://localhost:8000  (docs: http://localhost:8000/docs)"
dim "   Streamlit   : http://localhost:8501"
dim "   n8n         : http://localhost:5678"
dim "   Ollama      : http://localhost:11434"
dim "   PostgreSQL  : localhost:5432 (usuario: $PG_USER)"
warn "📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-streamlit"
echo ""
