# -*- coding: utf-8 -*-
"""Teste do teto de tempo dos subprocessos (`midia.roda`).

POR QUE EXISTE

Em 31/08/2026 os runs #188 e #189 morreram no teto de 6h do GitHub Actions.
Nenhum dos dois era lento — trabalharam 19,8 e 23,1 minutos e depois ficaram
5,52h e 5,56h em silencio absoluto: sem erro, sem traceback, sem OOM, com
109 GB de disco livre. No fim o runner matou dois orfaos, `python` e `ffmpeg`.

Foram ~12h de runner queimadas, e o log nao diz onde parou.

⚠️ O TIMEOUT NAO CONSERTA A CAUSA. Ele troca "6h perdidas em silencio" por
"erro em N minutos, com o comando no log". E' instrumento de diagnostico.

O CASO NEGATIVO, que e' o que este teste protege de verdade

Um teto mal posto e' PIOR que teto nenhum: ele mata render legitimo no meio e
a falha parece defeito do motor. Entao nao basta provar que o timeout dispara
— tem de provar que ele NAO dispara em comando normal, e que o caminho de
sucesso continua devolvendo o que devolvia.

Roda com: python teste/teste_timeout_midia.py
"""
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from engine import midia  # noqa: E402

falhas = []


def checar(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


print(__doc__.splitlines()[0])

# --- 1. cobertura: nenhuma chamada pode ter ficado sem teto ---------------
print("\n[1] nenhum subprocess.run do midia.py sem timeout")
import ast  # noqa: E402
fonte = (RAIZ / "engine" / "midia.py").read_text(encoding="utf-8")
linhas = fonte.splitlines()
sem = []
for n in ast.walk(ast.parse(fonte)):
    if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "run"
            and getattr(getattr(n.func, "value", None), "id", "") == "subprocess"):
        bloco = "\n".join(linhas[n.lineno - 1:getattr(n, "end_lineno", n.lineno)])
        if "timeout" not in bloco:
            sem.append(n.lineno)
checar(not sem, f"todas cobertas (sem teto: {sem or 'nenhuma'})")
checar(midia.TIMEOUT_PADRAO >= 900,
       f"TIMEOUT_PADRAO={midia.TIMEOUT_PADRAO}s — folgado o bastante pra render")
checar(midia.TIMEOUT_SONDA <= 300,
       f"TIMEOUT_SONDA={midia.TIMEOUT_SONDA}s — curto, e' so' metadado")

# --- 2. o caso POSITIVO: um comando travado morre no teto ----------------
print("\n[2] comando que trava e' derrubado, com diagnostico")
dorminhoco = [sys.executable, "-c", "import time; time.sleep(30)"]
t0 = time.monotonic()
try:
    midia.roda(dorminhoco, timeout=2)
except midia.TravouError as e:
    gasto = time.monotonic() - t0
    checar(gasto < 8, f"derrubou em {gasto:.1f}s, nao esperou os 30s")
    txt = str(e)
    checar("TRAVOU" in txt, "a mensagem diz TRAVOU")
    checar("passou de 2s" in txt, "a mensagem diz qual era o teto")
    checar(sys.executable in txt or "time.sleep" in txt,
           "a mensagem traz o COMANDO INTEIRO (nao so' os 3 primeiros itens)")
except Exception as e:
    checar(False, f"levantou {type(e).__name__} em vez de TravouError: {e}")
else:
    checar(False, "NAO levantou nada — o timeout nao esta' ligado")

# --- 3. o caso NEGATIVO: comando normal nao pode ser morto ---------------
print("\n[3] comando normal passa, e o retorno continua o mesmo")
rapido = [sys.executable, "-c", "print('oi')"]
try:
    r = midia.roda(rapido, silencioso=False, timeout=30)
    checar(r.returncode == 0, "comando rapido termina com codigo 0")
except Exception as e:
    checar(False, f"comando normal foi derrubado: {type(e).__name__}: {e}")

# --- 4. erro de verdade continua sendo erro de verdade -------------------
print("\n[4] falha de comando nao vira TravouError por engano")
quebrado = [sys.executable, "-c", "import sys; sys.exit(3)"]
try:
    midia.roda(quebrado, timeout=30)
except midia.TravouError:
    checar(False, "confundiu returncode!=0 com travamento")
except RuntimeError:
    checar(True, "returncode!=0 continua RuntimeError, nao TravouError")
else:
    checar(False, "nao levantou nada para returncode 3")

# --- 5. TravouError e' pegavel como RuntimeError -------------------------
print("\n[5] quem ja' pegava RuntimeError continua pegando")
checar(issubclass(midia.TravouError, RuntimeError),
       "TravouError herda de RuntimeError — nada que capturava antes quebra")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("tudo verde")
