#!/usr/bin/env bash
# ============================================
# iniciar-cloudflared.sh — SHelpDesk Microsoft (TÚNEL Cloudflare: backend + PANEL)
# Levanta la pila completa y expone por Cloudflare el backend (FastAPI) y el
# PANEL de Streamlit, con URLs automáticas listas al terminar.
#
# DOS MODOS, según el .env:
#
#   * MODO TOKEN (CLOUDFLARE_TUNNEL_TOKEN presente en .env):
#       Usa docker-compose.cloudflared.yml: NINGÚN puerto al host; todo sale
#       por el túnel gestionado (hostnames fijos de Zero Trust):
#         - API   -> https://api.tudominio.com/api    (frontend en Vercel)
#         - Panel -> https://panel.tudominio.com      (Streamlit)
#       ADEMÁS arranca un túnel RÁPIDO extra (contenedor cloudflared-panel)
#       con URL automática temporal para el panel, visible en:
#         docker logs helpdesk-cloudflared-panel
#
#   * MODO PRUEBA (sin token en .env):
#       Usa el compose DEV (puertos locales publicados: 8000/8501) y crea DOS
#       túneles rápidos en el host (trycloudflare, sin cuenta de Cloudflare):
#         - Backend -> https://<sub>.trycloudflare.com   (actualiza config.js)
#         - Panel   -> https://<sub>.trycloudflare.com
#
# Flags:
#   --no-config   (modo prueba) no modifica frontend/js/config.js
#
# Uso:
#   chmod +x iniciar-cloudflared.sh
#   ./iniciar-cloudflared.sh [--no-config]
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
COMPOSE_TOKEN="$SCRIPT_DIR/docker-compose.cloudflared.yml"
COMPOSE_DEV="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"
CONFIG_JS="$PROJECT_ROOT/frontend/js/config.js"
CF_DIR="$HOME/.cloudflared"

# Flags
NO_CONFIG=0
for arg in "$@"; do
    case "$arg" in
        --no-config) NO_CONFIG=1 ;;
        *) echo "Flag desconocido: $arg (usos: --no-config)"; exit 1 ;;
    esac
done

# docker compose solo auto-carga .env desde el directorio del compose;
# aquí el compose está en docker/ y el .env vive en la raíz:
# se pasa SIEMPRE con --env-file.
COMPOSE_ARGS=()

echo ""
say "🚀 Iniciando HelpDesk por TÚNEL CLOUDFLARE (backend + panel)..."

# ============================================
# 0. REQUISITOS PREVIOS (Docker + .env + modo)
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

# --- Selección de modo ---
MODO_TOKEN=0
if grep -qE "^[[:space:]]*CLOUDFLARE_TUNNEL_TOKEN[[:space:]]*=[[:space:]]*[^[:space:]]" "$ENV_FILE"; then
    MODO_TOKEN=1
    COMPOSE_FILE="$COMPOSE_TOKEN"
else
    COMPOSE_FILE="$COMPOSE_DEV"
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    err "❌ No se encontró el compose en: $COMPOSE_FILE"
    exit 1
fi

COMPOSE_ARGS=(-f "$COMPOSE_FILE" --env-file "$ENV_FILE")

if [ "$MODO_TOKEN" -eq 1 ]; then
    say "🔑 MODO TOKEN: túnel gestionado por Cloudflare (hostnames fijos) + URL automática extra para el panel."
else
    warn "🧪 MODO PRUEBA: sin CLOUDFLARE_TUNNEL_TOKEN en .env. Se usa el stack dev (puertos locales)"
    warn "   y se crean túneles rápidos automáticos para el backend (:8000) y el PANEL (:8501)."
    dim "   Para hostnames fijos, añade CLOUDFLARE_TUNNEL_TOKEN al .env (Zero Trust -> Tunnels)."
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
# Helpers de túneles rápidos (trycloudflare)
# ============================================
ensure_cloudflared() {
    # Binario correcto por SO; $EXE global.
    case "$(uname -s)/$(uname -m)" in
        Linux/x86_64)
            EXE="$CF_DIR/cloudflared"
            [ -x "$EXE" ] && return 0
            mkdir -p "$CF_DIR"
            warn "⬇️  Descargando cloudflared (linux amd64)..."
            curl -fsSL -o "$EXE" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" || return 1
            chmod +x "$EXE"
            ;;
        Darwin/arm64)
            EXE="$CF_DIR/cloudflared"
            [ -x "$EXE" ] && return 0
            mkdir -p "$CF_DIR"
            warn "⬇️  Descargando cloudflared (darwin arm64)..."
            curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz" | tar -xz -C "$CF_DIR" cloudflared || return 1
            chmod +x "$EXE"
            ;;
        Darwin/x86_64)
            EXE="$CF_DIR/cloudflared"
            [ -x "$EXE" ] && return 0
            mkdir -p "$CF_DIR"
            warn "⬇️  Descargando cloudflared (darwin amd64)..."
            curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz" | tar -xz -C "$CF_DIR" cloudflared || return 1
            chmod +x "$EXE"
            ;;
        *)
            err "❌ SO no soportado para el túnel rápido: $(uname -s)/$(uname -m)"
            return 1
            ;;
    esac
}

iniciar_tunel_rapido() {
    # $1 nombre, $2 url_local, $3 prefijo_log -> imprime la URL pública o falla
    local nombre="$1" url_local="$2" prefijo="$3"
    ensure_cloudflared || return 1

    # Solo mata túneles previos hacia la MISMA URL local (no toca otros)
    if command -v pkill >/dev/null 2>&1; then
        pkill -f "cloudflared.*--url $url_local" 2>/dev/null || true
        sleep 1
    fi

    local out="$CF_DIR/$prefijo.out.log" errf="$CF_DIR/$prefijo.err.log"
    rm -f "$out" "$errf"

    say "🚀 Túnel rápido $nombre -> $url_local ..."
    nohup "$EXE" tunnel --url "$url_local" --no-autoupdate >"$out" 2>"$errf" &
    echo $! > "$CF_DIR/$prefijo.pid"
    dim "   PID: $(cat "$CF_DIR/$prefijo.pid") (queda corriendo en segundo plano)"

    local i url=""
    for i in $(seq 1 30); do
        url="$(grep -hoE 'https://[a-z0-9-]+\.trycloudflare\.com' "$out" "$errf" 2>/dev/null | tail -n1)"
        if [ -n "$url" ]; then
            printf '%s\n' "$url"
            return 0
        fi
        sleep 1
    done
    err "❌ No se obtuvo la URL del túnel $nombre en 30s. Revisa: $errf"
    return 1
}

test_url_publica() {
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$1" 2>/dev/null || true)"
    if [ -n "$code" ] && [ "$code" -ge 200 ] 2>/dev/null && [ "$code" -lt 500 ] 2>/dev/null; then
        return 0
    fi
    return 1
}

update_config_js() {
    local url="$1" stamp
    if [ ! -f "$CONFIG_JS" ]; then
        warn "⚠️  No se encontró $CONFIG_JS"
        return
    fi
    stamp="$(date '+%Y-%m-%d %H:%M')"
    if grep -qE "^window\.APP_API_BASE_URL" "$CONFIG_JS"; then
        sed -i.bak "s|^window\.APP_API_BASE_URL.*|window.APP_API_BASE_URL = '$url'; // TEMPORAL (prueba de conexión; túnel del $stamp)|" "$CONFIG_JS"
        rm -f "$CONFIG_JS.bak"
        ok "✅ frontend/js/config.js actualizado con $url"
        dim "   Haz git add/commit/push para redesplegar Vercel."
    else
        warn "⚠️  No encontré la línea window.APP_API_BASE_URL; edítala a mano:"
        warn "   window.APP_API_BASE_URL = '$url';"
    fi
}

wait_http_ok() {
    # $1 url  $2 nombre  $3 intentos
    local url="$1" nombre="$2" intentos="${3:-30}" i=0 code
    while [ "$i" -lt "$intentos" ]; do
        i=$((i + 1))
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "$url" 2>/dev/null || true)"
        if [ "$code" = "200" ]; then
            return 0
        fi
        dim "   Intento $i/$intentos - $nombre aún no responde..."
        sleep 2
    done
    return 1
}

# ============================================
# 1. DOCKER COMPOSE - Levantar servicios base
# ============================================
say "🐳 Levantando servicios base (postgres, ollama)..."
if [ "$MODO_TOKEN" -eq 1 ]; then
    dim "   ℹ️ Este stack reemplaza el dev: localhost:8000/8501/5432/5678 dejan de publicarse."
fi
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
                           'embedding_vector','sugerencia_rag','log_ia','configuracion_ia',
                           'mensaje_chat_global'] LOOP
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
# 3. STACK COMPLETO + TÚNELES (build incluido)
# ============================================
if [ "$MODO_TOKEN" -eq 1 ]; then
    say "🐳 Construyendo y levantando n8n + backend + streamlit + cloudflared..."
else
    say "🐳 Construyendo y levantando n8n + backend + streamlit..."
fi
docker compose "${COMPOSE_ARGS[@]}" up -d --build
if [ $? -ne 0 ]; then
    err "❌ Error al construir/levantar la pila"
    exit 1
fi

# ============================================
# 4. HEALTH CHECKS + TÚNELES (no fatales)
# ============================================
URL_API=""
URL_PANEL=""

if [ "$MODO_TOKEN" -eq 1 ]; then
    # 4.1 Backend: healthcheck del compose (dentro del contenedor)
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

    # 4.2 Streamlit: prueba HTTP interna (:8501)
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

    # 4.3 Túnel token: conexión registrada en el edge
    say "⏳ Esperando registro del túnel Cloudflare (token)..."
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
        ok "✅ Túnel con token registrado y conectado al edge"
    else
        warn "⚠️ No se vio 'Registered tunnel connection' (¿token válido? ¿hostnames configurados?)"
        warn "   Revisa: docker logs helpdesk-cloudflared"
    fi

    # 4.4 URL AUTOMÁTICA del PANEL (túnel rápido en contenedor)
    say "⏳ Esperando la URL automática del PANEL (túnel rápido en contenedor)..."
    i=0
    while [ "$i" -lt 20 ]; do
        i=$((i + 1))
        URL_PANEL="$(docker logs --tail 100 helpdesk-cloudflared-panel 2>&1 | grep -hoE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n1)"
        [ -n "$URL_PANEL" ] && break
        sleep 2
    done
    if [ -n "$URL_PANEL" ]; then
        if test_url_publica "$URL_PANEL"; then
            ok "✅ PANEL expuesto automáticamente en: $URL_PANEL"
        else
            warn "⚠️ La URL del panel aún no responde (Cloudflare puede tardar unos segundos más)."
        fi
    else
        warn "⚠️ No se obtuvo la URL automática del panel; revisa: docker logs helpdesk-cloudflared-panel"
    fi
else
    # -------- MODO PRUEBA: puertos locales publicados --------
    say "⏳ Esperando al backend (http://localhost:8000/api/health)..."
    if wait_http_ok "http://localhost:8000/api/health" "Backend" 45; then
        ok "✅ Backend respondiendo en http://localhost:8000"
    else
        warn "⚠️ El backend no respondió a tiempo; revisa: docker logs helpdesk-backend"
    fi

    say "⏳ Esperando a Streamlit (http://localhost:8501)..."
    if wait_http_ok "http://localhost:8501" "Streamlit" 30; then
        ok "✅ Streamlit respondiendo en http://localhost:8501"
    else
        warn "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit"
    fi

    # -------- TÚNELES RÁPIDOS AUTOMÁTICOS (backend + panel) --------
    URL_API="$(iniciar_tunel_rapido "API/backend" "http://localhost:8000" "tunel-backend" || true)"
    if [ -n "$URL_API" ]; then
        if test_url_publica "$URL_API/api/health"; then
            ok "✅ Backend expuesto automáticamente en: $URL_API"
        else
            warn "⚠️ La URL del backend aún no responde (reintenta en unos segundos)."
        fi
    fi

    URL_PANEL="$(iniciar_tunel_rapido "Panel/Streamlit" "http://localhost:8501" "tunel-streamlit" || true)"
    if [ -n "$URL_PANEL" ]; then
        if test_url_publica "$URL_PANEL"; then
            ok "✅ PANEL expuesto automáticamente en: $URL_PANEL"
        else
            warn "⚠️ La URL del panel aún no responde (reintenta en unos segundos)."
        fi
    fi

    # Mantener el frontend de Vercel apuntando al backend actual
    if [ "$NO_CONFIG" -eq 1 ]; then
        dim "ℹ️  --no-config: frontend/js/config.js sin tocar"
    elif [ -n "$URL_API" ]; then
        update_config_js "$URL_API"
    fi
fi

# ============================================
# 5. RESUMEN
# ============================================
say "📊 Estado de los servicios Docker:"
docker compose "${COMPOSE_ARGS[@]}" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

if [ "$MODO_TOKEN" -eq 1 ]; then
    ok "✅ Stack de producción por túnel Cloudflare levantado"
    dim "   API (Vercel) : https://api.tudominio.com/api   <- apunta aquí tu frontend (APP_API_BASE_URL)"
    dim "   Panel (fijo) : https://panel.tudominio.com     (hostname del túnel con token)"
    if [ -n "$URL_PANEL" ]; then
        ok "   Panel (auto) : $URL_PANEL  <- URL automática temporal, lista ya"
    fi
    dim "   Hostnames    : configúralos en Cloudflare Zero Trust -> Tunnels -> Public Hostnames"
    dim "                  api.tudominio.com   -> http://backend:8000"
    dim "                  panel.tudominio.com -> http://streamlit:8501"
    warn "⚠️  Modo túnel: SIN puertos locales. localhost:8000 / :8501 / :5678 / :5432 / :11434"
    warn "   NO responden en el host; n8n/pg/ollama solo son accesibles desde la red interna."
    warn "   Para volver al entorno dev: ./iniciar.sh (en la raíz)"
    warn "📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-cloudflared | docker logs -f helpdesk-cloudflared-panel"
else
    ok "✅ MODO PRUEBA levantado (stack dev + túneles rápidos automáticos)"
    if [ -n "$URL_API" ]; then
        ok "   API  pública : $URL_API/api   (backend; frontend Vercel apunta aquí)"
        dim "   Docs         : $URL_API/docs"
    fi
    if [ -n "$URL_PANEL" ]; then
        ok "   Panel público: $URL_PANEL      (Streamlit, login del panel)"
    fi
    dim "   Local        : http://localhost:8000  |  http://localhost:8501"
    warn "⚠️  URLs trycloudflare TEMPORALES: cambian en cada ejecución del script."
    dim "   Túneles en segundo plano (logs en ~/.cloudflared/tunel-backend.* / tunel-streamlit.*)."
    dim "   Parar los túneles : pkill -f cloudflared"
    dim "   Hostnames fijos   : añade CLOUDFLARE_TUNNEL_TOKEN al .env y vuelve a ejecutar este script."
    warn "📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-streamlit"
fi
echo ""
