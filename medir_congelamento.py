# -*- coding: utf-8 -*-
"""Mede quanto tempo a imagem fica parada num video, pra calibrar o filtro.

POR QUE EXISTE
`config.CONGELAMENTO_MAX_S = 4.5` descarta candidato com bloco parado acima
disso. O 4,5 foi medido contra ENTREVISTA. Em 28/08/2026 ele rejeitou um video
de receita INTEIRO ("todos os momentos tinham camera travada"), e o projeto
vinha dizendo desde o inicio que o numero certo pra cozinha teria que sair
MEDINDO, nunca por chute.

Este script produz o dado: a distribuicao dos blocos parados. Com ela da' pra
separar dois casos que o filtro confunde:
  - plano bonito de comida parado 6-8s -> o limiar esta' baixo demais
  - slideshow / texto na tela por 30s+ -> o filtro esta' certo, a fonte e' ruim

Roda na nuvem (ver .github/workflows/medir_congelamento.yml) porque a maquina
do Bryan e' limitada e ele pediu nada de processamento pesado nela.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys


def blocos(caminho: str, limiar_db: int = -60, dur_min: float = 1.0) -> list[float]:
    """Duracao de cada bloco de imagem parada, em segundos."""
    r = subprocess.run(
        ["ffmpeg", "-i", caminho, "-vf", f"freezedetect=n=-{abs(limiar_db)}dB:d={dur_min}",
         "-map", "0:v:0", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore")
    return [float(x) for x in re.findall(r"freeze_duration:\s*([\d.]+)", r.stderr)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("arquivo")
    a = p.parse_args()
    d = sorted(blocos(a.arquivo), reverse=True)
    if not d:
        print("nenhum bloco parado detectado — o filtro nao deveria rejeitar nada aqui")
        return
    total = sum(d)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", a.arquivo], capture_output=True, text=True)
    try:
        dur_total = float(dur.stdout.strip())
    except ValueError:
        dur_total = 0.0
    print(f"blocos parados: {len(d)}")
    print(f"tempo parado somado: {total:.1f}s de {dur_total:.1f}s "
          f"({100*total/dur_total if dur_total else 0:.0f}% do video)")
    print()
    print("os 12 maiores (segundos):")
    print("  " + "  ".join(f"{x:.1f}" for x in d[:12]))
    print()
    for corte in (4.5, 6, 8, 10, 15, 20):
        acima = sum(1 for x in d if x > corte)
        print(f"  limiar {corte:5.1f}s -> {acima:3d} bloco(s) acima "
              f"({100*acima/len(d):3.0f}% dos blocos)")
    print()
    if total / (dur_total or 1) > 0.5:
        print("VEREDITO: mais de metade do video e' imagem parada. Isso e' slideshow,")
        print("nao plano de comida. O filtro esta' CERTO em rejeitar — a fonte e' ruim.")
    else:
        print("VEREDITO: a imagem se mexe na maior parte do tempo. Os blocos parados")
        print("sao planos, nao slideshow. Subir o limiar acima do maior bloco util.")


if __name__ == "__main__":
    main()
