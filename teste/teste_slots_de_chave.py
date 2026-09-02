# -*- coding: utf-8 -*-
"""Todo secret de chave gravado tem de estar MAPEADO nos workflows.

⚠️ GRAVAR O SECRET NAO BASTA, e essa lacuna ja' custou hoje. O `keys.Rotador`
le' VARIAVEL DE AMBIENTE; o secret so' vira variavel se o workflow o mapear.
Em 01/09/2026 o passo da fila mapeava `GEMINI_API_KEY_2.._5` — nomes que nem
existiam — e a sonda enxergava DUAS chaves de vinte, decidindo o teto de corte
com essa amostra.

⚠️ E O TETO DO RODIZIO TAMBEM CONTA. O `Rotador` varre `_2` ate' `_40`; chave
em slot acima disso existe no repositorio, aparece na listagem e NUNCA entra
no rodizio. Ja' aconteceu com o slot 21.
"""
import glob
import io
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
falhas = []

# ate' onde o Rotador enxerga
rot = io.open(RAIZ / "engine/keys.py", encoding="utf-8").read()
m = re.search(r"for i in range\(2,\s*(\d+)\)", rot)
teto_rot = int(m.group(1)) - 1 if m else 0
if teto_rot < 27:
    falhas.append(f"o Rotador so' le' ate' o slot {teto_rot}; ha' chaves acima disso")

# quais slots cada workflow de CORTE mapeia
for arq in sorted(glob.glob(str(RAIZ / ".github/workflows/*.yml"))):
    s = io.open(arq, encoding="utf-8").read()
    nums = sorted(int(n or 1) for n in
                  re.findall(r"GEMINI_API_KEY(?:_(\d+))?:", s))
    if not nums:
        continue          # workflow que nao corta nem sonda
    nome = Path(arq).name
    buracos = [n for n in range(1, max(nums) + 1) if n not in nums]
    if buracos:
        falhas.append(f"{nome}: buraco nos slots {buracos} — "
                      "chave gravada que o motor nunca le'")
    if max(nums) > teto_rot:
        falhas.append(f"{nome}: mapeia ate' o slot {max(nums)}, "
                      f"mas o Rotador so' le' ate' {teto_rot}")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print(f"[ok] teste_slots_de_chave: sem buracos, e o Rotador cobre ate' {teto_rot}")
