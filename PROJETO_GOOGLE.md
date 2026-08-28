# Identificadores do projeto Google Cloud

Guarde este arquivo. O **número do projeto** é exigido no formulário de
auditoria, e é o dado que mais gente perde na hora de pedir.

| Campo | Valor |
|---|---|
| **Número do projeto** | `961404808712` |
| **Project ID** | `geometric-ivy-503601-q8` |
| API ativada | YouTube Data API v3 |
| Criado em | 26/07/2026 |

Estes NÃO são segredos — são identificadores públicos do projeto. O que é
segredo é o `client_secrets.json` e o `token.json`, que nunca devem ser
versionados nem compartilhados.

---

## Progresso da configuração

- [x] **Passo 1** — projeto criado
- [x] **Passo 2** — YouTube Data API v3 ativada
- [ ] **Passo 3** — tela de consentimento OAuth
- [ ] **Passo 4** — credenciais (`client_secrets.json`)
- [ ] **Passo 5** — `python publicar.py --verificar`
- [ ] **Passo 6** — auditoria de compliance solicitada

Detalhe de cada passo em [GOOGLE_CLOUD.md](GOOGLE_CLOUD.md).

---

## Resposta do assistente de credenciais

> **"What data will you be accessing?"** → escolha **User data**

Motivo: publicar vídeo é agir *em nome de um usuário* no canal dele. Isso
exige consentimento via OAuth.

**Public data** criaria apenas uma API key, que só serve para LER dados
públicos (buscar vídeos, ver estatísticas). API key não sobe vídeo nenhum.

Se mais adiante você adicionar o módulo de descoberta (radar de vídeos em
alta no Brasil), aí sim vale criar TAMBÉM uma API key — as duas coisas
convivem no mesmo projeto.

---

## Auditoria — o que responder

Formulário: https://support.google.com/youtube/contact/yt_api_form

- **Project number:** `961404808712`
- **Descrição sugerida:**

  > Ferramenta que gera cortes curtos a partir de vídeos longos e os publica
  > em canais próprios e de criadores que autorizaram o uso. A seleção dos
  > trechos é feita por IA, com legendas e enquadramento próprios. A
  > publicação usa OAuth do dono de cada canal.

- Se for postar em canais de terceiros, **declare isso explicitamente**.
