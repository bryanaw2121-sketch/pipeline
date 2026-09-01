# -*- coding: utf-8 -*-
"""O nucleo compartilhado nao pode derivar do canonico.

⚠️ ESTE TESTE E' O CONSERTO DO PROBLEMA QUE CUSTOU O DIA. Em 01/09/2026 tres
reparos feitos no Modo-Futuro nunca chegaram aqui, e os runs #23 e #24 deste
motor bateram exatamente nos tres — dois runs de ~90 minutos perdidos por
deriva que ninguem via.

Agora a deriva REPROVA A SUITE. Sai de "silenciosa" para "impossivel de
ignorar", que e' a unica diferenca que importa.

⚠️ FALHA SO' POR DIVERGENCIA, NUNCA POR REDE. Sem internet, o teste PASSA com
aviso: reprovar a suite porque o GitHub esta' fora trocaria um problema real
por alarme falso — e alarme falso ensina a ignorar o alarme.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
r = subprocess.run([sys.executable, "-X", "utf8",
                    str(RAIZ / "sincronizar_nucleo.py")],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=str(RAIZ))
saida = (r.stdout or "") + (r.stderr or "")

if "nao conferido" in saida:
    import re
    m = re.search(r"(\d+) nao conferido", saida)
    if m and int(m.group(1)) > 0:
        print(f"  [aviso] {m.group(1)} modulo(s) nao conferido(s) — rede?")
        print("[ok] teste_nucleo: sem veredito (rede), suite nao reprova por isso")
        sys.exit(0)

if r.returncode != 0:
    print("  [x] o nucleo DIVERGIU do canonico:")
    for l in saida.splitlines():
        if "DIVERGE" in l or "divergente" in l:
            print("     ", l.strip())
    print("      -> rode: python sincronizar_nucleo.py --aplicar")
    sys.exit(1)

print("[ok] teste_nucleo: " + next(
    (l for l in saida.splitlines() if l.startswith("nucleo:")), "identico"))
