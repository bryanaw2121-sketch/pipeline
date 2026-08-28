"""Ancora o início do clipe no começo de uma FRASE, não no meio dela.

Por que existe (medido em 30/07/2026, nos insights reais do @modofuturo):

    vídeo 1 — 569 views, retenção 25%, primeira legenda: "A GENTE PROVAVELMENTE"
    vídeo 2 — 106 views, retenção 5,3%, primeira legenda: "ESSE É REALMENTE"

O TikTok informou, no primeiro: "a maioria dos espectadores parou de assistir
em 0:02". A curva do segundo cai de 100% para ~10% antes do primeiro segundo
terminar e depois segue reta — quem passa dos 2s fica até o fim. E 98,7% e
99,1% do tráfego vinham da Para Você, ou seja, distribuição não era o
problema: o vídeo simplesmente não dava motivo para ficar.

Os dois abriam no meio de uma frase. Sem sujeito, sem contexto, sem pergunta.

O prompt do Gemini JÁ mandava "corte em pausa natural da fala — nunca no meio
de uma palavra ou frase" (selecao.py). Ele não obedece de forma confiável, e
foi assim que dois clipes com essa abertura chegaram ao ar. Pedir de novo, com
mais ênfase, não é conserto: é a mesma aposta que já falhou.

Aqui a garantia é determinística. Transcreve uma JANELA curta do vídeo-fonte
em volta do início escolhido e recua o início até a última fronteira de frase
antes dele. Se não achar fronteira, devolve o início original — nunca piora.

Custo: uma chamada de transcrição por clipe, sobre ~12s de áudio.
"""
from pathlib import Path

import config
from . import midia, transcricao

# Quanto olhar para trás procurando o começo da frase. Frase falada em
# podcast raramente passa disso; olhar mais longe só aumenta o risco de
# recuar demais e trazer contexto que o Gemini decidiu cortar fora.
JANELA_S = 12.0

# Recuo máximo aceito. Acima disso o corte deixa de ser o que foi escolhido.
RECUO_MAX_S = 9.0

# Silêncio que separa duas frases quando não há pontuação. O Whisper nem
# sempre pontua; a pausa é o sinal que sobra. 0,45s é pausa de respiração
# entre frases — abaixo disso é cadência dentro da mesma frase.
PAUSA_FRASE_S = 0.45

_FIM_DE_FRASE = (".", "!", "?", "…", ":")


def _fronteiras(ps: list[dict], base: float) -> list[float]:
    """Instantes (absolutos) onde uma frase começa, dentro da janela.

    Duas evidências, porque nenhuma sozinha é confiável:
      - pontuação da palavra ANTERIOR (o Whisper às vezes pontua)
      - pausa antes da palavra (quando não pontua, o silêncio denuncia)
    """
    achados = []
    for i, p in enumerate(ps):
        if i == 0:
            continue
        anterior = ps[i - 1]
        texto_anterior = (anterior.get("palavra") or "").strip()
        pontuou = texto_anterior.endswith(_FIM_DE_FRASE)
        pausa = float(p.get("inicio", 0)) - float(anterior.get("fim", 0))
        if pontuou or pausa >= PAUSA_FRASE_S:
            achados.append(base + float(p["inicio"]))
    return achados


def ancorar(fonte: Path, inicio_s: float, fim_s: float,
            idioma: str | None = "pt", trabalho: Path | None = None) -> float:
    """Devolve um início ancorado no começo de frase, ou o original.

    Nunca devolve um início que:
      - recue mais que RECUO_MAX_S,
      - estoure config.DUR_MAX somando com o fim,
      - seja negativo.
    """
    if inicio_s <= 0.1:
        return inicio_s

    trabalho = trabalho or config.TRABALHO
    trabalho.mkdir(parents=True, exist_ok=True)

    base = max(0.0, inicio_s - JANELA_S)
    dur = inicio_s - base + 2.0          # +2s: contexto para o Whisper fechar
    if dur < 2.0:
        return inicio_s

    audio = trabalho / "ancora.flac"
    try:
        # Só o ÁUDIO da janela, direto da fonte: não passa por corte de vídeo
        # nem recodifica imagem. 12s de FLAC 16k mono é da ordem de 200 KB.
        # -ss antes do -i faz o seek rápido, sem decodificar o que vem antes.
        midia.roda(["ffmpeg", "-y", "-v", "error",
                    "-ss", f"{base:.3f}", "-t", f"{dur:.3f}", "-i", str(fonte),
                    "-vn", "-ac", "1", "-ar", "16000", str(audio)])
        ps = transcricao.palavras(audio, idioma)
    except Exception as e:                                   # noqa: BLE001
        print(f"      [ancoragem] pulei ({str(e)[:60]})")
        return inicio_s

    if not ps:
        return inicio_s

    # Só fronteiras ANTES do início escolhido — recuar, nunca avançar.
    # Avançar cortaria fora justamente o gancho que o Gemini escolheu.
    cands = [t for t in _fronteiras(ps, base)
             if t < inicio_s - 0.15 and inicio_s - t <= RECUO_MAX_S]
    if not cands:
        return inicio_s

    novo = max(cands)                     # a fronteira mais próxima do original
    if fim_s - novo > config.DUR_MAX:
        # Recuar estouraria o teto de duração. Melhor manter o corte original
        # do que entregar um clipe que o próprio filtro descarta depois.
        return inicio_s

    print(f"      início ancorado {inicio_s:.1f}s→{novo:.1f}s "
          f"(começo de frase, {inicio_s - novo:.1f}s antes)")
    return round(novo, 2)
