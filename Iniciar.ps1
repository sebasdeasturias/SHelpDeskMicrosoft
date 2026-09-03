# Iniciar.ps1
# Script seguro: Verifica y arranca toda la infraestructura de SHelpDesk SIN borrar nada
#   PostgreSQL (pgvector) + Ollama + n8n + Backend FastAPI + Streamlit
# Además monta la base de datos completa si no existe:
#   esquema (db_logic.sql) + rol de app (helpdesk_app) + usuarios de prueba (seed_usuarios.sql)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$EnvFile = Join-Path $ProjectRoot ".env"

Write-Host "`n🚀 Iniciando HelpDesk (Contenedores + Backend)..." -ForegroundColor Cyan

# ============================================
# 0. REQUISITOS PREVIOS (Docker + .env)
# ============================================
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

$dockerOk = $false
try { docker info *> $null; $dockerOk = ($LASTEXITCODE -eq 0) } catch { $dockerOk = $false }
if (-not $dockerOk) {
    Write-Host "❌ El demonio de Docker no está corriendo. Abre Docker Desktop e inténtalo de nuevo." -ForegroundColor Red
    exit 1
}

# Plugin docker compose (v2)
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ No se encontró el plugin 'docker compose' (v2). Instálalo y vuelve a intentarlo." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ComposeFile)) {
    Write-Host "❌ No se encontró docker-compose.yml en: $ComposeFile" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "❌ No se encontró el archivo .env en: $EnvFile" -ForegroundColor Red
    Write-Host "   Es obligatorio: contiene las credenciales (POSTGRES_*, JWT_SECRET_KEY, N8N_*)." -ForegroundColor Yellow
    exit 1
}

$envContent = Get-Content $EnvFile -Raw
$requiredVars = @("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                  "APP_DB_USER", "APP_DB_PASSWORD", "AI_CALLBACK_KEY",
                  "JWT_SECRET_KEY")
$faltan = $requiredVars | Where-Object { $envContent -notmatch "(?m)^\s*$_\s*=" }
if ($faltan) {
    Write-Host "❌ Faltan variables obligatorias en .env: $($faltan -join ', ')" -ForegroundColor Red
    exit 1
}

# Usuario de PostgreSQL leído del .env (por si no es 'postgres')
$PgUser = "postgres"
if ($envContent -match "(?m)^\s*POSTGRES_USER\s*=\s*(.+?)\s*$") { $PgUser = $Matches[1] }

# ============================================
# 1. DOCKER COMPOSE - Levantar servicios base
# ============================================
Write-Host "`n🐳 Levantando servicios base (postgres, ollama)..." -ForegroundColor Cyan
# Solo servicios base: n8n/backend/streamlit se levantan DESPUÉS de configurar la BD.
docker compose -f $ComposeFile up -d postgres ollama
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al iniciar los contenedores base" -ForegroundColor Red
    exit 1
}

# ============================================
# 2. Esperar a que PostgreSQL esté listo
# ============================================
Write-Host "`n⏳ Esperando a que PostgreSQL esté disponible..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$pgReady = $false

while (-not $pgReady -and $attempt -lt $maxAttempts) {
    $attempt++
    Start-Sleep -Seconds 2

    $null = docker exec helpdesk-db pg_isready -U $PgUser 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pgReady = $true
        break
    }

    Write-Host "   Intento $attempt/$maxAttempts - PostgreSQL aún no está listo..." -ForegroundColor DarkGray
}

if (-not $pgReady) {
    Write-Host "`n❌ PostgreSQL no respondió después de $($maxAttempts * 2) segundos" -ForegroundColor Red
    Write-Host "📋 Revisa los logs con: docker logs helpdesk-db" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n✅ PostgreSQL está listo y aceptando conexiones" -ForegroundColor Green

# Mostrar estado de contenedores
Write-Host "`n📊 Estado de los servicios Docker:" -ForegroundColor Cyan
docker compose -f $ComposeFile ps --format "table {{.Name}}`t{{.Status}}`t{{.Ports}}"

# Variables de la BD de la aplicación (leídas del .env)
$SchemaFile = Join-Path $ProjectRoot "database\db_logic.sql"
$SeedFile = Join-Path $ProjectRoot "database\seed_usuarios.sql"
$AppUser = "helpdesk_app"
if ($envContent -match "(?m)^\s*APP_DB_USER\s*=\s*(.+?)\s*$") { $AppUser = $Matches[1] }
$AppPass = ""
if ($envContent -match "(?m)^\s*APP_DB_PASSWORD\s*=\s*(.+?)\s*$") { $AppPass = $Matches[1] }
$PgDb = "helpdesk_db"
if ($envContent -match "(?m)^\s*POSTGRES_DB\s*=\s*(.+?)\s*$") { $PgDb = $Matches[1] }

if ([string]::IsNullOrWhiteSpace($AppPass)) {
    Write-Host "❌ APP_DB_PASSWORD está vacía en .env" -ForegroundColor Red
    exit 1
}
if ($AppUser -notmatch "^[a-z_][a-z0-9_]*$" -or $PgDb -notmatch "^[a-z_][a-z0-9_]*$") {
    Write-Host "❌ APP_DB_USER y POSTGRES_DB deben ser solo minúsculas/números/guion bajo" -ForegroundColor Red
    exit 1
}

# ============================================
# 2.5 ESQUEMA DE LA BD (db_logic.sql)
#     Se aplica solo si la BD está vacía (primera vez / volumen nuevo).
#     Va ANTES de los permisos para que el rol herede acceso a las tablas.
# ============================================
Write-Host "`n🗄️ Verificando esquema de la BD..." -ForegroundColor Cyan

$SchemaAplicado = (docker exec helpdesk-db psql -tA -U $PgUser -d $PgDb -c `
    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='usuarios'") -eq "1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ No se pudo consultar el esquema de la BD" -ForegroundColor Red
    exit 1
}

if (-not $SchemaAplicado) {
    if (-not (Test-Path $SchemaFile)) {
        Write-Host "❌ No se encontró db_logic.sql en: $SchemaFile" -ForegroundColor Red
        exit 1
    }
    Write-Host "   Esquema vacío; aplicando db_logic.sql..." -ForegroundColor DarkGray
    docker cp $SchemaFile "helpdesk-db:/tmp/db_logic.sql"
    if ($LASTEXITCODE -ne 0) { Write-Host "❌ No se pudo copiar db_logic.sql al contenedor" -ForegroundColor Red; exit 1 }
    docker exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/db_logic.sql *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error aplicando db_logic.sql. Revisa: docker exec helpdesk-db psql -U $PgUser -d $PgDb -f /tmp/db_logic.sql" -ForegroundColor Red
        exit 1
    }
    docker exec helpdesk-db rm -f /tmp/db_logic.sql
    Write-Host "✅ Esquema (db_logic.sql) aplicado" -ForegroundColor Green
} else {
    Write-Host "✅ El esquema ya existe; no se toca" -ForegroundColor Green
}

# ============================================
# 2.5.1 MIGRACIONES (database\migraciones\*.sql)
#     Idempotentes y seguras de repetir. Alinean BDs creadas con esquemas
#     anteriores (pgvector 1024, columnas nuevas, trigger duplicador fuera).
# ============================================
Write-Host "`n🔧 Aplicando migraciones (idempotentes)..." -ForegroundColor Cyan
$MigracionesDir = Join-Path $ProjectRoot "database\migraciones"
$Migraciones = @()
if (Test-Path $MigracionesDir) {
    $Migraciones = Get-ChildItem -Path $MigracionesDir -Filter *.sql | Sort-Object Name
}
if ($Migraciones.Count -eq 0) {
    Write-Host "   (no hay migraciones en database\migraciones; se omite)" -ForegroundColor DarkGray
} else {
    foreach ($m in $Migraciones) {
        docker cp $m.FullName "helpdesk-db:/tmp/helpdesk_mig.sql" *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ No se pudo copiar la migración $($m.Name)" -ForegroundColor Red
            exit 1
        }
        docker exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/helpdesk_mig.sql *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Error aplicando la migración $($m.Name)" -ForegroundColor Red
            exit 1
        }
        docker exec helpdesk-db rm -f /tmp/helpdesk_mig.sql
        Write-Host "   ✅ $($m.Name)" -ForegroundColor Green
    }
}

# ============================================
# 2.6 USUARIO DE BD DE LA APLICACIÓN (mínimo privilegio)
#     docker-compose solo inyecta APP_DB_USER/APP_DB_PASSWORD al backend;
#     el rol debe existir dentro de PostgreSQL. Idempotente.
# ============================================
Write-Host "`n👤 Configurando el usuario de BD de la aplicación..." -ForegroundColor Cyan

$EscPass = $AppPass.Replace("'", "''")
$Sql = @'
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
'@
$Sql = $Sql.Replace('__USER__', $AppUser).Replace('__PASS__', $EscPass).Replace('__DB__', $PgDb)

$TmpSql = Join-Path $env:TEMP "helpdesk_app_init.sql"
[System.IO.File]::WriteAllText($TmpSql, $Sql, (New-Object System.Text.UTF8Encoding($false)))
try {
    docker cp $TmpSql "helpdesk-db:/tmp/helpdesk_app_init.sql"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el SQL al contenedor" }
    docker exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/helpdesk_app_init.sql
    if ($LASTEXITCODE -ne 0) { throw "Error configurando el rol $AppUser en PostgreSQL" }
    docker exec helpdesk-db rm -f /tmp/helpdesk_app_init.sql
    Write-Host "✅ Usuario '$AppUser' listo (rol + permisos sobre las tablas de la app)" -ForegroundColor Green
} finally {
    Remove-Item $TmpSql -ErrorAction SilentlyContinue
}

# ============================================
# 2.7 DATOS INICIALES (seed_usuarios.sql)
#     Idempotente: sincroniza los usuarios de prueba (password123).
# ============================================
if (-not (Test-Path $SeedFile)) {
    Write-Host "⚠️ No se encontró seed_usuarios.sql; se omiten los usuarios de prueba" -ForegroundColor Yellow
} else {
    docker cp $SeedFile "helpdesk-db:/tmp/seed_usuarios.sql"
    if ($LASTEXITCODE -ne 0) { Write-Host "❌ No se pudo copiar seed_usuarios.sql al contenedor" -ForegroundColor Red; exit 1 }
    docker exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/seed_usuarios.sql *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error aplicando seed_usuarios.sql" -ForegroundColor Red
        exit 1
    }
    docker exec helpdesk-db rm -f /tmp/seed_usuarios.sql
    Write-Host "✅ Usuarios de prueba sincronizados (contraseña: password123)" -ForegroundColor Green
}

# ============================================
# 2.8 n8n (requiere PostgreSQL listo; crea sus tablas al primer arranque)
# ============================================
Write-Host "`n🐳 Levantando n8n..." -ForegroundColor Cyan
docker compose -f $ComposeFile up -d n8n
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al iniciar n8n" -ForegroundColor Red
    exit 1
}

# ============================================
# 3. BACKEND - Corre dentro de Docker (servicio "backend")
# ============================================
Write-Host "`n🐳 Construyendo/actualizando el backend dentro de Docker..." -ForegroundColor Cyan
docker compose -f $ComposeFile up -d --build backend
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al iniciar el contenedor del backend" -ForegroundColor Red
    exit 1
}

# ============================================
# 4. STREAMLIT - Dashboard de estadísticas y control admin
# ============================================
Write-Host "`n🐳 Construyendo/actualizando Streamlit dentro de Docker..." -ForegroundColor Cyan
docker compose -f $ComposeFile up -d --build streamlit
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al iniciar el contenedor de Streamlit" -ForegroundColor Red
    exit 1
}

# ============================================
# 5. HEALTH CHECKS (no fatales)
# ============================================
function Wait-HttpOk {
    param([string]$Url, [string]$Nombre, [int]$MaxAttempts = 30)
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Seconds 2 }
        Write-Host "   Intento $i/$MaxAttempts - $Nombre aún no responde..." -ForegroundColor DarkGray
    }
    return $false
}

Write-Host "`n⏳ Esperando al backend (FastAPI :8000)..." -ForegroundColor Yellow
if (Wait-HttpOk -Url "http://localhost:8000/api/health" -Nombre "Backend") {
    Write-Host "✅ Backend respondiendo en :8000" -ForegroundColor Green
} else {
    Write-Host "⚠️ El backend no respondió a tiempo; revisa: docker logs helpdesk-backend" -ForegroundColor Yellow
}

Write-Host "⏳ Esperando a Streamlit (:8501)..." -ForegroundColor Yellow
if (Wait-HttpOk -Url "http://localhost:8501" -Nombre "Streamlit") {
    Write-Host "✅ Streamlit respondiendo en :8501" -ForegroundColor Green
} else {
    Write-Host "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit" -ForegroundColor Yellow
}

# ============================================
# 6. RESUMEN
# ============================================
Write-Host "`n✅ Backend corriendo en Docker (sincronizado con .\backend)" -ForegroundColor Green
Write-Host "   URL:  http://localhost:8000" -ForegroundColor DarkGray
Write-Host "   Docs: http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host "`n✅ Streamlit corriendo en Docker (sincronizado con .\streamlit_app)" -ForegroundColor Green
Write-Host "   URL:  http://localhost:8501" -ForegroundColor DarkGray
Write-Host "`n✅ n8n (workflows IA): http://localhost:5678" -ForegroundColor Green
Write-Host "✅ Ollama (modelos IA): http://localhost:11434" -ForegroundColor Green
Write-Host "✅ PostgreSQL: localhost:5432 (usuario: $PgUser)" -ForegroundColor Green
Write-Host "`n📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-streamlit" -ForegroundColor Yellow
