"""Pós-produção leve, 100% CPU (sem upscaler de IA — esses precisam de GPU,
que o runner grátis do GitHub Actions não tem, e ficariam lentos demais pra
caber num pipeline noturno).

Duas camadas, as duas nativas do ffmpeg, sem asset externo (sem LUT baixado
de terceiro, sem modelo):

1. `estabilizar()` — vidstab (libvidstab, 2 passes: detectar tremedeira,
   depois compensar). Falha de forma segura: se o ffmpeg do ambiente não
   tiver vidstab compilado, devolve o vídeo original sem quebrar o run.
2. `FILTRO_COR_CINEMATICO` — grade de cor tipo documentário (contraste leve
   +sombras puxadas pro azul/verde, meio-tom neutro, luz puxada pro quente),
   feita só com `curves`/`eq` do ffmpeg — sem LUT externo pra não depender
   de licença de terceiro nem arquivo extra no repositório.
"""
from pathlib import Path

from . import midia

FILTRO_COR_CINEMATICO = (
    ",eq=contrast=1.08:saturation=1.05,"
    "curves=r='0/0.02 0.5/0.5 1/0.98':b='0/0.05 0.5/0.52 1/1'"
)


def estabilizar(bruto: Path, destino: Path) -> Path:
    """2 passes de vidstab. Se o filtro não existir no ffmpeg do ambiente
    (compilado sem libvidstab), devolve `bruto` sem alteração — estabilizar
    é bônus, não pode derrubar o render."""
    trf = destino.with_suffix(".trf")
    try:
        midia.roda([
            "ffmpeg", "-y", "-i", str(bruto),
            "-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={trf}",
            "-f", "null", "-",
        ])
        midia.roda([
            "ffmpeg", "-y", "-i", str(bruto),
            "-vf", f"vidstabtransform=input={trf}:zoom=0:smoothing=10,"
                   "unsharp=5:5:0.8:3:3:0.4",
            "-c:a", "copy",
            str(destino),
        ])
        return destino
    except Exception as e:
        print(f"   [!] estabilização pulada (vidstab indisponível?): {e}")
        return bruto
    finally:
        trf.unlink(missing_ok=True)
