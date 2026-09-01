# -*- coding: utf-8 -*-
"""A mensagem de erro da traducao tem que dizer COTA quando e' cota.

O run #200 (31/08/2026) morreu com "traducao falhou em todas as chaves:
None". As 20 chaves do Gemini estavam sem cota — o log dizia isso 20 vezes,
uma linha por chave — mas a excecao final apagava a causa: o caminho 429/403
fazia `continue` sem tocar em `ultimo_erro`.

⚠️ CASO NEGATIVO OBRIGATORIO. Um teste que so' confere o caso da cota passa
tambem numa versao que grite "SEM COTA" em TODA falha — e ai' o erro de rede
viraria "espere o reset", que e' conselho errado. Por isso o segundo caso.
"""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import traducao  # noqa: E402


class _Resposta:
    def __init__(self, status): self.status_code = status
    def raise_for_status(self): pass
    def json(self): return {}


def _erro(post):
    with mock.patch.object(traducao.requests, "post", post), \
         mock.patch.object(traducao.time, "sleep", lambda *_: None):
        try:
            traducao._traduzir_texto("qualquer coisa")
        except RuntimeError as e:
            return str(e)
    raise AssertionError("devia ter levantado RuntimeError")


falhas = []

# 1. POSITIVO — toda chave responde 429. Tem que falar de cota, e nao de None.
m = _erro(lambda *a, **k: _Resposta(429))
if "COTA" not in m.upper():
    falhas.append(f"cota nao nomeada: {m!r}")
if "None" in m:
    falhas.append(f"a causa continua apagada como None: {m!r}")

# 2. NEGATIVO — erro que NAO e' cota. Nao pode virar conselho de esperar reset.
def _cai(*a, **k):
    raise ConnectionError("cabo arrancado")

m2 = _erro(_cai)
if "SEM COTA" in m2.upper() or "reset" in m2:
    falhas.append(f"erro de rede vendido como cota: {m2!r}")
if "cabo arrancado" not in m2:
    falhas.append(f"a causa real sumiu da mensagem: {m2!r}")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_erro_cota: cota nomeada, e erro de rede nao vira cota")
