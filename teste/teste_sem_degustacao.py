# -*- coding: utf-8 -*-
"""O criterio de receita tem de PROIBIR degustacao, e so' ela.

⚠️ O ERRO FOI REAL, em 31/08/2026: o run escolheu dois momentos do video da
Levain Bakery — um ensinando a assar o cookie, outro com as pessoas PROVANDO
o cookie comprado na loja. O segundo foi agendado; o Bryan apagou.

⚠️ E o corte nao tinha defeito. Comida na tela, apetite, fala boa, duracao
certa, unidade completa: passava em TODOS os criterios que existiam. Nao foi
o criterio que errou ao aplicar as regras — faltava a regra.

⚠️ CASO NEGATIVO: a proibicao nao pode derrubar o que o canal EXISTE pra
fazer. Um prompt que dissesse "nao escolha nada com comida sendo comida"
mataria o prato pronto no fim da receita, que e' o clímax do corte.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import selecao  # noqa: E402

p = selecao.PROMPT_RECEITA
falhas = []

for termo in ("DEGUSTACAO", "PROVA", "RESENHA"):
    if termo not in p:
        falhas.append(f"o criterio nao fala em {termo}")
if "ZERO momentos" not in p:
    falhas.append("nao manda devolver zero quando a fonte INTEIRA e' degustacao")

# NEGATIVO — o que o canal existe pra fazer continua pedido
for essencial in ("prato pronto", "INGREDIENTE", "receita inteira", "apetite"):
    if essencial.lower() not in p.lower():
        falhas.append(f"a proibicao comeu um criterio essencial: {essencial!r}")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_sem_degustacao: degustacao proibida, preparo intacto")
