# -*- coding: utf-8 -*-
"""A cozinha publica de verdade, nao so' manda pra rascunho.

POR QUE EXISTE

Ate' 31/08/2026 o @cozinha.internacional era o unico dos cinco canais SEM
caminho de publicacao. Os quatro do poisonb9/Modo-Futuro tem
`publicar_release.py` + `agendar_buffer.py` no workflow; aqui os quatro
workflows so' chamavam `previa_buffer.py`, que manda pro RASCUNHO.

Medido antes do conserto:

    canal                   workflow                          publicacao
    @modofuturo             Modo-Futuro/cortar_de_bruto.yml   release+agendar
    @semanestesia.pod       Modo-Futuro/cortar_de_bruto.yml   release+agendar
    @atefalhar              Modo-Futuro/cortar_de_bruto.yml   release+agendar
    @truque.importado       Modo-Futuro/cortar_de_bruto.yml   release+agendar
    @cozinha.internacional  pipeline/cortar_*.yml             SO' PREVIA  <<<

⚠️ E o rascunho nem servia pra revisar. O `previa_buffer` subia todo clipe com
o nome do arquivo (`short_9x16.mp4`, igual pra todos) e apagava o anterior:
os TRES rascunhos do run #16 apontavam pro MESMO video. Promove-los teria
publicado o mesmo clipe tres vezes, e duplicata e' a causa medida dos colapsos
de alcance de 02/08 e 25/08.

⚠️ O TOKEN E' O PONTO DELICADO. A release vive no repo `media-assets`, e o
`secrets.GITHUB_TOKEN` do runner so' escreve NO PROPRIO repositorio. Tem de
ser o `GH_PAT`. Um GITHUB_TOKEN comum aqui falharia — e com `continue-on-error`
falharia EM SILENCIO, deixando o clipe sem URL publica e a fila vazia sem
ninguem entender por que.

Roda com: python teste/teste_caminho_publicacao.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import yaml  # noqa: E402

falhas = []


def checar(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


WF = RAIZ / ".github" / "workflows" / "cortar_do_drive.yml"
d = yaml.safe_load(WF.read_text(encoding="utf-8"))
passos = d["jobs"][list(d["jobs"])[0]]["steps"]
nomes = [(p.get("name") or "") for p in passos]
por_nome = {(p.get("name") or ""): p for p in passos}

print(__doc__.splitlines()[0])

# --- 1. os dois passos existem, e nesta ordem ----------------------------
print("\n[1] o caminho de publicacao existe no workflow")
rel = [n for n in nomes if "Release" in n]
buf = [n for n in nomes if "Enfileirar no Buffer" in n]
checar(len(rel) == 1, f"ha um passo de Release ({len(rel)})")
checar(len(buf) == 1, f"ha um passo de Enfileirar ({len(buf)})")
if rel and buf:
    checar(nomes.index(rel[0]) < nomes.index(buf[0]),
           "a Release vem ANTES do Buffer (o Buffer le' o manifesto dela)")
    drive = [n for n in nomes if "Drive" in n and "Subir" in n]
    if drive:
        checar(nomes.index(drive[0]) < nomes.index(rel[0]),
               "o Drive vem antes dos dois")

# --- 2. o TOKEN certo, que e' onde isto falharia calado ------------------
print("\n[2] a Release usa GH_PAT, nao o GITHUB_TOKEN do runner")
for nome in rel + buf:
    env = por_nome[nome].get("env") or {}
    tok = str(env.get("GITHUB_TOKEN", ""))
    checar("GH_PAT" in tok, f"{nome[:34]}: GITHUB_TOKEN vem do GH_PAT")
    checar("media-assets" in str(env.get("GITHUB_REPO", "")),
           f"{nome[:34]}: aponta pro repo media-assets")

# --- 3. a guarda de canal, nos dois -------------------------------------
print("\n[3] a guarda de canal esta' nos dois passos")
for nome in rel + buf:
    env = por_nome[nome].get("env") or {}
    checar(str(env.get("CANAL_ESPERADO", "")) == "cozinha.importada",
           f"{nome[:34]}: CANAL_ESPERADO = cozinha.importada")

# --- 4. falha do Buffer nao pode reprovar o corte -----------------------
print("\n[4] erro de publicacao nao derruba o clipe ja' pronto")
for nome in rel + buf:
    checar(por_nome[nome].get("continue-on-error") is True,
           f"{nome[:34]}: continue-on-error")

# --- 5. o CASO NEGATIVO: os scripts existem mesmo -----------------------
print("\n[5] os scripts que o workflow chama existem no repo")
for arq in ("publicar_release.py", "agendar_buffer.py"):
    checar((RAIZ / arq).exists(), f"{arq} esta' no repo")
corpo = " ".join(str(por_nome[n].get("run", "")) for n in rel + buf)
checar("publicar_release.py" in corpo, "o passo chama publicar_release.py")
checar("agendar_buffer.py" in corpo, "o passo chama agendar_buffer.py")

# --- 6. o rascunho saiu do caminho principal ----------------------------
print("\n[6] o rascunho nao esta' mais no fluxo deste workflow")
todo = WF.read_text(encoding="utf-8")
checar("previa_buffer.py" not in todo,
       "cortar_do_drive.yml nao chama mais previa_buffer")
checar("rascunhos do Buffer" not in todo,
       "o aviso do Telegram nao promete rascunho")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("tudo verde")
