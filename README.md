# VeraciBot — The Internet Tribunal ⚖️

Agente que monitora menções a **@tribunalbot** no X, interpreta a thread da disputa
e emite um julgamento com IA (Claude): quem está certo, quem está errado e por quê.

## Arquitetura

```
poll menções (@tribunalbot) ──► reconstruir thread (conversation_id)
        ▲                                   │
        │ since_id                          ▼
     SQLite ◄── salvar caso ◄── juiz (Claude, JSON) ──► reply na thread
```

- `src/veracibot/x_client.py` — X API v2 via tweepy: busca de menções, reconstrução de thread, post de reply
- `src/veracibot/judge.py` — prompt do juiz + parsing do veredito JSON
- `src/veracibot/reply.py` — formata o veredito em ≤280 caracteres
- `src/veracibot/store.py` — SQLite: casos, vereditos, threads e `since_id`
- `src/veracibot/main.py` — loop de polling

## Setup

```bash
cp .env.example .env   # preencha as credenciais
./bin/veracibotctl start
```

O `veracibotctl` cria o venv e instala dependências automaticamente na primeira execução.

```bash
./bin/veracibotctl start          # inicia bot + site em background
./bin/veracibotctl stop           # para tudo
./bin/veracibotctl restart bot    # reinicia só o bot (após mudar código/.env)
./bin/veracibotctl status         # está rodando?
./bin/veracibotctl logs web       # acompanha um log ao vivo (Ctrl+C para sair)
```

Os comandos aceitam o alvo `bot`, `web` ou `all` (padrão: `all`).

## Site (veraci.bot)

App FastAPI em `src/veracibot/web/` lendo o SQLite em modo somente-leitura.
Landing bilíngue (pt em `/`, en em `/en`), ranking público (`/ranking`) e casos
julgados (`/casos`). Porta configurável via `WEB_PORT` no `.env` (padrão 8000).
Para publicar em https://veraci.bot, aponte um proxy/túnel (ex.: Cloudflare
Tunnel) para `localhost:8000`.

## Deploy em produção (Windows Server)

Guia completo em [`deploy/windows/DEPLOY_WINDOWS.md`](deploy/windows/DEPLOY_WINDOWS.md):
serviços do Windows via NSSM (bot + site) e Caddy servindo https://veraci.bot.

Execução em foreground (debug): `source .venv/bin/activate && python -m src.veracibot.main`

### Credenciais necessárias

1. **X API (plano Basic)** — crie um app em https://developer.x.com com permissão
   *Read and Write*, gere Bearer Token + API Key/Secret + Access Token/Secret.
2. **Anthropic** — chave em https://console.anthropic.com.

## Comportamento e limites

- Um `conversation_id` é julgado **uma única vez** (idempotência) e menções do
  próprio bot são ignoradas (proteção contra loop).
- `POST_REPLIES=false` roda em modo observação: julga e salva sem postar.
- Plano Basic: busca cobre só os **últimos 7 dias** e há teto mensal de leitura —
  `MAX_THREAD_TWEETS` limita o custo por caso.
- O juiz recusa casos sem disputa clara, pedidos de assédio ou acusações graves.

## Convites

Com `INVITE_ONLY=true` no `.env`, só membros convidados abrem casos (controle do
consumo de cota da X API). Não-convidados recebem o aviso uma única vez. Convites:

- **Dono**: a conta @veracibot tweeta `Convido @fulano` — sem limite.
- **Membros**: respondem `@veracibot convido @fulano` — cada membro tem **5 convites**.
- Convidado recebe boas-vindas com link para o site; quem já é membro não consome convite.

## Pontuação (fact-check)

Todo handle começa com **1000 pontos**. Chamar o bot custa 1 ponto (exige saldo ≥ 1;
estornado se houver erro interno). O juiz identifica os papéis: autor da afirmação,
contestador e a posição do chamador (afirma / contesta / neutro).

**Chamador é parte** (afirma ou contesta; sem contestador na thread, chamar = contestar):

| | Chamador | Outro lado |
|---|---|---|
| Certo | +11 (líquido +10) | +10 |
| Errado | −10 (total −11) | −11 |

**Chamador neutro** (terceiro perguntando quem está certo): paga só o custo;
lado certo +10, lado errado −10.

Parcial / indeterminado / recusado: ninguém ganha nem perde; fica só o custo do chamador.

**Disputas** usam a mesma matriz, com vencedor/perdedor no lugar de certo/errado
(o juiz indica o perdedor principal). Empate: só o custo do chamador.

## Fase de provas (contradição factual)

Quando as partes se contradizem sobre um fato **decisivo** (ex.: "você prometeu por
e-mail" × "nunca mandei esse e-mail"), o juiz não decide às cegas: identifica quem
tem o **ônus da prova** (quem alega o fato positivo — prova negativa não se exige) e
pede na thread link ou print, com prazo de **48h**. Nova menção na conversa reabre o
julgamento com a thread atualizada — o juiz **lê as imagens anexadas** (prints valem
como indício não autenticável; links públicos pesam mais) e decide por preponderância
de evidências. Prazo vencido sem prova: a alegação é julgada improcedente e o
alegante perde. Pontos e composição só são aplicados no veredito final.

## Recurso (votação popular)

O **perdedor** pode apelar uma vez por caso, respondendo na thread com menção ao bot
expressando discordância (interpretada por IA). Custa **5 pontos**. O bot abre a
**votação do júri popular por 24h**: membros votam respondendo na thread
`@veracibot voto @fulano`. Só contam votos de **membros convidados** (imune a spam
de contas fake); as partes não votam; cada membro tem 1 voto e pode trocá-lo até o
fim. Com quorum (`APPEAL_QUORUM` no `.env`, padrão 5) e maioria pelo apelante, a
sentença é **reformada**: pontuação invertida (cada parte recebe o resultado da
outra), os 5 pontos voltam e composição pendente é cancelada. Empate, minoria ou
falta de quorum: sentença **mantida** e os 5 pontos não retornam. O acórdão sai
como reply do anúncio da votação.

## Composição

Quando há vencedor e perdedor claros (caso leve), o veredito propõe composição:
desculpas + reparação (disputa) ou retratação pública (fact-check falso). Se o
**vencedor** confirmar o cumprimento — respondendo na thread com menção ao bot em
até **7 dias** — o perdedor recupera **8 pontos** (fica −3 líquido). A confirmação
é interpretada por IA; casos **graves** (violência, crime, ameaça) não recebem
proposta: o tribunal recomenda procurar a justiça real.
Saldos em `scores`, histórico auditável em `ledger`. Pontuação de disputas: fase 2.

## Próximos passos

- [ ] Migrar SQLite → Postgres quando o site entrar
- [ ] Site https://veraci.bot (casos resolvidos + estatísticas; `thread_json` já é salvo para isso)
- [ ] Fila/retry para falhas de rate limit
- [ ] Dashboard de moderação antes do reply automático
