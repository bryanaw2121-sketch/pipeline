"""Organiza uma cópia dos clipes prontos numa pasta no Desktop, na mesma
estrutura do Drive (subir_drive.py): pasta de nota (7/8/9) -> pasta do dia
(DD-MM, data do lote) -> vídeo + legenda em .txt ao lado.

Não mexe em `saida/` nem nos registros de envio do TikTok/Drive — é só uma
cópia organizada pra navegar localmente. Roda de novo a qualquer momento
pra pegar lotes novos (pula o que já foi copiado).

    python organizar_desktop.py
    python organizar_desktop.py --destino "C:\\Users\\T3610\\Desktop\\Outputs TikTok"
"""
import argparse
import json
import shutil
from pathlib import Path

import config
from publicar_tiktok import legenda_do_clipe

PADRAO_DESTINO = Path.home() / "Desktop" / "Outputs TikTok"


def _pasta_por_nota(nota: float) -> str:
    if nota >= 90:
        return "9"
    if nota >= 80:
        return "8"
    return "7"


def _dia_do_lote(nome_lote: str) -> str:
    """'2026-07-26_2017' -> '26-07'. Se o nome não bater no formato esperado,
    usa o nome inteiro do lote como pasta (não perde o clipe)."""
    try:
        data = nome_lote.split("_")[0]          # '2026-07-26'
        ano, mes, dia = data.split("-")
        return f"{dia}-{mes}"
    except Exception:
        return nome_lote


def organizar(destino: Path):
    total = 0
    pulados = 0
    for pj in config.SAIDA.rglob("post.json"):
        clipe = pj.parent
        lote = clipe.parent.parent.name
        if lote in config.LOTES_IGNORADOS:
            continue
        video = clipe / "short_9x16.mp4"
        if not video.exists():
            continue
        try:
            nota = float(json.loads(pj.read_text(encoding="utf-8")).get("nota", 0))
        except Exception:
            nota = 0.0

        alvo = _pasta_por_nota(nota)
        dia = _dia_do_lote(lote)
        pasta_destino = destino / alvo / dia
        pasta_destino.mkdir(parents=True, exist_ok=True)

        nome_base = f"nota{int(nota)}_{clipe.name}"
        destino_video = pasta_destino / f"{nome_base}.mp4"
        destino_txt = pasta_destino / f"{nome_base}.txt"

        if destino_video.exists():
            pulados += 1
            continue

        shutil.copy2(video, destino_video)
        destino_txt.write_text(legenda_do_clipe(clipe), encoding="utf-8")
        print(f"  [{alvo}/{dia}] {nome_base}")
        total += 1

    print(f"\n{total} clipe(s) copiado(s), {pulados} já existiam. Destino: {destino}")


def main():
    p = argparse.ArgumentParser(description="Organiza os clipes prontos numa pasta no Desktop, por nota e dia")
    p.add_argument("--destino", default=str(PADRAO_DESTINO),
                   help=f"pasta de destino (padrão: {PADRAO_DESTINO})")
    a = p.parse_args()
    organizar(Path(a.destino))


if __name__ == "__main__":
    main()
