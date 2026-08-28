"""Dublagem com a voz clonada do Bryan (Chatterbox Multilingual, self-hosted,
grátis, MIT — ver [[modofuturo]] handoff 04/08/2026).

Roda 100% na nuvem do Actions (CPU, sem GPU) — não na máquina do Bryan, que é
fraca demais pra isso. Medido em 04/08/2026 (run #30867337829):
  - instalar dependências: ~165s
  - carregar o modelo:      ~48s
  - gerar 1 frase (24 palavras): ~154s

O modelo é caro de carregar (48s) — por isso fica em cache no módulo e só
carrega UMA VEZ por execução do main.py, reaproveitado entre todos os
clipes do lote (`--qtd`), não recarregado por clipe.

Watermarker (resemble-perth) tem um bug de ambiente (pkg_resources faltando
em alguns setups) que derruba o carregamento do modelo com
`TypeError: 'NoneType' object is not callable` — contornado com um stub
vazio antes do import, ao custo de o áudio sair sem o carimbo "gerado por
IA" da Resemble (não achamos alternativa: 3 tentativas de consertar a causa
raiz falharam, ver commits 61bc8b8/202e3f6/98bfa2a).
"""
import re
import shutil
from pathlib import Path

from . import midia

IDIOMA_PADRAO = "pt"
_MODELO = None
_PAUSA_ENTRE_FRASES_S = 0.15


def _bypass_watermarker():
    import perth

    class _SemMarcaDagua:
        def __init__(self, *a, **k):
            pass

        def apply_watermark(self, wav, sample_rate=None):
            return wav

    perth.PerthImplicitWatermarker = _SemMarcaDagua


def _carregar_modelo():
    global _MODELO
    if _MODELO is None:
        _bypass_watermarker()
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        print("      carregando modelo de voz clonada (Chatterbox)...")
        _MODELO = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    return _MODELO


def _falar(texto: str, destino: Path, amostra_voz: Path, idioma: str) -> Path:
    import torchaudio as ta
    from . import numeros
    modelo = _carregar_modelo()
    # Numero por extenso SO' aqui, no ponto em que o texto vira audio. A
    # legenda na tela continua com o digito ("2030" le' melhor que "dois mil
    # e trinta" escrito), e o `timing` devolvido segue com o texto original.
    falado = numeros.por_extenso(texto)
    wav = modelo.generate(falado, audio_prompt_path=str(amostra_voz), language_id=idioma)
    ta.save(str(destino), wav, modelo.sr)
    return destino


def _ajustar_duracao(audio: Path, alvo_s: float, destino: Path) -> Path:
    """Encaixa o áudio no tamanho do clipe (`render.vertical` usa
    `-shortest`, então o áudio TEM que ter pelo menos a duração do vídeo,
    senão o vídeo final sai cortado).

    Narração mais CURTA que o clipe: preenche o resto com SILÊNCIO no
    final, sem mexer no ritmo da fala — esticar/desacelerar (como fazia
    antes, sempre) deixava a voz arrastada mesmo quando a diferença era
    pequena (Bryan reportou "ficou lenta" com um fator de só 0.86x, ou
    seja, eu tava desacelerando a fala em 14% à toa). Narração mais LONGA
    que o clipe: acelera (até 1.6x, acima disso fica robótico/irreconhecível
    — já tinha esse teto antes)."""
    dur = midia.duracao(audio)
    if dur <= 0:
        shutil.copy(audio, destino)
        return destino

    if dur <= alvo_s:
        falta = alvo_s - dur
        midia.roda(["ffmpeg", "-y", "-i", str(audio),
                    "-af", f"apad=pad_dur={falta:.3f}",
                    "-ar", "44100", str(destino)])
        return destino

    fator = min(1.6, dur / max(0.1, alvo_s))
    midia.roda(["ffmpeg", "-y", "-i", str(audio),
                "-filter:a", f"atempo={fator:.3f}",
                "-ar", "44100", str(destino)])
    return destino


# Abreviações comuns em português — o "." delas NÃO é fim de frase.
# Sem isso, "Dr. Yao" virava duas frases ("Dr." + "Yao..."), isolando
# "Yao" como uma síntese de TTS separada e curtíssima — o Chatterbox
# reagiu com uma pausa longa e um ruído de respiração ali (Bryan
# reportou em 05/08/2026 ouvindo o clipe 002).
_ABREVIACOES = {
    "dr", "dra", "sr", "sra", "srta", "prof", "profa", "eng", "engo",
    "gen", "cel", "cap", "pe", "irmã", "dom", "exmo", "exma",
    "jr", "mr", "mrs", "ms", "st",
}


def _dividir_frases(texto: str) -> list[str]:
    """Divide pela pontuação de fim de frase (. ! ?), não por janela de
    tempo arbitrária — cada pedaço vira uma chamada de TTS curta, que é o
    regime em que o Chatterbox soa bem (ver módulo: ~154s pra 24 palavras;
    um texto de 90s inteiro numa síntese só saiu arrastado e com dicção
    ruim, medido com o Bryan em 05/08/2026).

    Protege abreviações (Dr., Sr., etc.) antes de cortar — o "." delas não
    marca fim de frase."""
    texto = texto.strip()

    def _proteger(m: re.Match) -> str:
        return m.group(0)[:-1] + "\x00"

    padrao_abrev = r"\b(?:" + "|".join(re.escape(a) for a in _ABREVIACOES) + r")\."
    protegido = re.sub(padrao_abrev, _proteger, texto, flags=re.IGNORECASE)

    partes = re.split(r"(?<=[.!?])\s+", protegido)
    return [p.replace("\x00", ".").strip() for p in partes if p.strip()]


def _concatenar_com_pausas(caminhos: list[Path], destino: Path,
                            pausa_s: float = _PAUSA_ENTRE_FRASES_S) -> Path:
    """Junta os áudios de cada frase em sequência, com uma pausa curta e
    fixa entre elas (o silêncio natural de troca de frase de um narrador,
    não o silêncio de início/fim que o TTS já bota em cada pedaço isolado)."""
    if len(caminhos) == 1:
        shutil.copy(caminhos[0], destino)
        return destino

    cmd = ["ffmpeg", "-y"]
    for c in caminhos:
        cmd += ["-i", str(c)]

    n = len(caminhos)
    filtros, rotulos = [], []
    for i in range(n):
        if i < n - 1:
            filtros.append(f"[{i}:a]apad=pad_dur={pausa_s}[a{i}]")
            rotulos.append(f"[a{i}]")
        else:
            rotulos.append(f"[{i}:a]")
    filtro = ";".join(filtros) + ";" + "".join(rotulos) + f"concat=n={n}:v=0:a=1[out]"

    cmd += ["-filter_complex", filtro, "-map", "[out]", "-ar", "44100", str(destino)]
    midia.roda(cmd)
    return destino


def gerar_trilha(segmentos: list[dict], duracao_total: float, trabalho: Path,
                  amostra_voz: Path, idioma: str = IDIOMA_PADRAO
                  ) -> tuple[Path | None, list[dict]]:
    """Mesma interface de dublagem.gerar_trilha, mas com a voz clonada.

    Sintetiza FRASE POR FRASE (não um trechinho por janela de ~4s, que
    cortava no meio da frase e dessincronizava as pausas da legenda; nem o
    trecho inteiro numa síntese só, que saiu arrastado e com dicção ruim —
    o Chatterbox não é feito pra 90s contínuos, ver `_dividir_frases`),
    concatena com uma pausa curta fixa entre frases, e só então ajusta a
    duração total do resultado pro tamanho do clipe (um único atempo suave
    no final, não por pedaço).

    Devolve (caminho_do_audio, timing) — timing é [{frase, inicio, fim}]
    no timeline REAL do áudio final (já contando a pausa entre frases e o
    atempo aplicado no fim). O timing do texto original (baseado no vídeo
    fonte) não bate mais com esse áudio — a legenda tem que usar ESSE
    timing, não o dos `segmentos` de entrada (Bryan reportou legenda
    "correndo" em 05/08/2026 quando ela ainda seguia o timing antigo)."""
    if not segmentos:
        return None, []
    if not amostra_voz.exists():
        raise RuntimeError(f"amostra de voz não encontrada: {amostra_voz}")

    texto_completo = " ".join(
        seg["texto"].strip() for seg in segmentos if seg["texto"].strip())
    frases = _dividir_frases(texto_completo)
    if not frases:
        return None, []

    trabalho.mkdir(parents=True, exist_ok=True)
    partes, duracoes = [], []
    for i, frase in enumerate(frases):
        p = trabalho / f"voz_frase_{i:03d}.wav"
        _falar(frase, p, amostra_voz, idioma)
        partes.append(p)
        duracoes.append(midia.duracao(p))

    concatenado = trabalho / "voz_concatenada.wav"
    _concatenar_com_pausas(partes, concatenado)
    dur_concatenada = midia.duracao(concatenado)

    destino = trabalho / "trilha_dublada_clonada.wav"
    _ajustar_duracao(concatenado, duracao_total, destino)
    # narração mais curta que o clipe = preenchida com silêncio no final,
    # SEM mexer no ritmo (ver _ajustar_duracao) — o timing de cada frase
    # não muda. Só quando acelera (narração mais longa) é que o timing
    # precisa ser comprimido na mesma proporção.
    if dur_concatenada <= duracao_total:
        escala = 1.0
    else:
        dur_final = midia.duracao(destino)
        escala = (dur_final / dur_concatenada) if dur_concatenada > 0 else 1.0

    # diagnóstico: narração mais curta = sobra silêncio no fim (ritmo
    # natural, não desacelera mais); mais longa = acelera até 1.6x (acima
    # disso ainda fica corrido). Medir aqui em vez de adivinhar pela
    # duração do run (foi assim que achamos o problema de lentidão em
    # 05/08/2026, run 31037313597, sem esse print).
    if dur_concatenada <= duracao_total:
        print(f"      {len(frases)} frase(s), narração {dur_concatenada:.1f}s "
              f"pro clipe de {duracao_total:.1f}s "
              f"({duracao_total - dur_concatenada:.1f}s de silêncio no final, ritmo natural)")
    else:
        fator_atempo = min(1.6, dur_concatenada / max(0.1, duracao_total))
        print(f"      {len(frases)} frase(s), narração {dur_concatenada:.1f}s "
              f"pro clipe de {duracao_total:.1f}s (acelerando {fator_atempo:.2f}x"
              f"{' — NO TETO, ainda vai soar corrido' if fator_atempo >= 1.6 else ''})")

    timing, t = [], 0.0
    for frase, dur in zip(frases, duracoes):
        timing.append({"frase": frase, "inicio": t * escala,
                        "fim": (t + dur) * escala})
        t += dur + _PAUSA_ENTRE_FRASES_S

    return destino, timing
