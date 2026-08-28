# -*- coding: utf-8 -*-
"""Manda um clipe pronto pros RASCUNHOS do Buffer, pro Bryan revisar no celular.

POR QUE EXISTE
Pedido do Bryan em 28/08/2026: "quando for mandar a previa me manda nos
rascunhos do buffer". Arquivo de 66 MB nao passa pelo chat, e ele revisa no
telefone — o rascunho do Buffer poe o video na mao dele, no app que ele ja' usa.

COMO FUNCIONA
O Buffer nao aceita upload de arquivo pela API: pede URL publica. Entao o clipe
sobe como asset de Release (mesmo caminho da publicacao normal) e o post e'
criado com `saveToDraft: true` — campo do CreatePostInput, achado por
introspeccao. `ShareMode` NAO tem opcao de rascunho; e' o saveToDraft que
resolve.

RASCUNHO NAO PUBLICA. Fica parado ate' o Bryan mandar. E o rotulo de IA vai
marcado desde o rascunho, pra ele nao ter que lembrar depois.

USO
    python previa_buffer.py "caminho/do/short_9x16.mp4" --titulo "..."
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import agendar_buffer as ab

RAIZ = Path(__file__).resolve().parent
TAG = "previas"


def _gh(url: str, dados=None, metodo=None, tipo="application/json"):
    tok = ab._token_github()
    r = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
        "User-Agent": "previa", "Content-Type": tipo})
    return json.load(urllib.request.urlopen(r))


def subir_asset(arquivo: Path) -> str:
    """Sobe o clipe numa Release e devolve a URL publica."""
    repo = ab.REPO
    try:
        rel = _gh(f"https://api.github.com/repos/{repo}/releases/tags/{TAG}")
    except Exception:
        rel = _gh(f"https://api.github.com/repos/{repo}/releases",
                  json.dumps({"tag_name": TAG, "name": "previas",
                              "body": "Clipes em revisao."}).encode())
    # nome repetido faz o GitHub recusar o upload: apaga o antigo antes
    for a in rel.get("assets", []):
        if a["name"] == arquivo.name:
            _gh(f"https://api.github.com/repos/{repo}/releases/assets/{a['id']}",
                metodo="DELETE")
    up = rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(arquivo.name)
    a = _gh(up, arquivo.read_bytes(), tipo="application/octet-stream")
    return a["browser_download_url"]


def criar_rascunho(url: str, texto: str, titulo: str) -> dict:
    org, canal, _ = ab.contexto_buffer(ab._token_buffer())
    m = """mutation($input: CreatePostInput!) {
      createPost(input: $input) { __typename
        ... on PostActionSuccess { post { id status } }
        ... on RestProxyError { code message }
        ... on InvalidInputError { message }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message } } }"""
    d = ab.consultar(ab._token_buffer(), m, {"input": {
        "channelId": canal,
        "text": texto,
        "mode": "addToQueue",
        "schedulingType": "automatic",
        "saveToDraft": True,          # <- o que mantem parado como rascunho
        "assets": [{"video": {"url": url}}],
        "metadata": {"tiktok": {"isAiGenerated": True, "title": titulo[:90]}},
    }})["createPost"]
    if d["__typename"] != "PostActionSuccess":
        raise RuntimeError(f"{d['__typename']}: {d.get('message','')[:200]}")
    return d["post"]


def main() -> None:
    p = argparse.ArgumentParser(description="Clipe -> rascunho do Buffer")
    p.add_argument("arquivo")
    p.add_argument("--titulo", default="")
    p.add_argument("--texto", default="")
    a = p.parse_args()
    arq = Path(a.arquivo)
    if not arq.exists():
        sys.exit(f"nao encontrei: {arq}")
    titulo = a.titulo or arq.parent.name
    print(f"subindo {arq.name} ({arq.stat().st_size/1e6:.1f} MB)...")
    url = subir_asset(arq)
    print("  url:", url)
    post = criar_rascunho(url, a.texto or titulo, titulo)
    print(f"rascunho criado: id={post['id']} status={post['status']}")


if __name__ == "__main__":
    main()
