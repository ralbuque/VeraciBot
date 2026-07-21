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
./bin/veracibotctl start     # inicia em background (daemon)
./bin/veracibotctl stop      # para
./bin/veracibotctl restart   # reinicia (após mudar código ou .env)
./bin/veracibotctl status    # está rodando?
./bin/veracibotctl logs      # acompanha o log ao vivo (Ctrl+C para sair)
```

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
Saldos em `scores`, histórico auditável em `ledger`. Pontuação de disputas: fase 2.

## Próximos passos

- [ ] Migrar SQLite → Postgres quando o site entrar
- [ ] Site https://veraci.bot (casos resolvidos + estatísticas; `thread_json` já é salvo para isso)
- [ ] Fila/retry para falhas de rate limit
- [ ] Dashboard de moderação antes do reply automático
