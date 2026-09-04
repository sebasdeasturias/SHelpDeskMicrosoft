#!/usr/bin/env bash
# ============================================
# iniciar-cloudflared.sh — SHelpDesk Microsoft (PRODUCCIÓN por TÚNEL Cloudflare)
# Levanta la pila completa definida en docker-compose.cloudflared.yml:
#   postgres (pgvector) + ollama + n8n + backend FastAPI + streamlit + cloudflared
#
# Diferencias con iniciar.sh (dev):
#   * Usa docker-compose.cloudflared.yml: NINGÚN puerto se publica al host.
#       - API      -> https://api.tudominio.com/api     (frontend en Vercel)
#       - Panel    -> https://panel.tudominio.com        (Streamlit)
#   * backend/streamlit se CONSTRUYEN desde imagen (sin bind mount de código).
#   * Exige CLOUDFLARE_TUNNEL_TOKEN en .env (Cloudflare Zero Trust -> Tunnels).
#   * Reutiliza el MISMO proyecto compose (shelpdeskmicrosoft): recicla los
#     volúmenes/datos del entorno dev, pero al terminar NO habrá localhost:8000
#     ni localhost:8501, y n8n/postgres/ollama quedan solo en la red interna.
#
# Uso:
#   chmod +x iniciar-cloudflared.sh
#   ./iniciar-cloudflared.sh
# ============================================
set -u

# Colores
CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; GREEN='\033[0;32m'; GRAY='\033[0;90m'; NC='\033[0m'

say()  { echo -e "${CYAN}${1}${NC}"; }
warn() { echo -e "${YELLOW}${1}${NC}"; }
err()  { echo -e "${RED}${1}${NC}"; }
ok()   { echo -e "${GREEN}${1}${NC}"; }
dim()  { echo -e "${GRAY}${1}${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.cloudflared.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# docker compose solo auto-carga .env desde el directorio del compose;
# aquí el compose está en docker/ y el .env vive en la raíz:
# se pasa SIEMPRE con --env-file.
COMPOSE_ARGS=(-f "$COMPOSE_FILE" --env-file "$ENV_FILE")

echo ""
say "🚀 Iniciando HelpDesk por TÚNEL CLOUDFLARE (stack producción)..."

# ============================================
# 0. REQUISITOS PREVIOS (Docker + .env + token)
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
    err "❌ No se encontró el compose en: $COMPOSE_FILE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    err "❌ No se encontró el archivo .env en: $ENV_FILE"
    warn "   Es obligatorio: contiene las credenciales (POSTGRES_*, JWT_SECRET_KEY, N8N_*)."
    exit 1
fi

faltan=""
for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB APP_DB_USER APP_DB_PASSWORD AI_CALLBACK_KEY JWT_SECRET_KEY CLOUDFLARE_TUNNEL_TOKEN; do
    grep -qE "^[[:space:]]*${var}[[:space:]]*=" "$ENV_FILE" || faltan="$faltan $var"
done
if [ -n "$faltan" ]; then
    err "❌ Faltan variables obligatorias en .env:$faltan"
    if printf '%s' "$faltan" | grep -q "CLOUDFLARE_TUNNEL_TOKEN"; then
        warn "   Crea el túnel en Cloudflare Zero Trust -> Networks -> Tunnels -> 'Create a tunnel',"
        warn "   copia el token (eyJhIjoi...) y añádelo al .env como CLOUDFLARE_TUNNEL_TOKEN=..."
    fi
    exit 1
fi

# Avisos (no fatales) para el frontend de Vercel
if ! grep -qE "^[[:space:]]*CORS_ORIGINS[[:space:]]*=" "$ENV_FILE"; then
    warn "⚠️ CORS_ORIGINS no está en .env (el compose usará '*'). Para Vercel conviene:"
    warn "   CORS_ORIGINS=https://<tu-app>.vercel.app"
fi
if ! grep -qE "^[[:space:]]*N8N_API_KEY[[:space:]]*=" "$ENV_FILE"; then
    warn "⚠️ N8N_API_KEY no está en .env (sin ella el panel no podrá hablar con la API de n8n)"
fi

# Usuario de PostgreSQL leído del .env (por si no es 'postgres')
PG_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d ' \t\r\"')"
PG_USER="${PG_USER:-postgres}"

# ============================================
# 1. DOCKER COMPOSE - Levantar servicios base
#    (postgres/ollama se recrean SIN puertos publicados: modo túnel)
# ============================================
say "🐳 Levantando servicios base (postgres, ollama)..."
dim "   ℹ️ Este stack reemplaza el dev: localhost:8000/8501/5432/5678 dejan de publicarse."
docker compose "${COMPOSE_ARGS[@]}" up -d postgres ollama
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
SCHEMA_FILE="$PROJECT_ROOT/database/db_logic.sql"
SEED_FILE="$PROJECT_ROOT/database/seed_usuarios.sql"
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
# 2.5.1 MIGRACIONES (database/migraciones/*.sql)
#     Idempotentes y seguras de repetir.
# ============================================
MIGRACIONES_DIR="$PROJECT_ROOT/database/migraciones"
if [ -d "$MIGRACIONES_DIR" ] && ls "$MIGRACIONES_DIR"/*.sql >/dev/null 2>&1; then
    say "🔧 Aplicando migraciones (idempotentes)..."
    for f in "$MIGRACIONES_DIR"/*.sql; do
        nombre="$(basename "$f")"
        if cat "$f" | docker exec -i helpdesk-db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
            ok "   ✅ $nombre"
        else
            err "   ❌ Error aplicando $nombre"
            exit 1
        fi
    done
else
    dim "   (no hay migraciones en database/migraciones; se omite)"
fi

# ============================================
# 2.6 USUARIO DE BD DE LA APLICACIÓN (mínimo privilegio)
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
# 3. STACK COMPLETO + TÚNEL (build incluido)
#    depends_on con service_healthy garantiza el orden tras postgres.
# ============================================
say "🐳 Construyendo y levantando n8n + backend + streamlit + cloudflared..."
docker compose "${COMPOSE_ARGS[@]}" up -d --build
if [ $? -ne 0 ]; then
    err "❌ Error al construir/levantar la pila"
    exit 1
fi

# ============================================
# 4. HEALTH CHECKS (no fatales; vía contenedor, NO por localhost:
#    en modo túnel ningún puerto está publicado en el host)
# ============================================

# 4.1 Backend: espera el healthcheck definido en el compose (dentro del contenedor)
say "⏳ Esperando al backend (healthcheck interno :8000)..."
backend_ok=false
i=0
while [ "$i" -lt 45 ]; do
    i=$((i + 1))
    st="$(docker inspect -f '{{.State.Health.Status}}' helpdesk-backend 2>/dev/null || true)"
    if [ "$st" = "healthy" ]; then
        backend_ok=true
        break
    fi
    dim "   Intento $i/45 - backend aún no está healthy (${st:-desconocido})..."
    sleep 2
done
if [ "$backend_ok" = true ]; then
    ok "✅ Backend healthy (accesible por el túnel en /api/*)"
else
    warn "⚠️ El backend no reportó healthy a tiempo; revisa: docker logs helpdesk-backend"
fi

# 4.2 Streamlit: prueba HTTP interna dentro del contenedor (:8501)
say "⏳ Esperando a Streamlit (prueba interna :8501)..."
streamlit_ok=false
i=0
while [ "$i" -lt 30 ]; do
    i=$((i + 1))
    if docker exec helpdesk-streamlit python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501', timeout=3).getcode()==200 else 1)" >/dev/null 2>&1; then
        streamlit_ok=true
        break
    fi
    dim "   Intento $i/30 - Streamlit aún no responde..."
    sleep 2
done
if [ "$streamlit_ok" = true ]; then
    ok "✅ Streamlit respondiendo (accesible por el túnel en /)"
else
    warn "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit"
fi

# 4.3 Cloudflared: busca en los logs la conexión registrada del túnel
say "⏳ Esperando registro del túnel Cloudflare..."
tunel_ok=false
i=0
while [ "$i" -lt 20 ]; do
    i=$((i + 1))
    if docker logs --tail 100 helpdesk-cloudflared 2>&1 | grep -q "Registered tunnel connection"; then
        tunel_ok=true
        break
    fi
    sleep 2
done
if [ "$tunel_ok" = true ]; then
    ok "✅ Túnel Cloudflare registrado y conectado al edge"
else
    warn "⚠️ No se vio 'Registered tunnel connection' en los logs."
    warn "   Revisa: docker logs helpdesk-cloudflared (¿token válido? ¿hostname configurado en Cloudflare?)"
fi

# ============================================
# 5. RESUMEN
# ============================================
say "📊 Estado de los servicios Docker:"
docker compose "${COMPOSE_ARGS[@]}" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

ok "✅ Stack de producción por túnel Cloudflare levantado"
dim "   API (Vercel) : https://api.tudominio.com/api   <- apunta aquí tu frontend (APP_API_BASE_URL)"
dim "   Panel        : https://panel.tudominio.com     (Streamlit vía túnel)"
dim "   Hostnames    : configúralos en Cloudflare Zero Trust -> Tunnels -> Public Hostnames"
dim "                  api.tudominio.com   -> http://backend:8000"
dim "                  panel.tudominio.com -> http://streamlit:8501"
warn "⚠️  Modo túnel: SIN puertos locales. localhost:8000 / :8501 / :5678 / :5432 / :11434"
warn "   NO responden en el host; n8n/pg/ollama solo son accesibles desde la red interna."
warn "   Para volver al entorno dev: ./iniciar.sh (en la raíz)"
warn "📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-cloudflared"
echo ""
