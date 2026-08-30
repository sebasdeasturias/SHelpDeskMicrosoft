# Iniciar.ps1
# Script seguro: Verifica y arranca toda la infraestructura de SHelpDesk SIN borrar nada
#   PostgreSQL (pgvector) + Ollama + n8n + Backend FastAPI + Streamlit

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
$requiredVars = @("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "JWT_SECRET_KEY",
                  "N8N_BASIC_AUTH_USER", "N8N_BASIC_AUTH_PASSWORD")
$faltan = $requiredVars | Where-Object { $envContent -notmatch "(?m)^\s*$_\s*=" }
if ($faltan) {
    Write-Host "❌ Faltan variables obligatorias en .env: $($faltan -join ', ')" -ForegroundColor Red
    exit 1
}

# Usuario de PostgreSQL leído del .env (por si no es 'postgres')
$PgUser = "postgres"
if ($envContent -match "(?m)^\s*POSTGRES_USER\s*=\s*(.+?)\s*$") { $PgUser = $Matches[1] }

# ============================================
# 1. DOCKER COMPOSE - Levantar la pila base
# ============================================
Write-Host "`n🐳 Verificando y levantando contenedores Docker..." -ForegroundColor Cyan
# up -d es idempotente: si ya están corriendo, no hace nada. Si están parados, los inicia.
docker compose -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al iniciar los contenedores" -ForegroundColor Red
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
