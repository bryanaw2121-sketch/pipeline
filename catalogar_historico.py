# -*- coding: utf-8 -*-
"""Cataloga o que ja' existe: posts do Buffer e assets das releases.

Decisao do Bryan em 31/08/2026: "vamos do de agora pra frente, mas vamos
escrever tudo em uma lista ainda assim. Vamos ter isso catalogado."

⚠️ O QUE ENTRA AQUI NAO TEM HASH. Nao baixa os ~4 GB de assets pra calcular
sha; entra como CATALOGO, com a chave derivada do titulo e o campo
`sem_hash`. Isso e' registro, nao protecao: titulo e' a chave fraca que
deixou seis posts da cozinha apontarem pro mesmo arquivo. A protecao de
verdade comeca nos clipes novos, que passam pelo `publicar_release`.

Rodar uma vez. Rodar de novo nao duplica (a chave e' o titulo normalizado).
"""
from __future__ import annotations

import json
import os
import urllib.request

import requests

from conferir_postados import CANAIS, publicados
from engine import registro_clipes as reg

# ⚠️ Os mp4 deste motor moram no media-assets, nao no proprio repo.
REPO = os.environ.get("REPO_ASSETS") or "bryanaw2121-sketch/media-assets"


def do_buffer() -> list[str]:
    linhas = []
    for nome, (org, ch, env) in CANAIS.items():
        token = (os.environ.get(env) or "").strip()
        if not token:
            linhas.append(f"  {nome}: sem token — NAO catalogado")
            continue
        try:
            posts = publicados(token, org, ch)
        except Exception as e:
            linhas.append(f"  {nome}: Buffer recusou ({str(e)[:50]})")
            continue
        for p in posts:
            titulo = p["text"].splitlines()[0]
            # ⚠️ Se o clipe JA' tem entrada com hash de verdade, marca nela e
            # nao cria catalogo paralelo — senao o mesmo video ficaria com
            # duas entradas, uma protegida e outra nao.
            sha = reg.sha_por_titulo(titulo)
            if sha and reg.tem_hash(sha):
                reg.marcar_postado(sha, origem="buffer", quando=p["dueAt"],
                                   canal=nome, detalhe=titulo[:70])
                continue
            reg.registrar_historico(titulo=titulo, canal=nome,
                                    postado_em=p["dueAt"], origem="buffer")
        linhas.append(f"  {nome}: {len(posts)} post(s) publicados catalogados")
    return linhas


def das_releases() -> list[str]:
    """Os mp4 que estao nas releases mas nunca viraram post."""
    tok = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not tok:
        return ["  releases: sem token do GitHub — NAO catalogadas"]
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases?per_page=10",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    if r.status_code != 200:
        return [f"  releases: HTTP {r.status_code}"]
    n = 0
    for rel in r.json():
        for a in rel.get("assets", []):
            if not a["name"].endswith(".mp4"):
                continue
            # o nome do asset vira titulo legivel; e' o que existe sem baixar
            titulo = (a["name"].removesuffix(".mp4")
                      .replace("_short_9x16", "").replace("-", " ").replace("_", " "))
            if reg.sha_por_titulo(titulo):
                continue
            reg.registrar_historico(titulo=titulo, canal="", arquivo=a["name"],
                                    url=a["browser_download_url"])
            n += 1
    return [f"  releases: {n} asset(s) sem post catalogados"]


def main() -> None:
    linhas = ["Catalogo do que ja' existia", ""]
    linhas += do_buffer()
    linhas += das_releases()
    r = reg.resumo()
    linhas += ["", f"registro: {r['total']} clipes "
                   f"({r['com_hash']} com hash, {r['so_catalogo']} so' catalogo)",
               f"          {r['postados']} postados, "
               f"{r['nunca_postados']} nunca postados"]
    # ⚠️ A distincao com_hash x so_catalogo tem de aparecer no relato: e' a
    # diferenca entre "protegido" e "apenas anotado".
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
