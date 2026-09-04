# docker/iniciar-tunel-prueba.ps1 — SHelpDesk Microsoft
# Túnel RÁPIDO de Cloudflare (trycloudflare.com) para exponer el backend local.
#
#   Navegador (Vercel) -> https://<subdominio>.trycloudflare.com/api -> Cloudflare edge
#        -> cloudflared (esta máquina) -> http://localhost:8000 (helpdesk-backend)
#
# * URL TEMPORAL: cambia cada vez que se reinicia el túnel (modo prueba, sin cuenta).
# * Si el backend corre en Docker (docker/docker-compose.yml) el puerto 8000 ya
#   está publicado en el host; si corres el backend fuera de Docker, arráncalo tú.
# * Al terminar ACTUALIZA frontend/js/config.js con la nueva URL (el frontend de
#   Vercel se despliega desde GitHub con root folder frontend/).
#
# Uso:
#   .\docker\iniciar-tunel-prueba.ps1                  # túnel + actualiza config.js
#   .\docker\iniciar-tunel-prueba.ps1 -NoConfigUpdate  # solo túnel, sin tocar config.js
#   .\docker\iniciar-tunel-prueba.ps1 -Restart         # mata el túnel previo y arranca uno nuevo

param([switch]$NoConfigUpdate, [switch]$Restart)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# FIX PowerShell 5.1: la salida por stderr de comandos nativos con
# $ErrorActionPreference="Stop" genera NativeCommandError fantasma.
# ------------------------------------------------------------------
function Invoke-Quiet {
    param([scriptblock]$Cmd)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Cmd } finally { $ErrorActionPreference = $prev }
}

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ConfigJs = Join-Path $ProjectRoot "frontend\js\config.js"
$CfDir = Join-Path $env:USERPROFILE ".cloudflared"
$Exe = Join-Path $CfDir "cloudflared.exe"
$LogOut = Join-Path $CfDir "quick-tunnel.out.log"
$LogErr = Join-Path $CfDir "quick-tunnel.err.log"

Write-Host "`n🔗 Túnel de prueba Cloudflare para el backend SHelpDesk..." -ForegroundColor Cyan

# ============================================
# 0. REQUISITOS: backend arriba + cloudflared disponible
# ============================================
try {
    $null = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Backend local respondiendo en http://localhost:8000" -ForegroundColor Green
} catch {
    Write-Host "❌ El backend no responde en http://localhost:8000/api/health" -ForegroundColor Red
    Write-Host "   Levántalo primero:  docker compose -f docker/docker-compose.yml --env-file .env up -d backend" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $Exe)) {
    Write-Host "⬇️  Descargando cloudflared (Windows amd64)..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $CfDir -Force | Out-Null
    Invoke-Quiet { Invoke-WebRequest `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $Exe -UseBasicParsing -TimeoutSec 120 }
    if (-not (Test-Path $Exe)) { Write-Host "❌ No se pudo descargar cloudflared" -ForegroundColor Red; exit 1 }
}

# ============================================
# 1. ARRANCAR (o reutilizar) el túnel rápido
# ============================================
if ($Restart) {
    Write-Host "♻️  Reiniciando túnel previo..." -ForegroundColor Yellow
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 1
}

$proc = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "ℹ️  Ya hay un túnel corriendo (PID $($proc.Id -join ', ')); reutilizando..." -ForegroundColor DarkGray
} else {
    Write-Host "🚀 Arrancando cloudflared tunnel --url http://localhost:8000 ..." -ForegroundColor Cyan
    Remove-Item $LogOut, $LogErr -ErrorAction SilentlyContinue
    $p = Invoke-Quiet { Start-Process -FilePath $Exe `
        -ArgumentList @("tunnel", "--url", "http://localhost:8000", "--no-autoupdate") `
        -WindowStyle Hidden -RedirectStandardOutput $LogOut -RedirectStandardError $LogErr -PassThru }
    Write-Host "   PID: $($p.Id) (queda corriendo en segundo plano)" -ForegroundColor DarkGray
}

# ============================================
# 2. EXTRAER la URL pública de los logs
# ============================================
$publicUrl = $null
for ($i = 1; $i -le 30; $i++) {
    $logs = @()
    if (Test-Path $LogErr) { $logs += Get-Content $LogErr -ErrorAction SilentlyContinue }
    if (Test-Path $LogOut) { $logs += Get-Content $LogOut -ErrorAction SilentlyContinue }
    $m = ($logs | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1)
    if ($m) { $publicUrl = $m.Matches.Value; break }
    Start-Sleep -Seconds 1
}
if (-not $publicUrl) {
    Write-Host "❌ No se obtuvo URL del túnel en 30s. Revisa: $LogErr" -ForegroundColor Red
    exit 1
}

# ============================================
# 3. VERIFICAR el enlace completo por la URL pública
# ============================================
$okPublico = $false
try {
    $r = Invoke-WebRequest -Uri "$publicUrl/api/health" -UseBasicParsing -TimeoutSec 25
    if ($r.StatusCode -eq 200) { $okPublico = $true }
} catch { }
if ($okPublico) {
    Write-Host "✅ Backend accesible públicamente: $publicUrl/api/health -> 200" -ForegroundColor Green
} else {
    Write-Host "⚠️  La URL pública aún no responde; reintentando o revisa: $LogErr" -ForegroundColor Yellow
}

# ============================================
# 4. ACTUALIZAR frontend/js/config.js (deploy de Vercel)
# ============================================
if ($NoConfigUpdate) {
    Write-Host "ℹ️  -NoConfigUpdate: frontend/js/config.js sin tocar" -ForegroundColor DarkGray
} else {
    if (-not (Test-Path $ConfigJs)) {
        Write-Host "⚠️  No se encontró $ConfigJs" -ForegroundColor Yellow
    } else {
        $raw = [System.IO.File]::ReadAllText($ConfigJs)
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        $pattern = "(?m)^window\.APP_API_BASE_URL\s*=\s*'[^']*';.*$"
        $replacement = "window.APP_API_BASE_URL = '$publicUrl/api'; // TEMPORAL (prueba de conexión; túnel del $stamp)"
        $nuevo = [regex]::Replace($raw, $pattern, $replacement)
        if ($nuevo -eq $raw -and $raw -notmatch [regex]::Escape($publicUrl)) {
            Write-Host "⚠️  No encontré la línea window.APP_API_BASE_URL en config.js; edítala a mano:" -ForegroundColor Yellow
            Write-Host "   $replacement" -ForegroundColor Yellow
        } else {
            $hasBom = $false
            $bytes = [System.IO.File]::ReadAllBytes($ConfigJs)
            if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $hasBom = $true }
            $enc = New-Object System.Text.UTF8Encoding($hasBom)
            [System.IO.File]::WriteAllText($ConfigJs, $nuevo, $enc)
            Write-Host "✅ frontend/js/config.js actualizado con $publicUrl/api" -ForegroundColor Green
            Write-Host "   Haz 'git add frontend/js/config.js && git commit && git push' para que Vercel redespliegue." -ForegroundColor DarkGray
        }
    }
}

# ============================================
# 5. RESUMEN
# ============================================
Write-Host "`n📊 MONTAJE DE PRUEBA LISTO" -ForegroundColor Cyan
Write-Host "   URL pública API : $publicUrl/api" -ForegroundColor Green
Write-Host "   Docs (Swagger)  : $publicUrl/docs" -ForegroundColor DarkGray
Write-Host "   Backend local   : http://localhost:8000  (docker: helpdesk-backend)" -ForegroundColor DarkGray
Write-Host "   Logs del túnel  : $LogErr" -ForegroundColor DarkGray
Write-Host "   Parar el túnel  : Get-Process cloudflared | Stop-Process" -ForegroundColor DarkGray
Write-Host "`n⚠️  La URL cambia en cada reinicio del túnel (modo prueba). Para una URL fija," -ForegroundColor Yellow
Write-Host "   usa docker/docker-compose.cloudflared.yml (túnel con token + tu dominio)." -ForegroundColor Yellow
