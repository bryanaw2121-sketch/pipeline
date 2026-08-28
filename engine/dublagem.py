"""Dublagem pt-BR via edge-tts (gratuito, sem chave de API).

Não clona a voz original — troca por uma voz de TTS. Cada segmento
traduzido (engine.traducao.traduzir_segmentos) vira um trechinho de áudio,
esticado/comprimido com ffmpeg atempo pra caber na janela de tempo do
trecho original, e todos os trechos são posicionados na linha do tempo
formando a trilha dublada completa do clipe.
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

from . import midia

VOZ_PADRAO = "pt-BR-AntonioNeural"
_ATEMPO_MIN, _ATEMPO_MAX = 0.7, 1.6   # fora disso a voz fica robótica/irreconhecível


def _exige_edge_tts():
    if not shutil.which("edge-tts"):
        raise RuntimeError("'edge-tts' não encontrado. Rode: pip install edge-tts")


async def _sintetizar(texto: str, destino: Path, voz: str):
    import edge_tts
    from . import numeros
    # Mesmo conserto do voz_clonada: o defeito e' dos dois caminhos de
    # TTS, nao so' do que estava ativo em 22/08/2026.
    comm = edge_tts.Communicate(numeros.por_extenso(texto), voice=voz)
    await comm.save(str(destino))


def _falar(texto: str, destino: Path, voz: str) -> Path:
    asyncio.run(_sintetizar(texto, destino, voz))
    return destino


def _ajustar_duracao(audio: Path, alvo_s: float, destino: Path) -> Path:
    """Estica/comprime o áudio pra caber em `alvo_s` segundos, dentro de um
    limite razoável de velocidade (fala 2x mais rápida vira ruído)."""
    dur = midia.duracao(audio)
    if dur <= 0:
        shutil.copy(audio, destino)
        return destino

    fator = dur / max(0.1, alvo_s)   # >1 = fala rápido demais, precisa acelerar
    fator = max(_ATEMPO_MIN, min(_ATEMPO_MAX, fator))

    midia.roda(["ffmpeg", "-y", "-i", str(audio),
                "-filter:a", f"atempo={fator:.3f}",
                "-ar", "44100", str(destino)])
    return destino


def gerar_trilha(segmentos: list[dict], duracao_total: float, trabalho: Path,
                  voz: str = VOZ_PADRAO) -> Path | None:
    """Gera a trilha de áudio dublada (pt-BR) do tamanho do clipe inteiro,
    com cada trecho traduzido posicionado no tempo do trecho original.

    Devolve None se não houver segmento nenhum (clipe sem fala)."""
    _exige_edge_tts()
    if not segmentos:
        return None

    trabalho.mkdir(parents=True, exist_ok=True)
    partes = []   # (inicio_s, caminho_wav_ajustado)
    for i, seg in enumerate(segmentos):
        texto = seg["texto"].strip()
        if not texto:
            continue
        bruto = trabalho / f"tts_{i:03d}.mp3"
        _falar(texto, bruto, voz)
        janela = max(0.3, seg["fim"] - seg["inicio"])
        ajustado = trabalho / f"tts_{i:03d}_ok.wav"
        _ajustar_duracao(bruto, janela, ajustado)
        partes.append((seg["inicio"], ajustado))

    if not partes:
        return None

    destino = trabalho / "trilha_dublada.wav"
    _mixar(partes, duracao_total, destino)
    return destino


def _mixar(partes: list[tuple[float, Path]], duracao_total: float, destino: Path) -> Path:
    """Posiciona cada trecho na linha do tempo com adelay e mixa tudo com
    uma base de silêncio do tamanho do clipe inteiro."""
    cmd = ["ffmpeg", "-y",
           "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duracao_total:.3f}"]
    for _, caminho in partes:
        cmd += ["-i", str(caminho)]

    filtros = []
    entradas_mix = ["[0:a]"]
    for i, (inicio, _) in enumerate(partes, start=1):
        ms = max(0, int(inicio * 1000))
        filtros.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        entradas_mix.append(f"[a{i}]")

    filtro_final = ";".join(filtros)
    filtro_final += f";{''.join(entradas_mix)}amix=inputs={len(entradas_mix)}:normalize=0[out]"

    cmd += ["-filter_complex", filtro_final, "-map", "[out]",
            "-ar", "44100", str(destino)]
    midia.roda(cmd)
    return destino
