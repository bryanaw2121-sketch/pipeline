# Padrão do motor — decidido com o usuário, não renegociar sem pedido explícito

Este arquivo é a fonte de verdade de como todo vídeo deve ser processado.
Se um comando/config abaixo diverge do padrão, o padrão vence, a menos que
o usuário peça uma exceção pontual.

## Comando padrão pra um vídeo novo

```powershell
python main.py --url "URL" --idioma en --qtd 5
```

- **NÃO usar `--dublar`**. Testado e rejeitado pelo usuário (qualidade de
  TTS ruim, sem sincronismo labial). Só ligar se pedirem de novo,
  explicitamente, pro vídeo específico.
- **`--qtd 8-10`**, não 3 nem 5. Dois filtros descartam candidato: a
  checagem de congelamento (entrevista remota trava câmera) e agora o
  mínimo de 65s (ver abaixo). Pedindo pouco, sobra 1 ou nenhum.
- Sempre roda com `--manter-temp` durante uma sessão de ajuste/teste (pra
  poder inspecionar `trabalho/bruto_*.mp4` se algo sair errado). Pode tirar
  em produção/lote depois que o pipeline estiver rodando sem supervisão.

## Duração do clipe: MÍNIMO 65s (27/07/2026) — regra de dinheiro

```python
DUR_MIN = 65      # era 20
DUR_MAX = 110     # era 120
```

**O TikTok só paga por "visualização qualificada", e ela exige vídeo com
mais de 60 segundos.** Achado mais corroborado da destilação — 8 vídeos
independentes (`sabedoria/PLAYBOOK_TIKTOK.md` §1). Clipe abaixo disso rende
**zero** por mais que viralize.

Prova em casa: o lote da Bermuda (`saida/2026-07-26_2346`) tem 6 clipes de
notas 83-95, **todos entre 42 e 56s** — nenhum podia monetizar.

- 65 e não 61 é margem: `MARGEM` e o corte em pausa natural mexem no tempo
  final, e perder tudo por 0,4s seria burrice.
- 110 no teto porque a visualização qualificada também pede ~50% de
  retenção, que fica difícil em vídeo longo.
- O prompt manda **alargar o recorte** pra passar de 65s quando o trecho
  bom é curto — e **descartar** em vez de encher de enrolação, porque
  enrolação derruba a retenção e mata a qualificação do mesmo jeito.
- `engine/selecao.py:_validar()` descarta candidato abaixo de `DUR_MIN`
  automaticamente. Por isso o `--qtd` subiu pra 8-10.

**Vídeos já publicados ficam como estão** (decisão do usuário, 27/07/2026).
A regra vale daqui pra frente.

## Modelo do Gemini e cascata de reserva (27/07/2026)

**O padrão continua `gemini-3.6-flash`.** Não trocar por conta própria.

O tier gratuito do Gemini é de **20 requisições por dia, por projeto, por
modelo** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). Com 8
chaves são ~160 chamadas/dia **naquele modelo** — e um vídeo custa 1
chamada (`selecao.escolher`). A cota de cada modelo é **independente**.

Por isso o `config.py` tem:
```python
GEMINI_MODELO = "gemini-3.6-flash"
GEMINI_MODELOS_RESERVA = []          # vazia: os candidatos reprovaram
```

**A lista está vazia porque os reservas foram TESTADOS e reprovaram**
(27/07/2026, `teste/comparar_modelos.py`, vídeo da Bermuda contra a
referência de 6 clipes do 3.6-flash):

| modelo | resultado |
|---|---|
| `gemini-3-flash-preview` | 1 clipe de 6, e **errado**: pegou 18-138s (a introdução) e deu a ele o título do trecho de US$1,5 tri, que está em 1300-1356s |
| `gemini-3.5-flash` | 0 clipes |

O modo de falha é traiçoeiro: o `post.json` sai completo e convincente
(título forte, nota 92, taxonomia cheia), então **passa despercebido** — só
se descobre assistindo. Um clipe com título que não bate com o conteúdo é
pior que clipe nenhum. **Quando a cota estourar, o motor falha alto e a
gente espera a virada** (~4-5h da manhã).
`engine/selecao.py:_pedir()` roda as 8 chaves no modelo principal e **só
cai pro reserva quando todas esgotam naquele modelo**. Distingue:
- **429** = sem cota naquele modelo → marca a chave e, esgotando todas,
  desce na lista;
- **503** = "high demand", sobrecarga temporária do modelo → espera e
  repete, **não** desce (a cota está intacta).

**Regra pra mexer nessa lista:** só entra modelo **validado** com
`teste/comparar_modelos.py`, que roda a seleção real no mesmo vídeo e
compara contra um lote já produzido (nº de clipes, notas, duração,
taxonomia e quantos momentos da referência o modelo reencontra):
```
python teste/comparar_modelos.py --url "URL" \
  --modelos gemini-3.6-flash gemini-3.5-flash gemini-3-flash-preview \
  --qtd 6 --ref "saida/2026-07-26_2346/fonte"
```

**A cota do Gemini é do pipeline de vídeo.** Trabalho de lote pesado
(destilação de corpus, análise de texto em massa) vai no **Nemotron**
(`engine/nemotron.py`, 5 chaves NVIDIA, sem teto diário). Em 27/07/2026
uma destilação de 129 lotes queimou a cota do dia inteira e deixou o motor
sem `gemini-3.6-flash` — foi o que originou esta seção.

## Tradução e idioma

- Fala em outro idioma (inglês etc.) → **sempre traduz pra pt-BR**
  (padrão do `main.py`, não precisa flag).
- Título, descrição, tags: **sempre pt-BR**, mesmo com fala original em
  outro idioma. Já embutido no prompt do Gemini (`engine/selecao.py`).
- Título: **chamativo/clickbait controlado** — gera curiosidade, usa
  contraste/números, nunca genérico.
- Descrição: **palavra-chave logo no início** (primeiros ~200 caracteres),
  sem frase de efeito antes dela — é o que o YouTube indexa primeiro.
- Estrutura do corte: **GPC (Gancho-Progresso-Clímax)** — sem introdução
  de contexto no começo, termina logo após o pico, ideia fecha sozinha.

## Vídeo / edição

- **Fonte da legenda: Inter Black** (open-source, instalada no sistema).
  Nunca usar Arial Black (era feia, trocada a pedido do usuário) nem Segoe
  UI Black (opção intermediária, também trocada).
- Legenda **pequena e centralizada**: `altura*0.038`, margem lateral
  `largura*0.12`. Não deixar grande nem encostando na borda.
- **Ken Burns** (zoom lento 1.00→1.06) sempre ativo no render vertical e
  horizontal — usa o fps NATIVO da fonte (nunca forçar 30fps: isso
  dessincroniza legenda/áudio, já corrigido uma vez).
- **Descarte de câmera travada**: candidato com zona de congelamento
  contínua (blocos próximos agrupados, gap <1s) acima de
  `config.CONGELAMENTO_MAX_S` (4.5s) é descartado inteiro. Se o
  congelamento for só na abertura do clipe, o início é empurrado pra depois
  dele em vez de descartar (`midia.pular_congelamento_inicial`).
- Face tracking: **hoje cai pro crop central** (mediapipe legado
  removido da API nova). Funciona, mas não seleciona rosto de verdade.
  Corrigir só se o usuário pedir — a correção certa é reescrever
  `engine/enquadrar.py` pra API `mp.tasks`, que exige baixar um modelo
  `.tflite` (pedir permissão antes).

## Formato de saída: SÓ VERTICAL (decidido 26/07/2026)

O destino agora é TikTok, que é vertical-first — 16:9 rende mal lá. O
`main.py` **não gera mais o `fullscreen_16x9.mp4`** por padrão (dobrava o
tempo de render por nada). Use `--com-horizontal` só se pedirem.
Mesma coisa no `publicar_tiktok.py`.

## Publicação — TikTok (plataforma atual)

- **Só vertical.** `publicar_tiktok.py --pasta "..."` — o 9:16 é o padrão.
- **Modo rascunho é o único que funciona hoje.** O app não é auditado, e o
  TikTok recusa Direct Post com
  `unaudited_client_can_only_post_to_private_accounts` (app não auditado só
  posta em conta PRIVADA — inútil, a conta precisa ser pública). Então o
  fluxo é: script manda pro **inbox como rascunho** → usuário abre o app do
  TikTok e toca em "Postar". A legenda com hashtags sai no output do
  terminal pra copiar/colar.
- `--direto` (Direct Post) só vai funcionar depois da auditoria completa
  (basicamente um **vídeo demo** gravado pelo usuário; NÃO precisa de domínio
  verificado — isso só vale pro método `pull_by_url`, e nós usamos
  `push_by_file`). Não submetido: em 26/07/2026 o usuário decidiu
  **ficar no modo rascunho**, colando a legenda na mão. Não oferecer
  auditoria de novo sem ele pedir.
- **Como o usuário posta manualmente, o HORÁRIO é decisão dele** — não
  existe agendamento de rascunho via API.

## Ritmo e variedade (o que derrubou o canal do YouTube)

O canal anterior foi banido por "Spam, práticas enganosas e golpes" depois
de uma rajada de ~8-10 vídeos em poucas horas, todos sobre o mesmo tema.
Regras acordadas com o usuário pra não repetir:

- **3-5 vídeos por dia** (escolha do usuário; foi avisado que em conta nova
  isso é a faixa de risco).
- ⚠️ **REVOGADO em 27/07, ver `sabedoria/PLAYBOOK_TIKTOK.md` §7.1 e §17.4.**
  A regra atual é **núcleo semântico único e estreito**, variando ângulo e
  formato — não o tema. Variar tema compete com o loop de reinjeção
  algorítmica. O texto riscado abaixo fica só como histórico:
- ~~**Variar o tema** — não fazer bateria só de Elon Musk/IA. Isso é
  requisito, não sugestão: mono-tema + volume foi exatamente o padrão
  flagado.~~
- **Espaçar ao longo do dia**, em horários de maior audiência, não tudo de
  uma vez. Ponto de partida (Brasil): manhã 6-9h, almoço 12-14h, noite
  19-23h. Depois que a conta tiver histórico, trocar esse chute pelos dados
  reais do painel do TikTok (o `SABEDORIA_YT.md` recomenda usar o gráfico de
  atividade do próprio público — o melhor horário muda de conta pra conta).
- **Conteúdo de terceiros**: só cortar/publicar com confirmação explícita de
  permissão. Perguntar sempre que for um criador/canal novo.

## Publicação — YouTube (canal banido, mantido como referência)

O canal "Fatos na Língua" foi removido em 26/07/2026. `publicar.py` continua
funcional e o `token.json` do canal banido está em
`token_canal_antigo_banido.json.bak`. Se um canal novo de YouTube entrar em
cena, valia isto:

- Sempre perguntar público vs privado antes de publicar — não assumir.
- `publicar.py --pasta "..." --publico`, e por padrão sobe vertical + tela
  cheia como dois vídeos separados (`--so-vertical` pula o tela cheia).
  Atenção: com o `main.py` não gerando mais 16:9, só o vertical existe.
- **1 vídeo só → publica direto, sem agendamento.** Pra 1 vídeo, depois do
  upload (que nasce privado com `publishAt` futuro), chamar
  `videos().update` trocando `privacyStatus` pra `public` na hora.

## O que NÃO fazer sem pedido explícito novo

- Não ligar dublagem (`--dublar`) por padrão.
- Não trocar Groq ou Gemini por alternativa local/Ollama — usuário tem
  bastante cota em ambos, decisão tomada.
- Não implementar Ken Burns/zoompan de outro jeito sem testar isolado
  primeiro (já causou 1 bug de dessincronia, corrigido).
- Não mexer no limiar de congelamento (`CONGELAMENTO_MAX_S = 4.5`,
  agrupamento com gap `<1.0s`) sem antes rodar o diagnóstico
  (`freezedetect` manual) pra confirmar que não é falso positivo/negativo —
  esse número já foi calibrado duas vezes com dado real.

## RPM inglês vs português — DECIDIDO (26/07/2026)

O documento `sabedoria/SABEDORIA_YT.md` aponta RPM 4-8x maior em conteúdo
em inglês pro público internacional do que em português. O algoritmo do
YouTube pareia por sinais de idioma/audiência (ver "encadeamento de
sessão" no doc) — um canal não "alcança" os dois públicos ao mesmo tempo
misturando pt-BR e inglês.

**Decisão do usuário:** manter o canal atual 100% pt-BR (fluxo padrão sem
mudança). Quando fizer sentido, abrir um **segundo canal separado,
puramente em inglês** (sem tradução, título/descrição/tags/legenda em
inglês) pra capturar o RPM maior — não é pra converter o canal existente,
é canal novo. Ainda não implementado (falta o modo "sem tradução" no
`main.py`/`traducao.py` e decidir a conta/branding do segundo canal) —
avisar antes de começar esse trabalho.
