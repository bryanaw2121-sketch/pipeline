# -*- coding: utf-8 -*-
"""Teste da dedup por prefixo, contra os 101 posts REAIS do @modofuturo.

POR QUE COM DADO REAL

O defeito nao aparece em exemplo inventado: ele depende de como as legendas
foram de fato escritas. 88 dos 101 posts tem titulo e descricao na MESMA
linha, e e' isso que quebra a chave. Um teste com titulos limpos passaria
com o codigo defeituoso.

Os 101 textos estao em `dados/posts_modofuturo.json`, puxados do Buffer em
30/08/2026. Sao legendas publicas de video publicado — nao ha' segredo neles,
e assim o teste roda sem gastar cota da API.

OS CASOS NEGATIVOS

  falso positivo    a regra nao pode casar clipes DIFERENTES. Medido: contra
                    os 101 reais ela casa 4 pares, e os 4 sao duplicatas de
                    verdade. Se algum dia casar um quinto, este teste acusa.

  clipe novo passa  um titulo que nunca foi publicado tem que ser aceito. Uma
                    dedup que recusa tudo "nunca duplica" e tambem nunca
                    publica.

  chave curta       titulo curto exige igualdade, nao prefixo. Senao "bolo"
                    seria prefixo de metade do canal.

Roda com: python teste/teste_dedup.py
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from engine import dedup

falhas = 0


def checar(cond, recado):
    global falhas
    if cond:
        print(f"  ok  {recado}")
    else:
        print(f"  FALHOU  {recado}")
        falhas += 1


def chave(t):
    """A mesma normalizacao do agendar_buffer do @modofuturo: PRIMEIRA linha,
    sem hashtag, sem acento, so' alfanumerico, cortada em 70."""
    t = (t or "").split("\n")[0].split("#")[0]
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:70]


posts = json.loads(
    (RAIZ / "teste" / "dados" / "posts_modofuturo.json").read_text(encoding="utf-8"))
chaves = [chave(p["text"]) for p in posts]

print(f"--- {len(posts)} posts reais do @modofuturo ---")

# O tamanho do problema, refeito a cada rodada em vez de anotado num comentario.
uma_linha = sum(1 for p in posts if len((p["text"] or "").split("\n")) == 1)
checar(uma_linha > len(posts) * 0.5,
       f"{uma_linha} de {len(posts)} tem titulo e descricao na mesma linha")

# ------------------------------------------------------- O CASO QUE ACONTECEU
print("\n--- as duas duplicatas de 30/08 ---")
for alvo in ("A Lei de Moore REALMENTE Morreu? Nvidia, Intel e IBM Respondem",
             "O Segredo dos Chips do Futuro: A Inovacao CFET Revelada"):
    k = chave(alvo)
    publicadas = [chave(p["text"]) for p in posts if p["status"] == "sent"]
    checar(dedup.ja_visto(k, publicadas), f"pega a duplicata: {alvo[:44]}")
    # E o negativo do mesmo caso: a comparacao ANTIGA (igualdade) nao pegava.
    checar(k not in publicadas,
           f"  (e a igualdade exata NAO pegava — era o defeito)")

# --------------------------------------------------------- FALSO POSITIVO
print("\n--- falso positivo contra os 101 reais ---")
pares = []
for i, a in enumerate(chaves):
    for j in range(i + 1, len(chaves)):
        b = chaves[j]
        if dedup.ja_visto(a, [b]):
            pares.append((posts[i], posts[j]))
suspeitos = [(x, y) for x, y in pares
             if chave(x["text"])[:25] != chave(y["text"])[:25]]
for x, y in pares:
    t = (x["text"] or "").split("\n")[0][:46].encode("ascii", "replace").decode()
    print(f"      casou: {x['dueAt'][:10]} + {y['dueAt'][:10]}  {t}")
checar(len(suspeitos) == 0,
       f"{len(pares)} par(es) casaram, {len(suspeitos)} com titulo diferente")
checar(len(pares) == 4,
       "sao exatamente os 4 pares conhecidos (se mudar, alguem precisa olhar)")

# ------------------------------------------------------------- CLIPE NOVO
print("\n--- clipe novo tem que PASSAR ---")
novos = ["Como a Samsung perdeu a lideranca dos chips de memoria",
         "O reator nuclear que cabe num caminhao",
         "Por que o vidro das lentes custa mais que ouro"]
for t in novos:
    checar(not dedup.ja_visto(chave(t), chaves), f"passa: {t[:46]}")

# ------------------------------------------------------------ CHAVE CURTA
print("\n--- chave curta exige igualdade, nao prefixo ---")
checar(not dedup.ja_visto("bolo", ["bolodechocolatecomcoberturademorango"]),
       "'bolo' NAO casa com 'bolo de chocolate...' (curta demais)")
checar(dedup.ja_visto("bolo", ["bolo"]), "'bolo' casa com 'bolo' (igual)")
checar(not dedup.ja_visto("", chaves), "chave vazia nunca casa")

if falhas:
    print(chr(10) + f"{falhas} FALHA(S)")
    sys.exit(1)
print(chr(10) + "tudo verde")
