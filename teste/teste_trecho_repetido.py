# -*- coding: utf-8 -*-
"""Mesma FONTE + mesmo SEGUNDO = mesmo clipe, mesmo com titulo diferente.

⚠️ ACONTECEU EM 02/09/2026, tres vezes na fila da cozinha:

    "Ramen de Carne com Legumes em Uma So Panela"        inicio 613,1s
    "Lamen de Carne Moida com Legumes em Uma Panela So"  inicio 613,1s

O mesmo bruto foi cortado em dois dias diferentes; o Gemini escolheu o MESMO
trecho — era o melhor — e traduziu diferente. As tres guardas existentes
passaram:

  hash   render novo -> arquivo novo -> sha diferente
  texto  a dedup compara PREFIXO, e "ramen" x "lamen" diferem na 1a letra
  fonte  o manifesto guardava "fonte.mp4" em TODAS as entradas — o nome que o
         runner da' ao baixar. Nao dava pra saber de que video o clipe veio.

⚠️ CASO NEGATIVO 1: clipe SEM `fonte_id` tem de passar. O manifesto anterior a
02/09 nao tem o campo, e recusar por ausencia de dado travaria todo o acervo.

⚠️ CASO NEGATIVO 2: mesma fonte em segundo DIFERENTE tem de passar — sao dois
cortes legitimos do mesmo video, que e' o funcionamento normal.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
falhas = []

vistos = {("bruto_A", 613.1), ("bruto_A", 11.7)}


def trecho_ja_usado(v) -> bool:
    """A guarda como esta' no agendar_buffer."""
    f, i = v.get("fonte_id"), v.get("inicio_s")
    if not f or i is None:
        return False
    return (f, round(float(i), 1)) in vistos


# 1. POSITIVO — mesmo trecho, titulo traduzido diferente
if not trecho_ja_usado({"fonte_id": "bruto_A", "inicio_s": 613.1,
                        "titulo": "Lamen de Carne Moida"}):
    falhas.append("nao recusou o MESMO trecho com titulo diferente")
# e o arredondamento nao pode deixar escapar por milesimos
if not trecho_ja_usado({"fonte_id": "bruto_A", "inicio_s": 613.14}):
    falhas.append("613,14 escapou — o arredondamento nao esta' valendo")

# 2. NEGATIVO — mesma fonte, OUTRO segundo: e' clipe legitimo
if trecho_ja_usado({"fonte_id": "bruto_A", "inicio_s": 225.1}):
    falhas.append("recusou outro trecho do mesmo video — quebraria o normal")

# 3. NEGATIVO — outra fonte, mesmo segundo: coincidencia, nao duplicata
if trecho_ja_usado({"fonte_id": "bruto_B", "inicio_s": 613.1}):
    falhas.append("recusou trecho de OUTRO video que comeca no mesmo segundo")

# 4. NEGATIVO — sem fonte_id (manifesto antigo) tem de passar
if trecho_ja_usado({"inicio_s": 613.1}):
    falhas.append("recusou entrada antiga sem fonte_id — travaria o acervo")
if trecho_ja_usado({"fonte_id": "bruto_A"}):
    falhas.append("recusou entrada sem inicio_s")

# 5. a guarda existe MESMO no agendador, nao so' aqui
import io  # noqa: E402
fonte = io.open(Path(__file__).resolve().parent.parent / "agendar_buffer.py",
                encoding="utf-8").read()
if "trecho_ja_usado" not in fonte:
    falhas.append("o agendador nao tem a guarda de trecho")
if "fonte_id" not in fonte:
    falhas.append("o agendador nao le' fonte_id")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_trecho_repetido: mesmo trecho recusado, outro trecho e "
      "entrada antiga passam")
