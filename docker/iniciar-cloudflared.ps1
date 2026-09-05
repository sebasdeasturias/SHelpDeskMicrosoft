# iniciar-cloudflared.ps1 — SHelpDesk Microsoft (TÚNEL Cloudflare: backend + PANEL)
# Levanta la pila completa y expone por Cloudflare el backend (FastAPI) y el
# PANEL de Streamlit, con URLs automáticas listas al terminar.
#
# DOS MODOS, según el .env:
#
#   * MODO TOKEN (CLOUDFLARE_TUNNEL_TOKEN presente en .env):
#       Usa docker-compose.cloudflared.yml: NINGÚN puerto se publica al host;
#       todo sale por el túnel gestionado (hostnames fijos de Zero Trust):
#         - API   -> https://api.tudominio.com/api    (frontend en Vercel)
#         - Panel -> https://panel.tudominio.com      (Streamlit)
#       ADEMÁS arranca un túnel RÁPIDO extra (contenedor cloudflared-panel)
#       que genera una URL automática temporal para el panel (trycloudflare),
#       impresa al final y visible en: docker logs helpdesk-cloudflared-panel
#
#   * MODO PRUEBA (sin token en .env):
#       Usa el compose DEV (puertos locales publicados: 8000/8501) y crea DOS
#       túneles rápidos en el host (trycloudflare, sin cuenta de Cloudflare):
#         - Backend -> https://<sub>.trycloudflare.com   (actualiza config.js
#                      con .../api una vez que responde HTTP 200)
#         - Panel   -> https://<sub>.trycloudflare.com
#       URLs temporales: cambian en cada ejecución (ideales para probar).
#
# Flags:
#   -NoConfigUpdate   (modo prueba) no modifica frontend/js/config.js
#
# Requisitos .env: POSTGRES_*, APP_DB_*, JWT_SECRET_KEY, AI_CALLBACK_KEY
# (+ CLOUDFLARE_TUNNEL_TOKEN y CORS_ORIGINS recomendados para el modo token).

param([switch]$NoConfigUpdate)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Split-Path $ScriptDir -Parent
$ComposeToken = Join-Path $ScriptDir "docker-compose.cloudflared.yml"
$ComposeDev = Join-Path $ScriptDir "docker-compose.yml"
$EnvFile = Join-Path $ProjectRoot ".env"
$ConfigJs = Join-Path $ProjectRoot "frontend\js\config.js"
$CfDir = Join-Path $env:USERPROFILE ".cloudflared"
$Exe = Join-Path $CfDir "cloudflared.exe"

# ------------------------------------------------------------------
# FIX PowerShell 5.1: con $ErrorActionPreference = "Stop", cualquier
# línea que un comando nativo escriba en stderr (p. ej. los NOTICE de
# psql que llegan vía docker exec) se convierte en "NativeCommandError"
# y aborta el script aunque el comando haya terminado bien (exit 0).
# ------------------------------------------------------------------
function Invoke-DockerQuiet {
    # Ejecuta docker silenciado y DEVUELVE el código de salida real.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker @args *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Invoke-DockerOutput {
    # Ejecuta docker y devuelve stdout+stderr como texto (sin lanzar
    # NativeCommandError por el stderr; útil para docker logs/inspect).
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker @args 2>&1
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Ensure-Cloudflared {
    # Garantiza el binario cloudflared para los túneles rápidos del host.
    if (Test-Path $Exe) { return $true }
    Write-Host "⬇️  Descargando cloudflared (Windows amd64)..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $CfDir -Force | Out-Null
    Invoke-QuietCmd { Invoke-WebRequest `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $Exe -UseBasicParsing -TimeoutSec 120 }
    return (Test-Path $Exe)
}

function Invoke-QuietCmd {
    # Ejecuta un scriptblock con EAP=Continue (evita NativeCommandError).
    param([scriptblock]$Cmd)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Cmd } finally { $ErrorActionPreference = $prev }
}

function Start-TunelRapidoHost {
    # Túnel rápido (trycloudflare) en el host hacia un puerto local.
    # Mata primero cualquier túnel previo hacia la MISMA URL local y devuelve
    # la URL pública nueva (o $null si no se pudo).
    param([string]$Nombre, [string]$UrlLocal, [string]$PrefijoLog)

    if (-not (Ensure-Cloudflared)) {
        Write-Host "❌ No se pudo obtener cloudflared para el túnel de $Nombre" -ForegroundColor Red
        return $null
    }

    # Solo mata los túneles que apuntan a la MISMA URL local (no toca otros).
    Invoke-QuietCmd {
        Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
            Where-Object { $_.CommandLine -like "*--url $UrlLocal*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    Start-Sleep -Milliseconds 800

    $logOut = Join-Path $CfDir "$PrefijoLog.out.log"
    $logErr = Join-Path $CfDir "$PrefijoLog.err.log"
    Remove-Item $logOut, $logErr -ErrorAction SilentlyContinue

    Write-Host "🚀 Túnel rápido $Nombre -> $UrlLocal ..." -ForegroundColor Cyan
    $p = Invoke-QuietCmd { Start-Process -FilePath $Exe `
        -ArgumentList @("tunnel", "--url", $UrlLocal, "--no-autoupdate") `
        -WindowStyle Hidden -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru }
    Write-Host "   PID: $($p.Id) (queda corriendo en segundo plano)" -ForegroundColor DarkGray

    return Get-UrlDeLogs -LogOut $logOut -LogErr $logErr -Nombre $Nombre
}

function Get-UrlDeLogs {
    # Extrae la URL trycloudflare de los logs de un túnel rápido (host).
    param([string]$LogOut, [string]$LogErr, [string]$Nombre)
    for ($i = 1; $i -le 30; $i++) {
        $logs = @()
        if (Test-Path $LogErr) { $logs += Get-Content $LogErr -ErrorAction SilentlyContinue }
        if (Test-Path $LogOut) { $logs += Get-Content $LogOut -ErrorAction SilentlyContinue }
        $m = ($logs | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1)
        if ($m) { return $m.Matches.Value }
        Start-Sleep -Seconds 1
    }
    Write-Host "❌ No se obtuvo la URL del túnel $Nombre en 30s. Revisa: $LogErr" -ForegroundColor Red
    return $null
}

function Test-UrlPublica {
    # Verificación suave: true si la URL responde (cualquier código HTTP).
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 25
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch {
        $resp = $_.Exception.Response
        if ($resp) { $code = [int]$resp.StatusCode; return ($code -ge 200 -and $code -lt 500) }
        return $false
    }
}

function Update-ConfigJs {
    # Reescribe window.APP_API_BASE_URL en frontend/js/config.js (Vercel).
    param([string]$UrlApi)
    if (-not (Test-Path $ConfigJs)) {
        Write-Host "⚠️  No se encontró $ConfigJs" -ForegroundColor Yellow
        return
    }
    $raw = [System.IO.File]::ReadAllText($ConfigJs)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $pattern = "(?m)^window\.APP_API_BASE_URL\s*=\s*'[^']*';.*$"
    $replacement = "window.APP_API_BASE_URL = '$UrlApi'; // TEMPORAL (prueba de conexión; túnel del $stamp)"
    $nuevo = [regex]::Replace($raw, $pattern, $replacement)
    if ($nuevo -eq $raw -and $raw -notmatch [regex]::Escape($UrlApi)) {
        Write-Host "⚠️  No encontré la línea window.APP_API_BASE_URL; edítala a mano:" -ForegroundColor Yellow
        Write-Host "   $replacement" -ForegroundColor Yellow
        return
    }
    $bytes = [System.IO.File]::ReadAllBytes($ConfigJs)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    [System.IO.File]::WriteAllText($ConfigJs, $nuevo, (New-Object System.Text.UTF8Encoding($hasBom)))
    Write-Host "✅ frontend/js/config.js actualizado con $UrlApi" -ForegroundColor Green
    Write-Host "   Haz 'git add frontend/js/config.js && git commit && git push' para redesplegar Vercel." -ForegroundColor DarkGray
}

Write-Host "`n🚀 Iniciando HelpDesk por TÚNEL CLOUDFLARE (backend + panel)..." -ForegroundColor Cyan

# ============================================
# 0. REQUISITOS PREVIOS (Docker + .env + modo)
# ============================================
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

if ((Invoke-DockerQuiet info) -ne 0) {
    Write-Host "❌ El demonio de Docker no está corriendo. Abre Docker Desktop e inténtalo de nuevo." -ForegroundColor Red
    exit 1
}

if ((Invoke-DockerQuiet compose version) -ne 0) {
    Write-Host "❌ No se encontró el plugin 'docker compose' (v2). Instálalo y vuelve a intentarlo." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "❌ No se encontró el archivo .env en: $EnvFile" -ForegroundColor Red
    Write-Host "   Es obligatorio: contiene las credenciales (POSTGRES_*, JWT_SECRET_KEY, N8N_*)." -ForegroundColor Yellow
    exit 1
}

# docker compose solo auto-carga .env desde el directorio del compose;
# aquí el compose está en docker/ y el .env vive en la raíz:
# se pasa SIEMPRE con --env-file.
$envContent = Get-Content $EnvFile -Raw
$requiredVars = @("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                  "APP_DB_USER", "APP_DB_PASSWORD", "AI_CALLBACK_KEY",
                  "JWT_SECRET_KEY")
$faltan = $requiredVars | Where-Object { $envContent -notmatch "(?m)^\s*$_\s*=" }
if ($faltan) {
    Write-Host "❌ Faltan variables obligatorias en .env: $($faltan -join ', ')" -ForegroundColor Red
    exit 1
}

# --- Selección de modo ---
$ModoToken = $envContent -match "(?m)^\s*CLOUDFLARE_TUNNEL_TOKEN\s*=\s*\S"
if ($ModoToken) {
    $ComposeFile = $ComposeToken
    if (-not (Test-Path $ComposeFile)) {
        Write-Host "❌ No se encontró el compose en: $ComposeFile" -ForegroundColor Red
        exit 1
    }
    Write-Host "🔑 MODO TOKEN: túnel gestionado por Cloudflare (hostnames fijos) + URL automática extra para el panel." -ForegroundColor Cyan
} else {
    $ComposeFile = $ComposeDev
    if (-not (Test-Path $ComposeFile)) {
        Write-Host "❌ No se encontró el compose en: $ComposeFile" -ForegroundColor Red
        exit 1
    }
    Write-Host "🧪 MODO PRUEBA: sin CLOUDFLARE_TUNNEL_TOKEN en .env. Se usa el stack dev (puertos locales)" -ForegroundColor Yellow
    Write-Host "   y se crean túneles rápidos automáticos para el backend (:8000) y el PANEL (:8501)." -ForegroundColor Yellow
    Write-Host "   Para hostnames fijos, añade CLOUDFLARE_TUNNEL_TOKEN al .env (Zero Trust -> Tunnels)." -ForegroundColor DarkGray
}

# Avisos (no fatales) para el frontend de Vercel
if ($envContent -notmatch "(?m)^\s*CORS_ORIGINS\s*=") {
    Write-Host "⚠️ CORS_ORIGINS no está en .env (el compose usará '*'). Para Vercel conviene:" -ForegroundColor Yellow
    Write-Host "   CORS_ORIGINS=https://<tu-app>.vercel.app" -ForegroundColor Yellow
}
if ($envContent -notmatch "(?m)^\s*N8N_API_KEY\s*=") {
    Write-Host "⚠️ N8N_API_KEY no está en .env (sin ella el panel no podrá hablar con la API de n8n)" -ForegroundColor Yellow
}

# Usuario/base de PostgreSQL leídos del .env (por si no son los por defecto)
$PgUser = "postgres"
if ($envContent -match "(?m)^\s*POSTGRES_USER\s*=\s*(.+?)\s*$") { $PgUser = $Matches[1] }

# ============================================
# 1. DOCKER COMPOSE - Levantar servicios base
# ============================================
Write-Host "`n🐳 Levantando servicios base (postgres, ollama)..." -ForegroundColor Cyan
if ($ModoToken) {
    Write-Host "   ℹ️ Este stack reemplaza el dev: localhost:8000/8501/5432/5678 dejan de publicarse." -ForegroundColor DarkGray
}
docker compose -f $ComposeFile --env-file $EnvFile up -d postgres ollama
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

    if ((Invoke-DockerQuiet exec helpdesk-db pg_isready -U $PgUser) -eq 0) {
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
    if ((Invoke-DockerQuiet cp $SchemaFile "helpdesk-db:/tmp/db_logic.sql") -ne 0) { Write-Host "❌ No se pudo copiar db_logic.sql al contenedor" -ForegroundColor Red; exit 1 }
    if ((Invoke-DockerQuiet exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/db_logic.sql) -ne 0) {
        Write-Host "❌ Error aplicando db_logic.sql. Revisa: docker exec helpdesk-db psql -U $PgUser -d $PgDb -f /tmp/db_logic.sql" -ForegroundColor Red
        exit 1
    }
    Invoke-DockerQuiet exec helpdesk-db rm -f /tmp/db_logic.sql | Out-Null
    Write-Host "✅ Esquema (db_logic.sql) aplicado" -ForegroundColor Green
} else {
    Write-Host "✅ El esquema ya existe; no se toca" -ForegroundColor Green
}

# ============================================
# 2.5.1 MIGRACIONES (database\migraciones\*.sql)
#     Idempotentes y seguras de repetir.
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
        if ((Invoke-DockerQuiet cp $m.FullName "helpdesk-db:/tmp/helpdesk_mig.sql") -ne 0) {
            Write-Host "❌ No se pudo copiar la migración $($m.Name)" -ForegroundColor Red
            exit 1
        }
        if ((Invoke-DockerQuiet exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/helpdesk_mig.sql) -ne 0) {
            Write-Host "❌ Error aplicando la migración $($m.Name)" -ForegroundColor Red
            exit 1
        }
        Invoke-DockerQuiet exec helpdesk-db rm -f /tmp/helpdesk_mig.sql | Out-Null
        Write-Host "   ✅ $($m.Name)" -ForegroundColor Green
    }
}

# ============================================
# 2.6 USUARIO DE BD DE LA APLICACIÓN (mínimo privilegio)
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
'@
$Sql = $Sql.Replace('__USER__', $AppUser).Replace('__PASS__', $EscPass).Replace('__DB__', $PgDb)

$TmpSql = Join-Path $env:TEMP "helpdesk_app_init_cf.sql"
[System.IO.File]::WriteAllText($TmpSql, $Sql, (New-Object System.Text.UTF8Encoding($false)))
try {
    if ((Invoke-DockerQuiet cp $TmpSql "helpdesk-db:/tmp/helpdesk_app_init.sql") -ne 0) { throw "No se pudo copiar el SQL al contenedor" }
    if ((Invoke-DockerQuiet exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/helpdesk_app_init.sql) -ne 0) { throw "Error configurando el rol $AppUser en PostgreSQL" }
    Invoke-DockerQuiet exec helpdesk-db rm -f /tmp/helpdesk_app_init.sql | Out-Null
    Write-Host "✅ Usuario '$AppUser' listo (rol + permisos sobre las tablas de la app)" -ForegroundColor Green
} finally {
    Remove-Item $TmpSql -ErrorAction SilentlyContinue
}

# ============================================
# 2.7 DATOS INICIALES (seed_usuarios.sql)
# ============================================
if (-not (Test-Path $SeedFile)) {
    Write-Host "⚠️ No se encontró seed_usuarios.sql; se omiten los usuarios de prueba" -ForegroundColor Yellow
} else {
    if ((Invoke-DockerQuiet cp $SeedFile "helpdesk-db:/tmp/seed_usuarios.sql") -ne 0) { Write-Host "❌ No se pudo copiar seed_usuarios.sql al contenedor" -ForegroundColor Red; exit 1 }
    if ((Invoke-DockerQuiet exec helpdesk-db psql -v ON_ERROR_STOP=1 -U $PgUser -d $PgDb -f /tmp/seed_usuarios.sql) -ne 0) {
        Write-Host "❌ Error aplicando seed_usuarios.sql" -ForegroundColor Red
        exit 1
    }
    Invoke-DockerQuiet exec helpdesk-db rm -f /tmp/seed_usuarios.sql | Out-Null
    Write-Host "✅ Usuarios de prueba sincronizados (contraseña: password123)" -ForegroundColor Green
}

# ============================================
# 3. STACK COMPLETO + TÚNELES (build incluido)
# ============================================
if ($ModoToken) {
    Write-Host "`n🐳 Construyendo y levantando n8n + backend + streamlit + cloudflared..." -ForegroundColor Cyan
} else {
    Write-Host "`n🐳 Construyendo y levantando n8n + backend + streamlit..." -ForegroundColor Cyan
}
docker compose -f $ComposeFile --env-file $EnvFile up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al construir/levantar la pila" -ForegroundColor Red
    exit 1
}

# ============================================
# 4. HEALTH CHECKS (no fatales)
# ============================================
$UrlApiPublica = $null
$UrlPanelPublica = $null

if ($ModoToken) {
    # 4.1 Backend: espera el healthcheck del compose (dentro del contenedor)
    Write-Host "`n⏳ Esperando al backend (healthcheck interno :8000)..." -ForegroundColor Yellow
    $backendOk = $false
    for ($i = 1; $i -le 45; $i++) {
        $st = (Invoke-DockerOutput inspect -f "{{.State.Health.Status}}" helpdesk-backend | Select-Object -First 1)
        if ("$st".Trim() -eq "healthy") { $backendOk = $true; break }
        Write-Host "   Intento $i/45 - backend aún no está healthy ($("$st".Trim()))..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
    if ($backendOk) {
        Write-Host "✅ Backend healthy (accesible por el túnel en /api/*)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ El backend no reportó healthy a tiempo; revisa: docker logs helpdesk-backend" -ForegroundColor Yellow
    }

    # 4.2 Streamlit: prueba HTTP interna dentro del contenedor (:8501)
    Write-Host "⏳ Esperando a Streamlit (prueba interna :8501)..." -ForegroundColor Yellow
    $streamlitOk = $false
    for ($i = 1; $i -le 30; $i++) {
        $rc = Invoke-DockerQuiet exec helpdesk-streamlit python -c `
            "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501', timeout=3).getcode()==200 else 1)"
        if ($rc -eq 0) { $streamlitOk = $true; break }
        Write-Host "   Intento $i/30 - Streamlit aún no responde..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
    if ($streamlitOk) {
        Write-Host "✅ Streamlit respondiendo (accesible por el túnel en /)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit" -ForegroundColor Yellow
    }

    # 4.3 Túnel token: conexión registrada en el edge
    Write-Host "⏳ Esperando registro del túnel Cloudflare (token)..." -ForegroundColor Yellow
    $tunelOk = $false
    for ($i = 1; $i -le 20; $i++) {
        $logs = (Invoke-DockerOutput logs --tail 100 helpdesk-cloudflared) -join "`n"
        if ($logs -match "Registered tunnel connection") { $tunelOk = $true; break }
        Start-Sleep -Seconds 2
    }
    if ($tunelOk) {
        Write-Host "✅ Túnel con token registrado y conectado al edge" -ForegroundColor Green
    } else {
        Write-Host "⚠️ No se vio 'Registered tunnel connection' (¿token válido? ¿hostnames configurados?)" -ForegroundColor Yellow
        Write-Host "   Revisa: docker logs helpdesk-cloudflared" -ForegroundColor Yellow
    }

    # 4.4 URL AUTOMÁTICA del PANEL: túnel rápido en contenedor (cloudflared-panel)
    Write-Host "⏳ Esperando la URL automática del PANEL (túnel rápido en contenedor)..." -ForegroundColor Yellow
    for ($i = 1; $i -le 20; $i++) {
        $logs = (Invoke-DockerOutput logs --tail 100 helpdesk-cloudflared-panel) -join "`n"
        $m = ($logs | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1)
        if ($m) { $UrlPanelPublica = $m.Matches.Value; break }
        Start-Sleep -Seconds 2
    }
    if ($UrlPanelPublica) {
        if (Test-UrlPublica $UrlPanelPublica) {
            Write-Host "✅ PANEL expuesto automáticamente en: $UrlPanelPublica" -ForegroundColor Green
        } else {
            Write-Host "⚠️ La URL del panel aún no responde (Cloudflare puede tardar unos segundos más)." -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠️ No se obtuvo la URL automática del panel; revisa: docker logs helpdesk-cloudflared-panel" -ForegroundColor Yellow
    }
} else {
    # -------- MODO PRUEBA: puertos locales publicados --------
    Write-Host "`n⏳ Esperando al backend (http://localhost:8000/api/health)..." -ForegroundColor Yellow
    $backendOk = $false
    for ($i = 1; $i -le 45; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 4
            if ($r.StatusCode -eq 200) { $backendOk = $true; break }
        } catch { }
        Write-Host "   Intento $i/45 - backend aún no responde..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
    if ($backendOk) {
        Write-Host "✅ Backend respondiendo en http://localhost:8000" -ForegroundColor Green
    } else {
        Write-Host "⚠️ El backend no respondió a tiempo; revisa: docker logs helpdesk-backend" -ForegroundColor Yellow
    }

    Write-Host "⏳ Esperando a Streamlit (http://localhost:8501)..." -ForegroundColor Yellow
    $streamlitOk = $false
    for ($i = 1; $i -le 30; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8501" -UseBasicParsing -TimeoutSec 4
            if ($r.StatusCode -eq 200) { $streamlitOk = $true; break }
        } catch { }
        Write-Host "   Intento $i/30 - Streamlit aún no responde..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
    if ($streamlitOk) {
        Write-Host "✅ Streamlit respondiendo en http://localhost:8501" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Streamlit no respondió a tiempo; revisa: docker logs helpdesk-streamlit" -ForegroundColor Yellow
    }

    # -------- TÚNELES RÁPIDOS AUTOMÁTICOS (backend + panel) --------
    $ApiPublicaOk = $false
    $UrlApiPublica = Start-TunelRapidoHost -Nombre "API/backend" -UrlLocal "http://localhost:8000" -PrefijoLog "tunel-backend"
    if ($UrlApiPublica) {
        Write-Host "⏳ Esperando HTTP 200 del backend vía Cloudflare ($UrlApiPublica/api/health)..." -ForegroundColor Yellow
        for ($i = 1; $i -le 25; $i++) {
            try {
                $r = Invoke-WebRequest -Uri "$UrlApiPublica/api/health" -UseBasicParsing -TimeoutSec 6
                if ($r.StatusCode -eq 200) { $ApiPublicaOk = $true; break }
            } catch { }
            Write-Host "   Intento $i/25 - backend vía Cloudflare aún no responde 200..." -ForegroundColor DarkGray
            Start-Sleep -Seconds 2
        }
        if ($ApiPublicaOk) {
            Write-Host "✅ Backend expuesto automáticamente en: $UrlApiPublica (HTTP 200)" -ForegroundColor Green
        } else {
            Write-Host "⚠️ La URL pública del backend no confirmó HTTP 200 tras varios reintentos." -ForegroundColor Yellow
            Write-Host "   No se actualizará frontend/js/config.js; revisa: docker logs helpdesk-backend" -ForegroundColor Yellow
        }
    }

    $UrlPanelPublica = Start-TunelRapidoHost -Nombre "Panel/Streamlit" -UrlLocal "http://localhost:8501" -PrefijoLog "tunel-streamlit"
    if ($UrlPanelPublica) {
        if (Test-UrlPublica $UrlPanelPublica) {
            Write-Host "✅ PANEL expuesto automáticamente en: $UrlPanelPublica" -ForegroundColor Green
        } else {
            Write-Host "⚠️ La URL del panel aún no responde (reintenta en unos segundos)." -ForegroundColor Yellow
        }
    }

    # Mantener el frontend de Vercel apuntando al backend actual. Solo se
    # escribe config.js cuando el túnel ya responde HTTP 200, y la base lleva
    # el sufijo /api (FastAPI monta todas las rutas bajo /api).
    if ($NoConfigUpdate) {
        Write-Host "ℹ️  -NoConfigUpdate: frontend/js/config.js sin tocar" -ForegroundColor DarkGray
    } elseif ($ApiPublicaOk -and $UrlApiPublica) {
        Update-ConfigJs -UrlApi "$UrlApiPublica/api"
    } else {
        Write-Host "⚠️  frontend/js/config.js se dejó sin cambios (la URL pública del backend no confirmó HTTP 200)." -ForegroundColor Yellow
        Write-Host "   Edita window.APP_API_BASE_URL a mano o vuelve a ejecutar el script con el túnel ya estable." -ForegroundColor Yellow
    }
}

# ============================================
# 5. RESUMEN
# ============================================
Write-Host "`n📊 Estado de los servicios Docker:" -ForegroundColor Cyan
docker compose -f $ComposeFile --env-file $EnvFile ps --format "table {{.Name}}`t{{.Status}}"

if ($ModoToken) {
    Write-Host "`n✅ Stack de producción por túnel Cloudflare levantado" -ForegroundColor Green
    Write-Host "   API (Vercel) : https://api.tudominio.com/api   <- apunta aquí tu frontend (APP_API_BASE_URL)" -ForegroundColor DarkGray
    Write-Host "   Panel (fijo) : https://panel.tudominio.com     (hostname del túnel con token)" -ForegroundColor DarkGray
    if ($UrlPanelPublica) {
        Write-Host "   Panel (auto) : $UrlPanelPublica  <- URL automática temporal, lista ya" -ForegroundColor Green
    }
    Write-Host "   Hostnames    : configúralos en Cloudflare Zero Trust -> Tunnels -> Public Hostnames" -ForegroundColor DarkGray
    Write-Host "                  api.tudominio.com   -> http://backend:8000" -ForegroundColor DarkGray
    Write-Host "                  panel.tudominio.com -> http://streamlit:8501" -ForegroundColor DarkGray
    Write-Host "`n⚠️  Modo túnel: SIN puertos locales. localhost:8000 / :8501 / :5678 / :5432 / :11434" -ForegroundColor Yellow
    Write-Host "   NO responden en el host; n8n/pg/ollama solo son accesibles desde la red interna." -ForegroundColor Yellow
    Write-Host "   Para volver al entorno dev: .\Iniciar.ps1" -ForegroundColor Yellow
    Write-Host "`n📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-cloudflared | docker logs -f helpdesk-cloudflared-panel" -ForegroundColor Yellow
} else {
    Write-Host "`n✅ MODO PRUEBA levantado (stack dev + túneles rápidos automáticos)" -ForegroundColor Green
    if ($UrlApiPublica) {
        Write-Host "   API  pública : $UrlApiPublica/api   (backend; frontend Vercel apunta aquí)" -ForegroundColor Green
        Write-Host "   Docs         : $UrlApiPublica/docs" -ForegroundColor DarkGray
    }
    if ($UrlPanelPublica) {
        Write-Host "   Panel público: $UrlPanelPublica      (Streamlit, login del panel)" -ForegroundColor Green
    }
    Write-Host "   Local        : http://localhost:8000  |  http://localhost:8501" -ForegroundColor DarkGray
    Write-Host "`n⚠️  URLs trycloudflare TEMPORALES: cambian en cada ejecución del script." -ForegroundColor Yellow
    Write-Host "   Túneles en segundo plano (logs en ~\.cloudflared\tunel-backend.* / tunel-streamlit.*)." -ForegroundColor DarkGray
    Write-Host "   Parar los túneles : Get-Process cloudflared | Stop-Process" -ForegroundColor DarkGray
    Write-Host "   Hostnames fijos   : añade CLOUDFLARE_TUNNEL_TOKEN al .env y vuelve a ejecutar este script." -ForegroundColor DarkGray
    Write-Host "`n📋 Logs: docker logs -f helpdesk-backend | docker logs -f helpdesk-streamlit" -ForegroundColor Yellow
}
