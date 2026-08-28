# -*- coding: utf-8 -*-
"""Puxa as métricas reais dos posts pelo Buffer e cruza com o manifesto.

POR QUE EXISTE
Medição é a lacuna que os handoffs chamam de "a maior do projeto" desde julho.
A API do TikTok foi RECUSADA pra este uso (ver `handoff_22-08-2026.md`), então
a rota oficial está fechada. Mas o Buffer, que publica por nós, devolve as
métricas de cada post **de graça, pela API**:

    Reactions · Comments · Eng. Rate · Views · Shares · Reach

Isso fecha o laço: o `manifesto.json` guarda nota do Gemini, vídeo-fonte e
posição do corte no original; o Buffer guarda o desempenho. Cruzando os dois dá
pra responder o que antes era palpite — que fonte rende, se a nota prediz
audiência, se o rótulo de IA muda alguma coisa.

⚠️ DUAS ARMADILHAS, as duas medidas em 26/08/2026:

1. **`metricsUpdatedAt` importa mais que o valor.** O Buffer atualiza em lotes;
   um post recém-publicado aparece com 0 views porque o número é de ANTES dele
   ir ao ar. Este script mostra a idade da medição e marca como `?` o que ainda
   não foi atualizado depois da publicação.

2. **Vídeo apagado do TikTok fica com 0 pra sempre.** Não é desempenho ruim, é
   ausência de vídeo. Os 4 posts de 25/08 que o Bryan apagou aparecem assim.

Uso:
    python medir_desempenho.py                 # tabela por post
    python medir_desempenho.py --por-fonte     # agrega por vídeo-fonte
    python medir_desempenho.py --csv saida.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

import requests

import agendar_buffer as ab
from engine import buffer_cota as cota

ORG_PADRAO = "6a90dddb9bb05f07b058e9bc"
FUSO_SP = datetime.timedelta(hours=3)   # America/Sao_Paulo = UTC-3


def _sp(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")) - FUSO_SP


def puxar(token: str, org: str, canal: str | None = None) -> list[dict]:
    """Posts publicados, com métricas. Uma requisição por página."""
    filtro = {"status": ["sent"]}
    if canal:
        filtro["channelIds"] = [canal]
    saida, cursor = [], None
    while True:
        d = ab.consultar(token, """
          query($i: PostsInput!, $a: String){ posts(input:$i, after:$a){
            pageInfo { hasNextPage endCursor }
            edges { node { id text sentAt metricsUpdatedAt
                           metrics { name value } } } } }""",
          {"i": {"organizationId": org, "filter": filtro}, "a": cursor})["posts"]
        saida += [e["node"] for e in d["edges"] if e["node"].get("sentAt")]
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]
    return saida


def _valores(post: dict) -> dict:
    return {m["name"]: m["value"] for m in (post.get("metrics") or [])}


def _medicao_confiavel(post: dict) -> bool:
    """A métrica foi atualizada DEPOIS da publicação?

    Se não foi, o valor é de antes do vídeo existir — e 0 ali não significa
    nada. Foi assim que quase li dois posts de hoje como fracasso.
    """
    at, sent = post.get("metricsUpdatedAt"), post.get("sentAt")
    if not at or not sent:
        return False
    return at > sent


def juntar_com_manifesto(posts: list[dict], man: dict) -> list[dict]:
    porchave = {ab._chave_texto(v.get("legenda") or v.get("titulo")): v
                for v in man.values()}
    linhas = []
    for p in posts:
        c = porchave.get(ab._chave_texto(p["text"])) or {}
        v = _valores(p)
        linhas.append({
            "quando": _sp(p["sentAt"]).strftime("%d/%m %H:%M"),
            "titulo": (c.get("titulo") or p["text"].split("#")[0]).strip()[:52],
            "nota": c.get("nota"),
            "fonte": (c.get("fonte") or "?")[:44],
            "inicio_s": c.get("inicio_s"),
            "views": v.get("Views", 0),
            "reacoes": v.get("Reactions", 0),
            "comentarios": v.get("Comments", 0),
            "shares": v.get("Shares", 0),
            "alcance": v.get("Reach", 0),
            "confiavel": _medicao_confiavel(p),
        })
    linhas.sort(key=lambda x: x["quando"], reverse=True)
    return linhas


def main() -> None:
    p = argparse.ArgumentParser(description="Mede o desempenho real dos posts")
    p.add_argument("--org", default=ORG_PADRAO)
    p.add_argument("--por-fonte", action="store_true",
                   help="agrega por vídeo-fonte em vez de listar post a post")
    p.add_argument("--csv", help="grava a tabela neste arquivo")
    a = p.parse_args()

    token = ab._token_buffer()
    posts = puxar(token, a.org)
    man = ab.manifesto(ab._token_github())
    linhas = juntar_com_manifesto(posts, man)

    medidos = [l for l in linhas if l["confiavel"]]
    print(f"{len(linhas)} post(s) publicado(s); {len(medidos)} com métrica "
          f"atualizada depois da publicação\n")

    if a.por_fonte:
        por = {}
        for l in medidos:
            g = por.setdefault(l["fonte"], {"n": 0, "views": 0, "reac": 0, "com": 0})
            g["n"] += 1
            g["views"] += l["views"]
            g["reac"] += l["reacoes"]
            g["com"] += l["comentarios"]
        print(f"{'vídeo-fonte':46s} {'n':>3s} {'views':>7s} {'média':>7s} {'reações':>8s}")
        for fonte, g in sorted(por.items(), key=lambda kv: -kv[1]["views"] / max(kv[1]["n"], 1)):
            print(f"{fonte:46s} {g['n']:3d} {g['views']:7.0f} "
                  f"{g['views']/g['n']:7.0f} {g['reac']:8.0f}")
    else:
        print(f"{'quando':13s} {'nota':>4s} {'views':>6s} {'reac':>5s} {'com':>4s} "
              f"{'shr':>4s}  titulo")
        for l in linhas:
            marca = " " if l["confiavel"] else "?"
            nota = f"{l['nota']:.0f}" if l["nota"] is not None else "  -"
            print(f"{l['quando']:13s} {nota:>4s} {l['views']:6.0f}{marca}"
                  f"{l['reacoes']:5.0f} {l['comentarios']:4.0f} {l['shares']:4.0f}  "
                  f"{l['titulo']}")
        print("\n? = métrica ainda não atualizada depois da publicação; "
              "0 aí não significa nada.")

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)
        print(f"\ntabela gravada em {a.csv}")
    print("\n" + cota.resumo())


if __name__ == "__main__":
    main()
