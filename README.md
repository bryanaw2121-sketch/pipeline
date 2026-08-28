# Motor de Cortes — Nitro 5

Vídeo longo entra, Shorts prontos pra postar saem. Gemini escolhe os momentos,
Groq faz as legendas, ffmpeg monta tudo na sua GTX 1650.

## Como o trabalho é dividido

| Etapa | Onde roda | Por quê |
|---|---|---|
| Download | Nitro 5 | yt-dlp |
| Extrair áudio | Nitro 5 | ffmpeg, 16kHz mono |
| **Escolher momentos** | **Gemini** | aguenta 9,5h num prompt — o vídeo inteiro vai de uma vez |
| **Legendas palavra-a-palavra** | **Groq** | só nos clipes de ~1 min (≈1 MB) |
| Corte, enquadramento, render | Nitro 5 | ffmpeg + NVENC da 1650 |

## A inversão que evita o limite de 25 MB

A ordem óbvia seria transcrever a hora inteira e mandar o texto pro Gemini.
Não é o que este motor faz.

```
              ┌─ vídeo de 1 hora ─┐
              │                   │
       Gemini analisa        (nunca vai pra Groq)
       o material INTEIRO
              │
       10 momentos escolhidos
              │
       ┌──────┴──────┐
       │ clipes de   │
       │ ~1 min cada │ ──► Groq legenda (1 MB, longe do limite)
       └─────────────┘
```

O arquivo grande só passa por quem aguenta arquivo grande. **Sem chunking,
sem offset de timestamp pra corrigir** — que é justamente onde esse tipo de
pipeline costuma quebrar em silêncio e produzir cortes tortos.

Cada modelo entrega o que sabe fazer: o Gemini dá tempo em segundos (basta pra
decidir onde cortar), e o Whisper dá tempo por palavra (obrigatório pro efeito
karaokê da legenda).

## Instalação

```powershell
.\setup_nitro5.ps1
```

Instala ffmpeg e yt-dlp via winget, as dependências Python, e cria o `.env`.
Depois preencha o `.env` com suas chaves — ele rota entre todas as 8 de cada
provedor automaticamente e aposenta sozinho as que estouram quota.

## Uso

```powershell
python main.py --url "https://youtube.com/watch?v=..."
```

```powershell
python main.py --arquivo "C:\videos\live.mp4" --qtd 15
```

| Flag | Efeito |
|---|---|
| `--qtd N` | quantos clipes extrair (padrão 10) |
| `--so-audio` | Gemini analisa só o áudio: bem mais barato, mas **não vê a cena** |
| `--so-vertical` | pula o render 16:9 |
| `--idioma en` | idioma da fala (padrão `pt`) |

Por padrão o Gemini recebe o **vídeo**, não só o áudio — ele vê expressão,
reação e mudança de cena. Um silêncio com cara de espanto não aparece em
transcrição nenhuma, e costuma ser o melhor corte do vídeo.

## O que sai

```
saida/2026-07-26_1430/nome-do-video/
├── 01_nota92_Titulo-Do-Corte/
│   ├── short_9x16.mp4        ← Shorts, com face tracking e legenda karaokê
│   ├── fullscreen_16x9.mp4   ← o corte de 1 minuto em tela cheia
│   ├── capa.jpg
│   ├── post.txt              ← título + descrição + hashtags, pronto pra colar
│   └── post.json
├── 02_nota88_.../
└── _resumo.json
```

As pastas vêm **numeradas por potencial viral** — a `01` é o melhor momento do
vídeo. Poste na ordem.

## Detalhes que importam

**Face tracking.** O crop 9:16 persegue o rosto em vez de cortar fixo no
centro; sem isso quem fala de lado fica com a cabeça cortada. O movimento é
suavizado nos dois sentidos e limitado a 60 mudanças de enquadramento por
clipe — quadro nervoso é pior que quadro parado.

**NVENC.** O motor detecta a 1650 e usa o encoder de hardware. Sem NVIDIA, cai
pra `libx264` sozinho — funciona igual, só mais devagar.

**Modelo de transcrição.** Usa `whisper-large-v3` (10,3% de erro), não o turbo
(12%). Como só transcrevemos ~10 minutos de clipe por vídeo, a diferença de
custo é irrelevante — e erro em legenda queimada é permanente.

**Validação dos cortes.** O Gemini às vezes devolve tempo fora do vídeo ou
trechos sobrepostos. O motor corrige o que dá e descarta o resto: melhor
perder um clipe que renderizar lixo.

## Custo por vídeo de 1 hora

- Gemini: ~115 mil tokens (áudio) — o vídeo custa mais, escolhe melhor
- Groq: ~10 min de áudio ≈ **$0,02**
- Render: elétrica do Nitro 5

## Ajustes

Tudo em `config.py`: duração dos clipes, quantidade, modelos, resolução,
suavização do tracking.

Se a escolha vier fraca em conteúdo muito técnico, troque
`GEMINI_MODELO` para `gemini-3.1-pro-preview`.
