"""Legendas palavra a palavra, via Groq.

Só recebe clipes de ~1 min (≈1 MB), então o limite de 25 MB do free tier
nunca é atingido. O vídeo de 1 hora não passa por aqui.
"""
import time
from pathlib import Path
import requests

import config
from . import keys, midia


def palavras(audio_clipe: Path, idioma: str | None = "pt") -> list[dict]:
    """Devolve [{palavra, inicio, fim}] com tempo RELATIVO ao clipe."""
    tam = midia.mb(audio_clipe)
    if tam > config.GROQ_LIMITE_MB:
        raise RuntimeError(
            f"{audio_clipe.name} tem {tam:.1f} MB, acima do limite de "
            f"{config.GROQ_LIMITE_MB} MB. Clipe longo demais?"
        )

    rot = keys.groq()
    for _ in range(len(rot) * 2):
        chave = rot.proxima()
        try:
            with open(audio_clipe, "rb") as fh:
                dados = {
                    "model": (None, config.GROQ_MODELO),
                    "response_format": (None, "verbose_json"),
                    "timestamp_granularities[]": (None, "word"),
                    "file": (audio_clipe.name, fh, "audio/flac"),
                }
                if idioma:
                    dados["language"] = (None, idioma)
                r = requests.post(
                    config.GROQ_URL,
                    headers={"Authorization": f"Bearer {chave}"},
                    files=dados,
                    timeout=300,
                )
            if r.status_code == 429:
                rot.queimar(chave)
                time.sleep(1)
                continue
            r.raise_for_status()
            js = r.json()
            saida = [
                {"palavra": w["word"].strip(),
                 "inicio": float(w["start"]),
                 "fim": float(w["end"])}
                for w in js.get("words", []) if w.get("word", "").strip()
            ]
            if saida:
                return saida
            # sem word-level: cai pro texto corrido (raro, mas acontece)
            return _do_texto(js.get("text", ""), audio_clipe)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (429, 401, 403):
                rot.queimar(chave)
                continue
            raise
        except Exception as e:
            print(f"   [!] Groq falhou: {e}")
            time.sleep(2)
    print("   [!] sem transcrição para este clipe — segue sem legenda")
    return []


def _do_texto(texto: str, audio: Path) -> list[dict]:
    """Fallback: distribui as palavras igualmente na duração. Impreciso,
    mas melhor que clipe sem legenda nenhuma."""
    ps = texto.split()
    if not ps:
        return []
    dur = midia.duracao(audio)
    passo = dur / len(ps)
    return [{"palavra": p, "inicio": i * passo, "fim": (i + 1) * passo}
            for i, p in enumerate(ps)]
