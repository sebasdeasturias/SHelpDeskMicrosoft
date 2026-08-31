#!/usr/bin/env bash
# ============================================
# iniciar.sh — SHelpDesk Microsoft
# Monta toda la infraestructura del proyecto de un tirón:
#   PostgreSQL (pgvector) + Ollama + n8n + Backend FastAPI + Streamlit
# Además monta la base de datos completa si no existe:
#   esquema (db_logic.sql) + rol de app (helpdesk_app) + usuarios de prueba (seed_usuarios.sql)
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
for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB APP_DB_USER APP_DB_PASSWORD AI_CALLBACK_KEY JWT_SECRET_KEY; do
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
# 1. DOCKER COMPOSE - Levantar servicios base
# ============================================
say "🐳 Levantando servicios base (postgres, ollama)..."
# Solo servicios base: n8n/backend/streamlit se levantan DESPUÉS de configurar la BD.
docker compose -f "$COMPOSE_FILE" up -d postgres ollama
if [ $? -ne 0 ]; then
    err "❌ Error al iniciar los contenedores base"
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

# Variables de la BD de la aplicación (leídas del .env)
SCHEMA_FILE="$PROJECT_ROOT/db_logic.sql"
SEED_FILE="$PROJECT_ROOT/seed_usuarios.sql"
APP_USER="$(grep -E '^APP_DB_USER=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d ' \t\r\"')"
APP_USER="${APP_USER:-helpdesk_app}"
APP_PASS="$(grep -E '^APP_DB_PASSWORD=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d ' \t\r\"')"
PG_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d ' \t\r\"')"
PG_DB="${PG_DB:-helpdesk_db}"

if [ -z "$APP_PASS" ]; then
    err "❌ APP_DB_PASSWORD está vacía en .env"
    exit 1
fi
if ! [[ "$APP_USER" =~ ^[a-z_][a-z0-9_]*$ ]] || ! [[ "$PG_DB" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    err "❌ APP_DB_USER y POSTGRES_DB deben ser solo minúsculas/números/guion bajo"
    exit 1
fi

# ============================================
# 2.5 ESQUEMA DE LA BD (db_logic.sql)
#     Se aplica solo si la BD está vacía (primera vez / volumen nuevo).
#     Va ANTES de los permisos para que el rol herede acceso a las tablas.
# ============================================
say "🗄️ Verificando esquema de la BD..."
schema_ok="$(docker exec helpdesk-db psql -tA -U "$PG_USER" -d "$PG_DB" \
    -c "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='usuarios'" 2>/dev/null || true)"
if [ "$schema_ok" != "1" ]; then
    if [ ! -f "$SCHEMA_FILE" ]; then
        err "❌ No se encontró db_logic.sql en: $SCHEMA_FILE"
        exit 1
    fi
    dim "   Esquema vacío; aplicando db_logic.sql..."
    cat "$SCHEMA_FILE" | docker exec -i helpdesk-db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" >/dev/null
    if [ $? -ne 0 ]; then
        err "❌ Error aplicando db_logic.sql"
        exit 1
    fi
    ok "✅ Esquema (db_logic.sql) aplicado"
else
    ok "✅ El esquema ya existe; no se toca"
fi

# ============================================
# 2.6 USUARIO DE BD DE LA APLICACIÓN (mínimo privilegio)
#     docker-compose solo inyecta APP_DB_USER/APP_DB_PASSWORD al backend;
#     el rol debe existir dentro de PostgreSQL. Idempotente.
# ============================================
say "👤 Configurando el usuario de BD de la aplicación..."

# Escapar comillas simples del password para el literal SQL (' -> '')
q="'"
APP_PASS_ESC="${APP_PASS//$q/$q$q}"

SQL="$(cat <<'SQLEOF'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__USER__') THEN
    CREATE ROLE __USER__ LOGIN PASSWORD '__PASS__';
  ELSE
    ALTER ROLE __USER__ WITH LOGIN PASSWORD '__PASS__';
  END IF;
END
$$;
GRANT CONNECT ON DATABASE __DB__ TO __USER__;
GRANT USAGE ON SCHEMA public TO __USER__;
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['usuarios','categoria','prioridad','solicitud','adjunto',
                           'comentario','historial','sla','log','clasificacion_ia',
                           'embedding_vector','sugerencia_rag','log_ia','configuracion_ia'] LOOP
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = t) THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I TO __USER__', t);
    END IF;
  END LOOP;
END
$$;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO __USER__;
SQLEOF
)"
SQL="${SQL//__USER__/$APP_USER}"
SQL="${SQL//__PASS__/$APP_PASS_ESC}"
SQL="${SQL//__DB__/$PG_DB}"

printf '%s\n' "$SQL" | docker exec -i helpdesk-db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" >/dev/null
if [ $? -ne 0 ]; then
    err "❌ Error configurando el rol $APP_USER en PostgreSQL"
    exit 1
fi
ok "✅ Usuario '$APP_USER' listo (rol + permisos sobre las tablas de la app)"

# ============================================
# 2.7 DATOS INICIALES (seed_usuarios.sql)
#     Idempotente: sincroniza los usuarios de prueba (password123).
# ============================================
if [ ! -f "$SEED_FILE" ]; then
    warn "⚠️ No se encontró seed_usuarios.sql; se omiten los usuarios de prueba"
else
    cat "$SEED_FILE" | docker exec -i helpdesk-db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" >/dev/null
    if [ $? -ne 0 ]; then
        err "❌ Error aplicando seed_usuarios.sql"
        exit 1
    fi
    ok "✅ Usuarios de prueba sincronizados (contraseña: password123)"
fi

# ============================================
# 2.8 n8n + BACKEND + STREAMLIT (requieren la BD lista)
#     n8n crea sus tablas al primer arranque; backend/streamlit se
#     reconstruyen con el código actual del repo.
# ============================================
say "🐳 Levantando n8n..."
docker compose -f "$COMPOSE_FILE" up -d n8n
if [ $? -ne 0 ]; then
    err "❌ Error al iniciar n8n"
    exit 1
fi

say "🐳 Construyendo y levantando backend y streamlit..."
docker compose -f "$COMPOSE_FILE" up -d --build backend streamlit
if [ $? -ne 0 ]; then
    err "❌ Error al iniciar backend/streamlit"
    exit 1
fi

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
