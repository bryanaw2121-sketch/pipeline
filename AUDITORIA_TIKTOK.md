# Auditoria do app no TikTok — roteiro do vídeo demo

Objetivo: liberar o **Direct Post**, que resolve os dois problemas de uma vez:
acaba o limite de ~5 rascunhos pendentes, e o vídeo passa a chegar **com a
legenda já preenchida** (o rascunho não carrega legenda).

Se recusarem, você recebe os comentários do revisor e **reenvia** — não é
eliminatório, e nada do que já funciona quebra.

---

## Antes de gravar

### 1. O truque que torna a gravação possível

O Direct Post hoje devolve:
```
403 unaudited_client_can_only_post_to_private_accounts
```
Leia com atenção: app não auditado **pode** postar em conta **privada**. Então
pra gravar o demo:

1. No app do TikTok: **Perfil → Configurações → Privacidade → Conta privada** (ligar)
2. Grave o demo (o Direct Post vai funcionar)
3. Depois de gravar, **volte a conta pra pública**

Sem isso não há como demonstrar o `video.publish`, e o revisor exige ver todos
os escopos pedidos funcionando.

### 2. Prepare a tela

- Feche o que for pessoal (abas, notificações, Telegram, WhatsApp)
- Deixe abertos e prontos:
  - o terminal na pasta `clip_engine`
  - o navegador **deslogado** de outras contas Google/TikTok, se possível
- Confira que existe pelo menos 1 clipe pronto: `python publicar_tiktok.py --fila`
- Apague o `token_tiktok.json` (renomeie, não delete):
  isso força o fluxo de login aparecer no vídeo, que é o que o revisor quer ver
  ```
  ren token_tiktok.json token_tiktok.json.bak
  ```

### 3. O que o revisor exige (do próprio formulário)

- fluxo **completo, ponta a ponta**
- **todos** os produtos e escopos pedidos, demonstrados: Login Kit
  (`user.info.basic`) + Content Posting API (`video.upload`, `video.publish`)
- interface e interações visíveis
- usar o **ambiente Sandbox** (é o nosso caso — app "Times Report")
- mp4 ou mov, até 50 MB, até 5 arquivos

---

## Roteiro (grave em uma tomada, ~3 min)

Use OBS, Xbox Game Bar (Win+G) ou qualquer gravador de tela. **Sem cortes** —
tomada única passa mais confiança pro revisor.

### Cena 1 — o que é o app (0:00–0:15)
Mostre a pasta do projeto no explorador de arquivos.
Fale (ou escreva na tela): *"Ferramenta pessoal de desktop. Publica cortes de
vídeo na minha própria conta do TikTok."*

### Cena 2 — login / Login Kit (0:15–1:00)
No terminal, digite devagar (o revisor precisa ler):
```
python publicar_tiktok.py --autorizar
```
Mostre:
1. o link de autorização aparecendo no terminal
2. o navegador abrindo na página oficial do TikTok
3. **você fazendo login e clicando em Autorizar** — a tela de consentimento
   mostrando os escopos é a parte mais importante do vídeo
4. a volta pro `localhost:8721/callback` com "Autorizado"
5. o terminal confirmando o token salvo com o `open_id`

Isso demonstra **Login Kit + `user.info.basic`**.

### Cena 3 — o conteúdo que vai subir (1:00–1:20)
Mostre a pasta `saida/`, abra um `short_9x16.mp4` e deixe tocar 3-4 segundos.
Fale: *"Este vídeo foi produzido por mim: corte, legenda e enquadramento."*

Isso responde antes de perguntarem "de onde vem esse conteúdo".

### Cena 4 — Direct Post (1:20–2:30)
Com a conta **privada** (passo 1 acima), rode:
```
python publicar_tiktok.py --pasta "saida/<lote>/fonte" --direto
```
Mostre no terminal:
1. o título/legenda sendo montado
2. o `publish_id` retornado
3. o `status` da consulta

Isso demonstra **Content Posting API + `video.publish`**.

### Cena 5 — resultado no app (2:30–3:00)
Abra o TikTok no celular (ou web) e mostre o vídeo publicado no perfil, **com
a legenda e as hashtags preenchidas**. Fecha o ciclo: o revisor viu entrar e
viu sair.

### Cena 6 — Display API / `video.list` (3:00–3:30)  ← NOVA em 31/07/2026

No terminal:
```
python metricas_tiktok.py
```
Mostre a tabela aparecendo: uma linha por vídeo publicado, com **views,
curtidas, comentários e compartilhamentos**. Depois rode:
```
python metricas_tiktok.py --gravar
```
e mostre o `estado/desempenho.json` sendo escrito, ou rode
`python desempenho.py` para exibir o relatório.

**Esta cena é obrigatória se o `video.list` estiver no formulário.** O
revisor exige ver todos os escopos funcionando; escopo pedido sem
demonstração é o motivo de recusa mais comum da tabela lá embaixo.

⚠️ Ordem importa: grave esta cena **depois** da autorização (Cena 2), e a
tela de consentimento precisa mostrar o `video.list` entre os escopos.

---

> Se quiser demonstrar também o `video.upload` (rascunho), rode
> `python publicar_tiktok.py --pasta "..."` sem `--direto` e mostre o vídeo
> chegando na Caixa de entrada. Só faça se houver vaga — hoje as ~5 estão
> presas (ver `sabedoria/SABEDORIA_TIKTOK.md`). Se não houver, **remova o
> escopo `video.upload`** do formulário: escopo pedido e não demonstrado
> atrasa a análise.

---

## Preencher o formulário (app de PRODUÇÃO, "Bryan Fatos")

Já temos tudo pronto:

- **App icon**: `app_icon_tiktok.png` (1024x1024)
- **Category**: Productivity
- **Description**:
  > Personal tool that publishes short video clips to my own TikTok account, with auto-generated captions.
- **Terms of Service URL** e **Privacy Policy URL**:
  `https://claude.ai/code/artifact/8f78a096-dd91-4c75-bf2f-e4c99b242704#terms`
  `https://claude.ai/code/artifact/8f78a096-dd91-4c75-bf2f-e4c99b242704#privacy`
  **Confira que estão públicas** (abrir numa janela anônima). Se o revisor não
  abrir, é recusa quase automática.
- **Platforms**: Desktop
- **Web/Desktop URL**: `https://claude.ai/code/artifact/8f78a096-dd91-4c75-bf2f-e4c99b242704`
- **Redirect URI**: `http://localhost:8721/callback`
- **NÃO precisa verificar domínio** — "Verify domains" vale só pro método
  `pull_by_url`; usamos `push_by_file`.

### Texto do "Explain how each product and scope works" (limite 1000)

```
This is a personal, single-operator desktop tool. Login Kit (user.info.basic)
authenticates the operator's own TikTok account via OAuth2 with PKCE, using a
local redirect server (http://localhost:8721/callback). After authorization,
the app uses the Content Posting API to upload a pre-rendered MP4 (a short
vertical clip with burned-in captions) directly to that same authorized
account, with the caption and hashtags set programmatically (video.publish).

The Display API (video.list) reads back the operator's own published videos
to retrieve view, like, comment and share counts. These numbers are written
to a local file and used to decide which clips to produce next. No metrics
from any other account are requested, stored or displayed.

Flow shown in the demo: (1) operator runs the local script, which prints the
authorization URL and opens it; (2) operator logs in and approves the scopes;
(3) the app exchanges the code for an access token; (4) the app calls
post/publish/video/init to obtain an upload URL; (5) the app PUTs the video
bytes; (6) the app polls post/publish/status/fetch until the post completes;
(7) the app calls video/list to read back the metrics of its own posts.

No other TikTok accounts are involved, no data is shared with third parties,
and the operator reviews every clip before it is published.
```

> Acima de 1000 caracteres? Corte o parágrafo do passo a passo (o vídeo já
> mostra o fluxo) e mantenha os três parágrafos de escopo — é o que o
> revisor procura.

---

## Se for recusado

Você recebe os comentários em **History → Review comments** no painel. Erros
comuns e como corrigir:

| Motivo provável | Correção |
|---|---|
| demo não mostra o fluxo completo | regravar incluindo a tela de consentimento e o resultado no app |
| escopo pedido sem demonstração | remover o escopo não usado, ou demonstrá-lo |
| URL de Termos/Privacidade não abre | hospedar o `site_times_report/` (ver abaixo) |
| descrição não corresponde ao app | alinhar descrição com o que o vídeo mostra |
| **ícone não bate com a marca** | **mesmo ícone no app, no logo do site E no favicon** |

### Recusa real de 31/07/2026

> *"Icon does not match brand. The app icon submitted in the Basic Info does
> not match the icon displayed on the website. Please ensure the same icon is
> used consistently across both the TikTok, the website and Browser tab
> (favicon), then resubmit for review."*

O app chama-se **Times Report**, mas o site e estes termos falavam em "Flux
Clips", com outro logo. Não era só o ícone: **a marca inteira não batia**.

E o site era um artifact do claude.ai, que **não pode ter favicon próprio** —
o favicon dele é um emoji. Por construção, o item reprovaria de novo.

**Corrigido:** `ATUALIZADA/site_times_report/` tem a página com o nome, o logo
e o favicon saindo do MESMO arquivo (`Downloads/times-report.png`), e as
âncoras `#terms` e `#privacy` preservadas. **Falta hospedar** (GitHub Pages) e
trocar as três URLs no app.

⚠️ **Este arquivo ainda diz "Flux Clips" em outros pontos, e o
`TERMOS_PARA_COLAR.txt` também.** Se reaproveitar aqueles textos como estão, o
problema de marca volta. Use o `site_times_report/index.html` como fonte.

Reenviar é normal e ilimitado. Enquanto isso, o fluxo de rascunho + transfer
manual continua funcionando igual.
