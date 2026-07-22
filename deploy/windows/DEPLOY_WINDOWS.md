# Deploy no Windows Server (NSSM + Caddy)

O VeraciBot roda como três serviços do Windows: `veracibot-bot` (agente),
`veracibot-web` (site FastAPI na porta 8000, só localhost) e `veracibot-caddy`
(HTTPS público em veraci.bot). Serviços sobem no boot e reiniciam sozinhos se caírem.

## 1. Pré-requisitos (PowerShell como Administrador)

```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install NSSM.NSSM
winget install CaddyServer.Caddy
```

Feche e reabra o PowerShell depois, para o PATH atualizar.

## 2. Clonar e configurar

```powershell
cd C:\
git clone https://github.com/ralbuque/veracibot.git
cd C:\veracibot
copy .env.example .env
notepad .env   # cole as chaves do X e da Anthropic
```

Se preferir, copie o `.env` e o `veracibot.db` da sua máquina atual (pare o bot
no Mac antes — dois bots com as mesmas chaves duplicam replies e gastam cota).

## 3. Instalar os serviços

```powershell
cd C:\veracibot\deploy\windows
powershell -ExecutionPolicy Bypass -File .\install-services.ps1
```

O script cria o venv, instala dependências, registra os três serviços, abre as
portas 80/443 no firewall e inicia tudo.

## 4. DNS

No provedor do domínio, crie um registro **A** de `veraci.bot` (e `www`)
apontando para o IP público do servidor. O Caddy emite o certificado HTTPS
automaticamente na primeira visita (o DNS precisa estar propagado).

## 5. Dia a dia

```powershell
Get-Service veracibot-*                 # status
nssm restart veracibot-bot             # reiniciar um serviço
nssm stop veracibot-bot                # parar ("desligar" o bot)
Get-Content C:\veracibot\logs\bot.log -Tail 50 -Wait   # acompanhar log
```

Atualizar o código:

```powershell
cd C:\veracibot
git pull
.venv\Scripts\pip.exe install -r requirements.txt
nssm restart veracibot-bot
nssm restart veracibot-web
```

## 6. Backup do banco (recomendado)

Tarefa agendada diária copiando o SQLite:

```powershell
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
  -Argument '/c copy C:\veracibot\veracibot.db C:\veracibot\backups\veracibot-%date:~-4%%date:~3,2%%date:~0,2%.db'
$trigger = New-ScheduledTaskTrigger -Daily -At 4am
New-Item -ItemType Directory -Force C:\veracibot\backups
Register-ScheduledTask -TaskName "VeraciBot Backup" -Action $action -Trigger $trigger
```

## Solução de problemas

- **Site não abre em https://veraci.bot**: confira o DNS (`nslookup veraci.bot`),
  se as portas 80/443 estão liberadas também no roteador/provedor, e o log
  `logs\caddy.log`.
- **Bot não posta**: veja `logs\bot.log`; erros 401/403 são credenciais/permissões
  do app no portal do X.
- **Remover tudo**: `nssm remove veracibot-bot confirm` (idem para web e caddy).
