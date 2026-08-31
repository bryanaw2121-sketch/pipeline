# -*- coding: utf-8 -*-
"""O agendador tem de recusar por CONTEUDO, nao so' por texto.

⚠️ O CASO E' O ESTRAGO MEDIDO DE 31/08/2026: seis posts na fila do
@cozinha.internacional, seis titulos e seis legendas DIFERENTES, todos
apontando pro mesmo arquivo. Nenhuma dedup de texto podia ver isso — os
textos eram, de fato, todos diferentes. So' o sha denuncia.

⚠️ CASO NEGATIVO: clipe com sha DESCONHECIDO tem de passar. Uma guarda que
recusa tudo o que nao reconhece passaria no teste de cima e travaria a
operacao inteira — nenhum clipe novo seria agendado nunca.

⚠️ E O CLIPE VELHO, SEM SHA NENHUM, tambem tem de passar: o manifesto antigo
nao tem o campo, e essas entradas continuam defendidas pelas guardas de texto.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import registro_clipes as reg  # noqa: E402

tmp = Path(tempfile.mkdtemp())
reg.ARQUIVO = tmp / "r.json"
falhas = []

v = tmp / "short_9x16.mp4"
v.write_bytes(b"o ensopado suculento" * 400)
sha = reg.sha_do_arquivo(v)
reg.registrar(sha, arquivo="short_9x16.mp4", titulo="Ensopado Suculento",
              canal="cozinha.internacional")
reg.marcar_postado(sha, origem="buffer", quando="2026-08-29T23:00:00Z")


def cabe(entrada: dict) -> bool:
    """A guarda como ela esta' no agendar_buffer."""
    s = entrada.get("sha")
    return not (s and reg.ja_postado(s))


# 1. POSITIVO — seis titulos distintos, mesmo arquivo: todos recusados
titulos = ["Rabanada Crocante", "Muffin Salgado", "Torrada com Ovo",
           "Granola Vietnamita", "Salada de Macarrao", "Huevos Rancheros"]
passaram = [t for t in titulos if cabe({"sha": sha, "titulo": t})]
if passaram:
    falhas.append(f"{len(passaram)} dos 6 titulos do MESMO video passaram: {passaram}")

# 2. NEGATIVO — arquivo novo, nunca postado: tem de passar
novo = tmp / "novo.mp4"
novo.write_bytes(b"receita nova de verdade" * 400)
sha2 = reg.sha_do_arquivo(novo)
if not cabe({"sha": sha2, "titulo": "Cookie Gigante da Levain"}):
    falhas.append("clipe NOVO foi recusado — a guarda recusa tudo")

# 3. NEGATIVO — entrada velha sem sha: tem de passar
if not cabe({"titulo": "Clipe antigo, manifesto sem sha"}):
    falhas.append("entrada sem sha foi recusada — quebraria o manifesto antigo")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_guarda_por_sha: 6 titulos do mesmo video recusados; "
      "clipe novo e entrada sem sha passam")
