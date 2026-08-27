"""Textos do site em pt-BR e inglês."""

T = {
    "pt": {
        "title": "VeraciBot — O Tribunal da Internet",
        "nav_ranking": "Ranking",
        "nav_cases": "Casos",
        "hero_title": "O Tribunal da Internet",
        "hero_sub": "Duas pessoas discutindo no X? Mencione @veracibot na thread e um juiz de IA "
                    "analisa os argumentos, verifica os fatos e declara quem tem razão — em público.",
        "hero_cta": "Mencione @veracibot numa thread para abrir um caso",
        "promo_title": "🔍 Em Busca da Verdade",
        "promo_sub": "Aponte o máximo de fake news em uma semana e ganhe até "
                     "3.000 microbitcoins (~R$ 1.000). São 5.000 μBTC em prêmios "
                     "(~R$ 2.500) para os 5 maiores caçadores de mentiras do X.",
        "promo_how_title": "Como participar",
        "promo_steps": [
            "Tenha o selo azul (X Premium) na sua conta.",
            "Siga @veracibot no X.",
            "Poste: \"@veracibot quero participar\" — o bot confirma sua inscrição na hora.",
            "Para receber o prêmio, os ganhadores precisam ter uma carteira Bitcoin "
            "com endereço na mainnet. O pagamento será feito no dia 31 de agosto.",
        ],
        "promo_rules_title": "Como funciona a disputa",
        "promo_rules": [
            "Em 16/08 às 0h, os pontos de todos os participantes são zerados em 1.000.",
            "Durante a semana, aponte fake news mencionando @veracibot na thread ou no quote da afirmação. Checagem verdadeira ou falsa movimenta pontos conforme as regras do tribunal.",
            "Em 22/08 às 24h, quem tiver mais pontos vence.",
        ],
        "promo_prizes_title": "Premiação (em microbitcoins)",
        "promo_prizes": [
            ("🥇 1º lugar", "3.000 μBTC (~R$ 1.000 / US$ 150)"),
            ("🥈 2º lugar", "1.000 μBTC"),
            ("🥉 3º lugar", "500 μBTC"),
            ("4º e 5º lugares", "250 μBTC cada"),
        ],
        "promo_cta": "Quero participar",
        "promo_count_many": "pessoas já estão inscritas — participe você também!",
        "promo_count_one": "pessoa já está inscrita — participe você também!",
        "winners_title": "Vencedores da promoção Em Busca da Verdade",
        "winners_note": "Placar congelado no encerramento (22/08 às 24h). Prêmios "
                        "pagos em microbitcoins no dia 31/08. Obrigado a todos os "
                        "caçadores da verdade — vem aí o Ciclo de Debates!",
        "promo_note": "Total de 5.000 μBTC (~R$ 2.500 / US$ 320) em prêmios. "
                      "Vencedores anunciados pelo @veracibot ao fim da promoção.",
        "why_title": "O que são microcausas?",
        "why_p1": "Ninguém aciona um tribunal por um prato quebrado, uma aposta de R$ 50 "
                  "ou uma promessa desfeita por e-mail. O custo, o tempo e a burocracia "
                  "da justiça tornam essas causas minúsculas — as microcausas — órfãs "
                  "de julgamento: ficam sem juiz, sem veredito e sem reparação.",
        "why_p2": "O mesmo vale para a verdade: acionar um tribunal porque alguém contou "
                  "uma mentira seria um excesso — mas deixá-la circular sem resposta "
                  "também tem custo. A verificação de fatos é a microcausa por "
                  "excelência, e aqui ela ganha juiz, evidências e veredito.",
        "why_p3": "O VeraciBot é o primeiro tribunal de microcausas: um juiz de IA que "
                  "resolve em minutos, em público e de graça, as pendências que nenhum "
                  "tribunal real pegaria. Não competimos com o sistema judiciário — "
                  "cuidamos justamente do que fica fora do alcance dele. Casos sérios "
                  "são sempre encaminhados à justiça de verdade.",
        "how_title": "Como funciona",
        "how_1_t": "1. Convoque o tribunal",
        "how_1": "Responda a qualquer thread com @veracibot. Custa 1 ponto do seu saldo.",
        "how_2_t": "2. O juiz analisa",
        "how_2": "A IA lê a thread inteira, classifica o caso — disputa ou checagem de fato — "
                 "e pesquisa na web quando precisa verificar afirmações.",
        "how_3_t": "3. Veredito público",
        "how_3": "O veredito sai como resposta na própria thread, com justificativa e o placar "
                 "de pontos de cada envolvido.",
        "scoring_title": "Pontuação",
        "scoring_intro": "Todo mundo começa com 1.000 pontos. Chamar o bot custa 1 ponto.",
        "scoring_rows": [
            ("Você aponta uma afirmação como falsa e o tribunal confirma", "+10 líquido (custo devolvido); o autor da afirmação perde 11"),
            ("A afirmação que você apontou era verdadeira", "você perde 11; o autor ganha 10"),
            ("Indeterminado ou caso arquivado", "só o custo de 1 ponto"),
            ("Disputas e debates: você é parte e vence / perde", "+10 líquido / −11; terceiro neutro paga só o custo e os lados disputam ±10"),
            ("Recurso (só o perdedor, 1 vez): enquete pública de 24h no X decide", "custa 5 pontos; voltam se a sentença for reformada"),
        ],
        "process_title": "O processo completo",
        "process_steps": [
            "Convite: só membros convidados abrem casos — cada membro pode convidar 5 pessoas.",
            "Abertura: mencione @veracibot na thread (custa 1 ponto do saldo). Debates e disputas podem ser abertos formalmente: \"vamos iniciar um debate entre @a e @b sobre X\".",
            "Instrução: se as partes se contradizem sobre um fato decisivo, o juiz pede provas (links ou prints) em 48h — quem alega, prova.",
            "Sentença: veredito público com justificativa e placar de pontos.",
            "Recurso: o perdedor pode apelar — uma enquete pública de 24h no X decide.",
        ],
        "stats_cases": "casos julgados",
        "stats_fact": "checagens de fato",
        "stats_disputes": "disputas",
        "stats_users": "cidadãos no tribunal",
        "ranking_title": "Ranking público",
        "ranking_sub": "Saldo de pontos de cada cidadão do tribunal.",
        "ranking_tab_promo": "🔍 Promoção",
        "ranking_tab_all": "Geral",
        "ranking_promo_sub": "Somente inscritos na promoção Em Busca da Verdade. "
                             "Os 5 primeiros ao fim de 22/08 levam os prêmios.",
        "ranking_promo_notstarted": "⏳ A contagem oficial começa em 16/08 às 0h, "
                                    "quando os pontos de todos os inscritos serão "
                                    "zerados em 1.000. Inscreva-se desde já!",
        "col_pos": "#",
        "col_user": "Usuário",
        "col_points": "Pontos",
        "cases_title": "Casos julgados",
        "cases_sub": "Vereditos emitidos pelo tribunal, do mais recente ao mais antigo.",
        "case_dispute": "Disputa",
        "case_fact": "Checagem de fato",
        "case_debate": "Debate",
        "case_declined": "Arquivado",
        "case_evidence": "Aguardando provas",
        "winner": "Vencedor",
        "tie": "Empate",
        "view_on_x": "Ver a thread no X",
        "case_label": "Caso",
        "back_to_cases": "← Todos os casos",
        "thread_title": "Autos (thread)",
        "ledger_title": "Movimentação de pontos",
        "comp_title": "Composição",
        "appeal_title": "Recurso",
        "votes_label": "votos",
        "deadline_label": "prazo",
        "onus_label": "Ônus da prova",
        "grave_warning": "Caso sério: o tribunal recomendou procurar a justiça.",
        "st_pendente": "pendente",
        "st_cumprida": "cumprida — 8 pontos devolvidos",
        "st_expirada": "expirada",
        "st_cancelada_recurso": "cancelada pelo recurso",
        "st_aberta": "votação em curso",
        "st_mantida": "sentença mantida",
        "st_reformada": "sentença reformada pelo júri",
        "nav_lawyers": "Advogados",
        "law_title": "Advogados parceiros",
        "law_sub": "Quando um caso é sério demais para o tribunal — ou termina sem acordo — "
                   "o VeraciBot indica profissionais de verdade. Estes são os parceiros "
                   "aprovados, por estado.",
        "law_all_ufs": "Todas as UFs",
        "law_filter": "Filtrar",
        "law_col_name": "Escritório / Advogado(a)",
        "law_col_city": "Cidade",
        "law_col_areas": "Áreas",
        "law_col_contact": "Contato",
        "law_empty": "Nenhum parceiro cadastrado nesta UF ainda.",
        "law_cta_title": "É advogado(a)?",
        "law_cta": "Receba indicações de microcausas que escalam para a justiça real.",
        "law_cta_link": "Cadastre seu escritório →",
        "nav_login": "Entrar",
        "claims_title": "afirmações julgadas separadamente",
        "verdict_true": "✅ Verdadeiro",
        "verdict_false": "❌ Falso",
        "verdict_partial": "⚠️ Parcialmente verdadeiro",
        "verdict_undetermined": "❓ Indeterminado",
        "no_cases": "Nenhum caso julgado ainda. Seja o primeiro: mencione @veracibot numa thread.",
        "no_scores": "Ninguém pontuou ainda.",
        "footer_note": "Vereditos gerados por IA. Podem conter erros — leia a justificativa e as fontes.",
        "footer_report": "Reportar problema",
    },
    "en": {
        "title": "VeraciBot — The Internet Tribunal",
        "nav_ranking": "Leaderboard",
        "nav_cases": "Cases",
        "hero_title": "The Internet Tribunal",
        "hero_sub": "Two people arguing on X? Mention @veracibot in the thread and an AI judge "
                    "reviews the arguments, checks the facts, and rules who is right — in public.",
        "hero_cta": "Mention @veracibot in a thread to open a case",
        "promo_title": "🔍 Truth Hunt",
        "promo_sub": "Call out as much fake news as you can in one week and win up to "
                     "3,000 microbitcoins (~US$ 150). A total of 5,000 μBTC in prizes "
                     "(~US$ 320) for X's top 5 lie hunters.",
        "promo_how_title": "How to join",
        "promo_steps": [
            "Have the blue badge (X Premium) on your account.",
            "Follow @veracibot on X.",
            "Post: \"@veracibot quero participar\" — the bot confirms your entry instantly.",
            "To receive the prize, winners must have a Bitcoin wallet with a mainnet "
            "address. Payment will be made on August 31.",
        ],
        "promo_rules_title": "How the contest works",
        "promo_rules": [
            "On Aug 16 at 0:00, every participant's points are reset to 1,000.",
            "During the week, call out fake news by mentioning @veracibot in the thread or quoting the claim. True or false rulings move points under the tribunal's rules.",
            "On Aug 22 at 24:00, whoever has the most points wins.",
        ],
        "promo_prizes_title": "Prizes (in microbitcoins)",
        "promo_prizes": [
            ("🥇 1st place", "3,000 μBTC (~US$ 150)"),
            ("🥈 2nd place", "1,000 μBTC"),
            ("🥉 3rd place", "500 μBTC"),
            ("4th and 5th places", "250 μBTC each"),
        ],
        "promo_cta": "I'm in",
        "promo_count_many": "people have already signed up — join them!",
        "promo_count_one": "person has already signed up — join them!",
        "winners_title": "Truth Hunt winners",
        "winners_note": "Scores frozen at the end of the contest (Aug 22, 24:00). "
                        "Prizes paid in microbitcoins on Aug 31. Thanks to every "
                        "truth hunter — the Debate Cycle is coming!",
        "promo_note": "5,000 μBTC (~US$ 320) in total prizes. Winners announced by "
                      "@veracibot when the contest ends.",
        "why_title": "What are microclaims?",
        "why_p1": "Nobody takes a broken plate, a $20 bet, or a broken email promise to "
                  "court. The cost, time, and bureaucracy of real justice leave these "
                  "tiny disputes — microclaims — orphaned: no judge, no verdict, no "
                  "remedy.",
        "why_p2": "The same goes for the truth: suing someone over a lie would be "
                  "overkill — but letting it spread unanswered has a cost too. "
                  "Fact-checking is the quintessential microclaim, and here it gets a "
                  "judge, evidence, and a verdict.",
        "why_p3": "VeraciBot is the first microclaims tribunal: an AI judge that settles "
                  "in minutes, in public, and for free the disputes no real court would "
                  "take. We don't compete with the judiciary — we handle precisely what "
                  "falls outside its reach. Serious cases are always referred to real "
                  "justice.",
        "how_title": "How it works",
        "how_1_t": "1. Summon the tribunal",
        "how_1": "Reply to any thread with @veracibot. It costs 1 point from your balance.",
        "how_2_t": "2. The judge deliberates",
        "how_2": "The AI reads the whole thread, classifies the case — dispute or fact-check — "
                 "and searches the web when claims need verification.",
        "how_3_t": "3. Public verdict",
        "how_3": "The ruling is posted as a reply in the thread itself, with reasoning and the "
                 "points scored by everyone involved.",
        "scoring_title": "Scoring",
        "scoring_intro": "Everyone starts with 1,000 points. Calling the bot costs 1 point.",
        "scoring_rows": [
            ("You flag a claim as false and the tribunal confirms", "+10 net (cost refunded); the claim's author loses 11"),
            ("The claim you flagged was true", "you lose 11; the author gains 10"),
            ("Undetermined or dismissed", "just the 1-point cost"),
            ("Disputes and debates: you are a party and win / lose", "+10 net / −11; a neutral third party pays only the cost and the sides play for ±10"),
            ("Appeal (loser only, once): a 24h public X poll decides", "costs 5 points; refunded if the ruling is reversed"),
        ],
        "process_title": "The full process",
        "process_steps": [
            "Invitation: only invited members can open cases — each member can invite 5 people.",
            "Opening: mention @veracibot in the thread (costs 1 point). Debates and disputes can be opened formally: \"vamos iniciar um debate entre @a e @b sobre X\".",
            "Discovery: if the parties contradict each other on a decisive fact, the judge requests evidence (links or screenshots) within 48h — who alleges, proves.",
            "Ruling: public verdict with reasoning and the points scoreboard.",
            "Appeal: the loser may appeal — a 24h public X poll decides.",
        ],
        "stats_cases": "cases ruled",
        "stats_fact": "fact-checks",
        "stats_disputes": "disputes",
        "stats_users": "citizens in the tribunal",
        "ranking_title": "Public leaderboard",
        "ranking_sub": "Point balance of every citizen of the tribunal.",
        "ranking_tab_promo": "🔍 Contest",
        "ranking_tab_all": "Overall",
        "ranking_promo_sub": "Truth Hunt participants only. The top 5 at the end of "
                             "Aug 22 take the prizes.",
        "ranking_promo_notstarted": "⏳ The official count starts Aug 16 at 0:00, "
                                    "when every participant's points reset to 1,000. "
                                    "Sign up now!",
        "col_pos": "#",
        "col_user": "User",
        "col_points": "Points",
        "cases_title": "Ruled cases",
        "cases_sub": "Verdicts issued by the tribunal, newest first.",
        "case_dispute": "Dispute",
        "case_fact": "Fact-check",
        "case_debate": "Debate",
        "case_declined": "Dismissed",
        "case_evidence": "Awaiting evidence",
        "winner": "Winner",
        "tie": "Tie",
        "view_on_x": "View thread on X",
        "case_label": "Case",
        "back_to_cases": "← All cases",
        "thread_title": "Case records (thread)",
        "ledger_title": "Points activity",
        "comp_title": "Settlement",
        "appeal_title": "Appeal",
        "votes_label": "votes",
        "deadline_label": "deadline",
        "onus_label": "Burden of proof",
        "grave_warning": "Serious case: the tribunal recommended seeking real justice.",
        "st_pendente": "pending",
        "st_cumprida": "fulfilled — 8 points returned",
        "st_expirada": "expired",
        "st_cancelada_recurso": "cancelled by the appeal",
        "st_aberta": "vote in progress",
        "st_mantida": "ruling upheld",
        "st_reformada": "ruling reversed by the jury",
        "nav_lawyers": "Lawyers",
        "law_title": "Partner lawyers",
        "law_sub": "When a case is too serious for the tribunal — or ends without a "
                   "settlement — VeraciBot refers real professionals. These are the "
                   "approved partners, by state.",
        "law_all_ufs": "All states",
        "law_filter": "Filter",
        "law_col_name": "Firm / Lawyer",
        "law_col_city": "City",
        "law_col_areas": "Practice areas",
        "law_col_contact": "Contact",
        "law_empty": "No partners registered in this state yet.",
        "law_cta_title": "Are you a lawyer?",
        "law_cta": "Get referrals of microclaims that escalate to real justice.",
        "law_cta_link": "Register your firm →",
        "nav_login": "Sign in",
        "claims_title": "claims ruled separately",
        "verdict_true": "✅ True",
        "verdict_false": "❌ False",
        "verdict_partial": "⚠️ Partially true",
        "verdict_undetermined": "❓ Undetermined",
        "no_cases": "No cases ruled yet. Be the first: mention @veracibot in a thread.",
        "no_scores": "Nobody has scored yet.",
        "footer_note": "Verdicts are AI-generated and may contain errors — read the reasoning and sources.",
        "footer_report": "Report a problem",
    },
}
