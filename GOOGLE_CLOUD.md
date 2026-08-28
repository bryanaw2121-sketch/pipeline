# Configurar o projeto no Google Cloud

Necessário só para o `publicar.py`. O `main.py` (gerar os cortes) não precisa
de nada disso.

---

## Passo 1 — Criar o projeto

1. Abra https://console.cloud.google.com
2. No topo, clique no seletor de projetos → **Novo projeto**
3. Nome: `flux-youtube` → **Criar**
4. **ANOTE O NÚMERO DO PROJETO** (não o nome, o número — algo como
   `483920174653`). Vai ser pedido na auditoria.
   Fica em *Início* → cartão "Informações do projeto".

## Passo 2 — Ativar a YouTube Data API v3

1. Menu ☰ → **APIs e serviços** → **Biblioteca**
2. Busque `YouTube Data API v3`
3. **Ativar**

## Passo 3 — Tela de consentimento OAuth

1. **APIs e serviços** → **Tela de permissão OAuth**
2. Tipo: **Externo** → **Criar**
3. Preencha:
   - Nome do app: `Flux YouTube`
   - E-mail de suporte: o seu
   - E-mail do desenvolvedor: o seu
4. **Escopos**: adicione os dois
   - `.../auth/youtube.upload`
   - `.../auth/youtube.force-ssl`
5. **Usuários de teste**: adicione a conta Google dona do canal.

   IMPORTANTE: enquanto o app estiver "Em teste", só as contas listadas aqui
   conseguem autorizar, e o refresh token expira a cada 7 dias (você refaz o
   login). Isso é normal e não impede nada — some quando o app for publicado.

## Passo 4 — Criar as credenciais

1. **APIs e serviços** → **Credenciais** → **Criar credenciais**
   → **ID do cliente OAuth**
2. Tipo de aplicativo: **App para computador**
3. Nome: `flux-desktop` → **Criar**
4. Baixe o JSON e salve como **`client_secrets.json`** na raiz do
   `clip_engine` (do lado do `publicar.py`)

## Passo 5 — Testar a liberação (NÃO PULE)

```powershell
python publicar.py --verificar
```

O que ele faz: sobe 1 vídeo descartável de 5 segundos, tenta torná-lo público,
lê o resultado de volta e apaga o vídeo.

- **PROJETO LIBERADO** → pode publicar em lote
- **PROJETO TRANCADO** → siga para o passo 6 e, até lá, suba pelo Studio

Enquanto o teste não passar, o `publicar.py` se recusa a subir em lote.

## Passo 6 — Pedir a auditoria de compliance

Projeto novo NÃO é auditado. Todo vídeo enviado por projeto não auditado é
**trancado como privado, sem direito a recurso** — só reenviando na mão.

Formulário (é o mesmo para auditoria e extensão de cota):

**https://support.google.com/youtube/contact/yt_api_form**

Tenha em mãos:
- Número do projeto (Passo 1)
- Descrição do uso. Seja concreto e honesto, por exemplo:

  > Ferramenta que gera cortes curtos a partir de vídeos longos e os publica
  > em canais próprios e de criadores que autorizaram o uso. A seleção dos
  > trechos é feita por IA, com legendas e enquadramento próprios. A
  > publicação usa OAuth do dono de cada canal.

- Se você posta em canais de terceiros, **diga explicitamente**. É o ponto
  que eles mais avaliam.

A resposta não tem prazo publicado — na prática costuma levar semanas.
**Peça agora**, mesmo que só vá automatizar depois; a fila corre em paralelo
enquanto você testa o motor.

Aprovado, você também ganha cota acima das 10.000 unidades/dia.

---

## Cota

Cada projeto começa com **10.000 unidades/dia**.

| Operação | Custo |
|---|---|
| `videos.insert` (upload) | ~100 unidades |
| `videos.list` | 1 unidade |
| `search.list` | 100 unidades |

O upload custava 1.600 unidades até dezembro/2025 — mudou para ~100, o que
levou o limite de **6 para ~100 uploads por dia**. Quase todo tutorial na
internet ainda cita o valor antigo.

---

## Uso do publicar.py

```powershell
# 1) sempre primeiro
python publicar.py --verificar

# 2) sobe privado, você revisa e publica na mão (padrão seguro)
python publicar.py --pasta "saida\2026-07-26_1430\meu-video"

# 3) agenda publicação: 2 por dia, a partir das 18h
python publicar.py --pasta "saida\..." --publico --por-dia 2 --hora 18:00

# 4) publica a versão 16:9 em vez do Short
python publicar.py --pasta "saida\..." --horizontal
```

Sem `--publico` os vídeos ficam privados e nada vai ao ar — você revisa no
Studio e publica quando quiser. Corte que vai ao ar sem ninguém olhar é como
canal de cortes toma strike.

O `--por-dia` distribui ao longo dos dias: 10 clipes com `--por-dia 2` viram
5 dias de postagem agendada.

Cada pasta ganha um `_publicados.json` com os IDs e horários enviados.
