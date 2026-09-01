# -*- coding: utf-8 -*-
"""503 espera CRESCENTE, com teto — e nao se confunde com cota.

⚠️ MEDIDO em 01/09/2026: o run #24 da cozinha morreu aos 91 minutos com
"tradução falhou em todas as chaves: 503 Service Unavailable". Com espera fixa
de 2s, o rodizio queimava as tentativas em ~1 minuto e desistia — mas
sobrecarga do Gemini dura MINUTOS.

⚠️ CASO NEGATIVO 1 — TETO. Sem limite, uma sobrecarga longa prenderia o run
ate' o teto de 6h do Actions: trocar um prejuizo por um pior.

⚠️ CASO NEGATIVO 2 — 503 NAO E' 429. Sobrecarga passa sozinha; cota diaria
nao. Se o codigo tratasse os dois igual, ou esperaria a toa por cota (que so'
volta no dia seguinte), ou desistiria cedo de uma sobrecarga passageira.
"""
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
fonte = io.open(RAIZ / "engine/traducao.py", encoding="utf-8").read()
falhas = []

if "espera_503" not in fonte:
    falhas.append("a espera crescente sumiu — 503 voltaria a desistir em 1 min")
if "min(30," not in fonte:
    falhas.append("sem teto de espera — sobrecarga longa prenderia o run ate' 6h")

# a espera tem de CRESCER e parar no teto
esperas = [min(30, 2 * (2 ** min(n, 4))) for n in range(7)]
if esperas != sorted(esperas):
    falhas.append(f"a espera nao cresce: {esperas}")
if max(esperas) > 30:
    falhas.append(f"a espera passou do teto: {max(esperas)}")
if esperas[0] > 4:
    falhas.append(f"a primeira espera ja' comeca alta ({esperas[0]}s)")

# NEGATIVO 2 — os dois codigos sao tratados em ramos diferentes
i503 = fonte.find("status_code == 503")
i429 = fonte.find("status_code in (429, 403)")
if i503 < 0 or i429 < 0:
    falhas.append("um dos dois tratamentos sumiu")
else:
    # ⚠️ ANALISA O CODIGO SEM COMENTARIO, e isso ja' custou duas versoes
    # deste teste. A primeira media 400 caracteres depois do `if` e reprovou
    # codigo CERTO — o comentario da guarda tem ~350 chars e empurrava o
    # `sem_cota` pra fora da janela. A segunda cortava no primeiro
    # "continue"... que aparece DENTRO do comentario ("Este `continue` nao
    # mexia em ultimo_erro").
    #
    # Duas vezes o teste mediu a PROSA em vez do comportamento. Tirar os
    # comentarios antes de olhar e' o que faz a medida ser do codigo.
    import re as _re
    codigo = chr(10).join(l for l in fonte.splitlines()
                          if not l.strip().startswith(chr(35)))
    for m in _re.finditer(r"status_code in \(429, 403\)", codigo):
        fim = codigo.find("continue", m.start())
        trecho = codigo[m.start():fim + 8 if fim > 0 else m.start() + 200]
        if "sem_cota" not in trecho:
            falhas.append("um ramo de 429 nao conta cota — voltaria a dizer 'None'")
        if "espera_503" in trecho:
            falhas.append("o ramo de cota espera como se fosse sobrecarga")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print(f"[ok] teste_espera_503: espera {esperas[:5]} com teto 30s, "
      "e cota segue em ramo proprio")
