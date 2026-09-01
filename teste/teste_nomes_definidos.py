# -*- coding: utf-8 -*-
"""Nenhum script usa nome que nao existe. Estatico, sem executar nada.

⚠️ O ERRO QUE ISTO PEGA JA' ACONTECEU EM PRODUCAO. Em 01/09/2026 a guarda de
canal em estreia foi pro ar com o import faltando, e o `agendar_buffer` morreu
no run #221 com

    NameError: name 'estreia' is not defined

depois de 40 minutos de corte, dublagem e render ja' pagos.

⚠️ E A MINHA PRIMEIRA TENTATIVA DE TESTE NAO PEGAVA. Escrevi um teste que
apenas IMPORTAVA cada script: ele passou verde com o import removido, porque
o NameError so' acontece quando a funcao roda. Um detector que nao reprova o
caso conhecido nao e' detector — foi o caso negativo que denunciou isso, nao
a intuicao.

Este aqui e' estatico: le' o codigo e cobra que todo nome usado exista.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

alvos = sorted(p for p in RAIZ.glob("*.py") if not p.name.startswith("_"))
alvos += sorted((RAIZ / "engine").glob("*.py"))

r = subprocess.run([sys.executable, "-m", "pyflakes", *[str(p) for p in alvos]],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
if r.returncode not in (0, 1):
    print(f"  [!] pyflakes indisponivel ({r.stderr.strip()[:60]}) — pulando")
    sys.exit(0)

# ⚠️ SO' "undefined name". pyflakes tambem reclama de import nao usado e
# estrela de import; isso e' estilo, nao defeito, e travar a suite por estilo
# faria alguem desligar o teste inteiro.
graves = [l for l in (r.stdout or "").splitlines() if "undefined name" in l]
if graves:
    for l in graves:
        print("  [x]", l.replace(str(RAIZ), "."))
    sys.exit(1)
print(f"[ok] teste_nomes_definidos: {len(alvos)} arquivos, nenhum nome solto")
