# Instala o VeraciBot (bot + site + Caddy) como servicos do Windows via NSSM.
# Pre-requisitos: Python 3.10+, NSSM e Caddy no PATH. Rodar como ADMINISTRADOR.
#   winget install Python.Python.3.12
#   winget install NSSM.NSSM
#   winget install CaddyServer.Caddy
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Venv = Join-Path $Root ".venv"
$Logs = Join-Path $Root "logs"
$Python = Join-Path $Venv "Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

if (!(Test-Path (Join-Path $Root ".env"))) {
    Write-Error ".env nao encontrado em $Root - copie de .env.example e preencha as chaves."
}

# Ambiente virtual + dependencias
if (!(Test-Path $Python)) {
    Write-Host "Criando venv e instalando dependencias..."
    py -3 -m venv $Venv
    & "$Venv\Scripts\pip.exe" install --quiet --upgrade pip
    & "$Venv\Scripts\pip.exe" install --quiet -r (Join-Path $Root "requirements.txt")
}

function Install-VbService {
    param($Name, $Program, $Arguments, $AppDir, $Log)
    if (Get-Service $Name -ErrorAction SilentlyContinue) {
        Write-Host "[$Name] ja existe; atualizando configuracao..."
        nssm stop $Name | Out-Null
    } else {
        nssm install $Name $Program $Arguments
    }
    nssm set $Name Application $Program | Out-Null
    nssm set $Name AppParameters $Arguments | Out-Null
    nssm set $Name AppDirectory $AppDir | Out-Null
    nssm set $Name AppStdout $Log | Out-Null
    nssm set $Name AppStderr $Log | Out-Null
    nssm set $Name AppRotateFiles 1 | Out-Null
    nssm set $Name AppRotateBytes 10485760 | Out-Null
    nssm set $Name Start SERVICE_AUTO_START | Out-Null
    nssm set $Name AppExit Default Restart | Out-Null
    nssm set $Name AppRestartDelay 5000 | Out-Null
}

Install-VbService -Name "veracibot-bot" -Program $Python `
    -Arguments "-m src.veracibot.main" -AppDir $Root -Log (Join-Path $Logs "bot.log")

Install-VbService -Name "veracibot-web" -Program $Python `
    -Arguments "-m uvicorn src.veracibot.web.app:app --host 127.0.0.1 --port 8000" `
    -AppDir $Root -Log (Join-Path $Logs "web.log")

$Caddy = (Get-Command caddy).Source
Install-VbService -Name "veracibot-caddy" -Program $Caddy `
    -Arguments "run --config `"$PSScriptRoot\Caddyfile`"" `
    -AppDir $PSScriptRoot -Log (Join-Path $Logs "caddy.log")

# Firewall: HTTP/HTTPS para o Caddy
if (!(Get-NetFirewallRule -DisplayName "VeraciBot Web" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "VeraciBot Web" -Direction Inbound `
        -Protocol TCP -LocalPort 80, 443 -Action Allow | Out-Null
    Write-Host "Regra de firewall criada (portas 80/443)."
}

nssm start veracibot-bot
nssm start veracibot-web
nssm start veracibot-caddy

Write-Host ""
Write-Host "Servicos instalados e iniciados:"
Get-Service veracibot-* | Format-Table Name, Status
Write-Host "Site local: http://localhost:8000 | Publico: https://veraci.bot (apos DNS)"
