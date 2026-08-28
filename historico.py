# -*- coding: utf-8 -*-
"""Registro local do que ja' foi publicado + serie temporal de views.

POR QUE EXISTE

1. DEDUP SEM API. A protecao contra duplicata do `agendar_buffer.py` consulta o
   Buffer e para em 4 paginas pra poupar orcamento — ou seja, ela e' CEGA pro
   que e' antigo. Foi essa cegueira que republicou um clipe em 25/08 e derrubou
   o alcance do dia. Com este arquivo, a checagem passa a ser completa,
   instantanea e sem gastar requisicao nenhuma.

2. CRESCIMENTO DE VIEWS. Uma medicao isolada nao diz se um video esta subindo ou
   parado. Cada execucao grava um PONTO por post; com dois pontos da' pra ver a
   velocidade. Sem isso, a mesma pergunta e' respondida do zero toda semana.

⚠️ Um video com poucas horas de vida mostrando 0 NAO e' bloqueio — o TikTok
demora a atualizar. So' chame de 0 depois de uma noite inteira.

Uso:
    python historico.py                 # puxa do Buffer e grava um ponto novo
    python historico.py --crescimento   # so' le' o disco, nao toca na API
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import agendar_buffer as ab

RAIZ = Path(__file__).resolve().parent
PUBLICADOS = RAIZ / "estado" / "publicados.json"
SERIE = RAIZ / "estado" / "serie_views.jsonl"
ORG = "6a90dddb9bb05f07b058e9bc"
CANAL = "6a90de80ccaf649a672ebe15"
FUSO_SP = datetime.timedelta(hours=3)


def _ler_publicados() -> dict:
    if PUBLICADOS.exists():
        try:
            return json.loads(PUBLICADOS.read_text(encoding="utf-8"))
        except Exception:
            print(f"[!] {PUBLICADOS.name} ilegivel, tratando como vazio.")
    return {}


def ja_publicado(chave: str) -> bool:
    """Checagem completa e offline. Nao gasta requisicao."""
    return chave in _ler_publicados()


def puxar(token: str, teto_paginas: int = 8) -> list[dict]:
    saida, cursor, paginas = [], None, 0
    while paginas < teto_paginas:
        d = ab.consultar(token, """
          query($i: PostsInput!, $a: String){ posts(input:$i, after:$a){
            pageInfo { hasNextPage endCursor }
            edges { node { id text sentAt metricsUpdatedAt
                           metrics { name value } } } } }""",
          {"i": {"organizationId": ORG,
                 "filter": {"status": ["sent"], "channelIds": [CANAL]}},
           "a": cursor})["posts"]
        saida += [e["node"] for e in d["edges"] if e["node"].get("sentAt")]
        paginas += 1
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]
    return saida


def gravar(posts: list[dict]) -> tuple[int, int]:
    pub = _ler_publicados()
    novos = 0
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()[:19]
    linhas = []
    for p in posts:
        texto = p.get("text") or ""
        chave = ab._chave_texto(texto)
        if not chave:
            continue
        if chave not in pub:
            pub[chave] = {"titulo": texto.split("#")[0].strip()[:80],
                          "sentAt": p.get("sentAt")}
            novos += 1
        v = {m["name"]: m["value"] for m in (p.get("metrics") or [])}
        confiavel = bool(p.get("metricsUpdatedAt") and p.get("sentAt")
                         and p["metricsUpdatedAt"] > p["sentAt"])
        linhas.append(json.dumps({
            "quando": agora, "chave": chave, "sentAt": p.get("sentAt"),
            "views": v.get("Views", 0), "reacoes": v.get("Reactions", 0),
            "comentarios": v.get("Comments", 0), "shares": v.get("Shares", 0),
            "confiavel": confiavel}, ensure_ascii=False))
    PUBLICADOS.parent.mkdir(parents=True, exist_ok=True)
    PUBLICADOS.write_text(json.dumps(pub, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    with open(SERIE, "a", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")
    return novos, len(linhas)


def crescimento() -> None:
    if not SERIE.exists():
        print("Sem serie ainda. Rode `python historico.py` uma vez.")
        return
    pontos: dict[str, list[dict]] = {}
    for linha in SERIE.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        d = json.loads(linha)
        pontos.setdefault(d["chave"], []).append(d)

    instantes = sorted({d["quando"] for v in pontos.values() for d in v})
    print(f"{len(instantes)} medicao(oes) no disco: {', '.join(instantes)}\n")
    if len(instantes) < 2:
        print("So' ha um instante — o crescimento aparece na proxima rodada.")
        return

    ant, atu = instantes[-2], instantes[-1]
    print(f"{'titulo':50s} {'antes':>7s} {'agora':>7s} {'+/-':>7s}")
    pub = _ler_publicados()
    linhas = []
    for chave, v in pontos.items():
        a = next((x for x in v if x["quando"] == ant), None)
        b = next((x for x in v if x["quando"] == atu), None)
        if not a or not b:
            continue
        linhas.append((b["views"] - a["views"], a["views"], b["views"],
                       pub.get(chave, {}).get("titulo", chave)[:50]))
    for d, a, b, t in sorted(linhas, reverse=True):
        print(f"{t:50s} {a:7.0f} {b:7.0f} {d:+7.0f}")


def main() -> None:
    p = argparse.ArgumentParser(description="Registro local e serie de views")
    p.add_argument("--crescimento", action="store_true",
                   help="so' le' o disco; nao toca na API do Buffer")
    a = p.parse_args()
    if a.crescimento:
        crescimento()
        return
    posts = puxar(ab._token_buffer())
    novos, n = gravar(posts)
    print(f"{n} post(s) publicado(s) lidos; {novos} entraram novos no registro.")
    print(f"registro: {len(_ler_publicados())} textos ja' publicados (dedup offline)")
    crescimento()


if __name__ == "__main__":
    main()
