# -*- coding: utf-8 -*-
"""Falha num clipe nao derruba os que ja' ficaram prontos.

⚠️ MEDIDO no run #229 (01/09/2026): o clipe 1 teve as 35 frases sintetizadas
— 1835 segundos, meia hora de TTS — e o run morreu ao traduzir o clipe 2, por
cota do Gemini. Setenta minutos de runner embora com trabalho PRONTO dentro.
O mesmo padrao nos #205 e #211.

⚠️ CASO NEGATIVO, e e' o que importa: run em que NENHUM clipe vinga tem de
FRACASSAR. Isolar clipe existe pra salvar o que sobreviveu, nao pra pintar de
verde um run vazio — o passo seguinte publicaria release sem video e o
agendador nao teria o que enfileirar, tudo "com sucesso". Falha silenciosa e'
o modo que esta maquinaria mais custou a extirpar.
"""
import ast
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
arv = ast.parse(io.open(RAIZ / "main.py", encoding="utf-8").read())
falhas = []

laco = None
for no in ast.walk(arv):
    if isinstance(no, ast.For) and getattr(no.iter, "func", None) is not None:
        alvo = getattr(no.iter.func, "id", "")
        if alvo == "enumerate" and isinstance(no.target, ast.Tuple):
            if len(no.body) == 1 and isinstance(no.body[0], ast.Try):
                laco = no
                break

if laco is None:
    falhas.append("o laco dos clipes nao esta' protegido por try — "
                  "uma falha no clipe 2 leva o clipe 1 junto")
else:
    manipuladores = laco.body[0].handlers
    if not manipuladores:
        falhas.append("try sem except")
    else:
        corpo = ast.dump(manipuladores[0])
        if "continue" not in corpo.lower() and "Continue" not in corpo:
            falhas.append("o except nao continua — ainda aborta o run")
        if "print" not in corpo:
            falhas.append("o except ENGOLE o erro: sem print, a falha some")

# NEGATIVO — run sem clipe nenhum tem de sair com erro
fonte = io.open(RAIZ / "main.py", encoding="utf-8").read()
if "if not resumo:" not in fonte or "sys.exit(1)" not in fonte:
    falhas.append("run com ZERO clipes nao fracassa — viraria sucesso vazio")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_clipe_isolado: clipe isolado, erro registrado, "
      "run vazio ainda fracassa")
