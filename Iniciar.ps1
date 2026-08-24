# Iniciar.ps1
# Script seguro: Verifica y arranca contenedores + backend SIN borrar nada

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackendPath = Join-Path $ProjectRoot "backend"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"

Write-Host "`n🚀 Iniciando HelpDesk (Contenedores + Backend)..." -ForegroundColor Cyan

# ============================================
# 1. DOCKER COMPOSE - Levantar solo lo necesario
# ============================================
if (-not (Test-Path $ComposeFile)) {
    Write-Host "❌ No se encontró docker-compose.yml en: $ComposeFile" -ForegroundColor Red
    exit 1
}

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
Write-Host "⏳ Esperando a que PostgreSQL esté disponible..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$pgReady = $false

while (-not $pgReady -and $attempt -lt $maxAttempts) {
    $attempt++
    Start-Sleep -Seconds 2

    $null = docker exec helpdesk-db pg_isready -U postgres 2>&1
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

Write-Host "✅ PostgreSQL está listo y aceptando conexiones" -ForegroundColor Green

# Mostrar estado de contenedores
Write-Host "`n📊 Estado de los servicios Docker:" -ForegroundColor Cyan
docker compose -f $ComposeFile ps --format "table {{.Name}}`t{{.Status}}`t{{.Ports}}"

# ============================================
# 3. BACKEND - Activar venv y ejecutar Uvicorn
# ============================================
$VenvActivate = Join-Path $BackendPath ".venv\Scripts\Activate.ps1"
$MainPy = Join-Path $BackendPath "main.py"

if (-not (Test-Path $VenvActivate)) {
    Write-Host "`n❌ No se encontró el entorno virtual en: $VenvActivate" -ForegroundColor Red
    Write-Host "   Crea uno con: python -m venv .venv dentro de la carpeta backend" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $MainPy)) {
    Write-Host "`n❌ No se encontró main.py en: $BackendPath" -ForegroundColor Red
    exit 1
}

Write-Host "`n🐍 Activando entorno virtual y ejecutando Uvicorn..." -ForegroundColor Cyan
Write-Host "   Ruta: $BackendPath" -ForegroundColor DarkGray
Write-Host "   URL:  http://localhost:8000" -ForegroundColor DarkGray
Write-Host "   Docs: http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host "`n💡 Presiona CTRL+C para detener el servidor backend`n" -ForegroundColor Yellow

& $VenvActivate
Set-Location $BackendPath
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000