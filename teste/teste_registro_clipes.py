# -*- coding: utf-8 -*-
"""O registro tem de pegar o estrago REAL da cozinha, nao um caso inventado.

⚠️ O CASO E' O MEDIDO, nao um exemplo bonito: em 31/08/2026 SEIS posts da
fila do @cozinha.internacional apontavam pro MESMO arquivo com seis titulos
diferentes. O teste reproduz exatamente isso — um conteudo, varios nomes — e
exige que o registro veja UM clipe.

⚠️ E TEM CASO NEGATIVO: dois arquivos DIFERENTES com titulos parecidos tem de
continuar sendo dois. Um registro que responde "ja' postado" pra tudo passaria
no caso de cima e travaria a operacao inteira.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import registro_clipes as reg  # noqa: E402

tmp = Path(tempfile.mkdtemp())
reg.ARQUIVO = tmp / "registro.json"
falhas = []

# um unico conteudo, gravado com seis nomes diferentes (o estrago real)
video = tmp / "short_9x16.mp4"
video.write_bytes(b"conteudo do ensopado suculento" * 500)
sha = reg.sha_do_arquivo(video)

nomes = ["01_nota94_Rabanada Crocante de Canela e Brioche",
         "01_nota95_Muffin Salgado de Salsicha e Queijo",
         "02_nota91_Torrada com Ovo Cremoso de 7 Minutos",
         "03_nota88_Granola Caseira de Cafe Vietnamita",
         "03_nota90_Salada Cremosa de Macarrao com Atum",
         "04_nota86_Huevos Rancheros Rapidos de 10 Minutos"]
for n in nomes:
    reg.registrar(sha, arquivo=n + ".mp4", titulo=n, canal="cozinha.internacional")

import json  # noqa: E402
d = json.loads(reg.ARQUIVO.read_text(encoding="utf-8"))
if len(d["clipes"]) != 1:
    falhas.append(f"seis nomes do MESMO video viraram {len(d['clipes'])} clipes")
if len(d["clipes"][sha].get("outros_nomes", [])) != 5:
    falhas.append("os apelidos nao ficaram registrados — o rastro some")

# ---- postar por fora do Buffer conta -------------------------------------
if reg.ja_postado(sha):
    falhas.append("clipe recem-saido ja' aparece como postado")
reg.marcar_postado(sha, origem="mao", detalhe="estreia postada no celular")
if not reg.ja_postado(sha):
    falhas.append("postagem NA MAO nao contou — e' o furo do Buffer")

# ---- NEGATIVO: outro conteudo continua sendo outro clipe -----------------
outro = tmp / "outro.mp4"
outro.write_bytes(b"outro conteudo, receita diferente" * 500)
sha2 = reg.sha_do_arquivo(outro)
reg.registrar(sha2, arquivo="03_nota90_Salada Cremosa de Macarrao com Atum.mp4",
              titulo="Salada Cremosa de Macarrao com Atum", canal="cozinha.internacional")
if sha2 == sha:
    falhas.append("dois conteudos diferentes deram o mesmo sha")
if reg.ja_postado(sha2):
    falhas.append("clipe NOVO marcado como postado so' por ter titulo parecido")

# ---- o titulo acha o clipe, sem o prefixo de arquivo ---------------------
if reg.sha_por_titulo("01_nota94_Rabanada Crocante de Canela e Brioche") != sha:
    falhas.append("o prefixo NN_notaXX_ atrapalhou o casamento por titulo")

# ---- nao_postados lista, e nao apaga ------------------------------------
pend = reg.nao_postados()
if [p["sha"] for p in pend] != [sha2]:
    falhas.append(f"nao_postados errou: {[p['sha'][:8] for p in pend]}")
if not outro.exists():
    falhas.append("o modulo APAGOU arquivo — ele so' pode listar")

if falhas:
    for f in falhas:
        print("  [x]", f)
    sys.exit(1)
print("[ok] teste_registro_clipes: 6 nomes = 1 clipe, postagem na mao conta, "
      "conteudo diferente segue diferente")

# ---- catalogo historico: anotado, mas NAO protegido ---------------------
# ⚠️ O caso negativo aqui e' o que impede a confianca falsa: entrada de
# catalogo nao pode se passar por entrada com hash. Se `tem_hash` respondesse
# True pra ela, o relato diria "protegido" onde nao ha' protecao — e a
# protecao que falta e' exatamente contra o estrago que originou o modulo.
ch = reg.registrar_historico(titulo="Ensopado de Carne Suculenta com Tomate",
                             canal="cozinha.internacional",
                             postado_em="2026-08-29T23:00:00Z")
if reg.tem_hash(ch):
    print("  [x] entrada de catalogo se passou por entrada com hash"); sys.exit(1)
if not reg.ja_postado(ch):
    print("  [x] catalogo com data de postagem nao conta como postado"); sys.exit(1)
if reg.tem_hash(sha) is not True:
    print("  [x] entrada com sha de verdade foi tratada como catalogo"); sys.exit(1)
r = reg.resumo()
if r["com_hash"] != 2 or r["so_catalogo"] != 1:
    print(f"  [x] resumo errado: {r}"); sys.exit(1)
# rodar de novo nao duplica
reg.registrar_historico(titulo="Ensopado de Carne Suculenta com Tomate",
                        canal="cozinha.internacional")
if reg.resumo()["total"] != 3:
    print("  [x] catalogar duas vezes duplicou a entrada"); sys.exit(1)
print("[ok] catalogo historico: anotado, contado, e NAO se passa por protegido")

# ---- o prefixo vem em DUAS formas --------------------------------------
# ⚠️ O titulo catalogado da RELEASE traz data + indice + nota; o texto do
# post no Buffer traz o titulo limpo. Ate' 31/08/2026 so' a forma da pasta
# era removida, e os dois nunca casavam — a marcacao manual do Cookie da
# Levain nao achou o clipe.
pares = [("2026 08 31 03 nota84 Provando o Famoso Cookie da Levain Bakery",
          "Provando o Famoso Cookie da Levain Bakery"),
         ("01_nota92_Como fazer base e contorno", "Como fazer base e contorno"),
         ("2026-08-31_04_nota81_Segredo para iluminar", "Segredo para iluminar")]
for bruto, limpo in pares:
    if reg.chave_titulo(bruto) != reg.chave_titulo(limpo):
        print(f"  [x] nao casou: {bruto[:40]!r} x {limpo[:30]!r}"); sys.exit(1)

# ⚠️ NEGATIVO: numero que faz PARTE do titulo nao pode ser comido. Comer
# qualquer digito inicial faria "10 Ideias de Marmitas" deixar de casar
# consigo mesmo — e ai' um clipe ja' postado voltaria a parecer novo.
if reg.chave_titulo("10 Ideias de Marmitas Fit") != "10ideiasdemarmitasfit":
    print("  [x] o numero legitimo do titulo foi comido"); sys.exit(1)
if reg.chave_titulo("Cookie Gigante") == reg.chave_titulo("Cookie Pequeno"):
    print("  [x] titulos diferentes viraram a mesma chave"); sys.exit(1)
print("[ok] chave_titulo: release e Buffer casam, numero legitimo preservado")
