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
import re
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
    resp = urllib.request.urlopen(r)
    corpo = resp.read()
    # DELETE devolve 204 com corpo VAZIO. Ler JSON de vazio estoura
    # JSONDecodeError e derruba o passo inteiro — foi o que quebrou o run de
    # 28/08 DEPOIS de 99 minutos de corte, com os 5 clipes ja' prontos.
    return json.loads(corpo) if corpo else {}


def subir_asset(arquivo: Path) -> str:
    """Sobe o clipe numa Release e devolve a URL publica."""
    repo = ab.REPO
    try:
        rel = _gh(f"https://api.github.com/repos/{repo}/releases/tags/{TAG}")
    except Exception:
        rel = _gh(f"https://api.github.com/repos/{repo}/releases",
                  json.dumps({"tag_name": TAG, "name": "previas",
                              "body": "Clipes em revisao."}).encode())
    # ⚠️ NOME UNICO POR CLIPE. Ate' 31/08/2026 o asset subia com o nome do
    # arquivo — e todo clipe do motor se chama `short_9x16.mp4`. Como nome
    # repetido faz o GitHub recusar o upload, o codigo APAGAVA o anterior e
    # gravava por cima.
    #
    # Consequencia medida no run #16: os TRES rascunhos da manteiga apontavam
    # para a mesma URL (`previas/short_9x16.mp4`), que continha so' o ultimo
    # clipe. O Bryan achou que era bug do app do Buffer — era a previa se
    # sobrescrevendo. E se aqueles rascunhos fossem promovidos a post, os tres
    # sairiam com o MESMO video: duplicata e' a causa medida dos colapsos de
    # alcance de 02/08 e 25/08.
    #
    # O nome agora carrega o conteudo: hash curto do arquivo + o nome da pasta
    # do clipe (que ja' e' unica por corte). Dois clipes iguais reaproveitam o
    # mesmo asset de proposito — e' o mesmo video, nao ha' o que sobrescrever.
    import hashlib
    dados = arquivo.read_bytes()
    curto = hashlib.sha256(dados).hexdigest()[:10]
    rotulo = re.sub(r"[^A-Za-z0-9_.-]+", "-", arquivo.parent.name)[:48] or "clipe"
    nome = f"{rotulo}_{curto}{arquivo.suffix}"

    ja = [a for a in rel.get("assets", []) if a["name"] == nome]
    if ja:
        # mesmo conteudo ja' esta' la': nao sobe de novo, so' reaproveita
        return ja[0]["browser_download_url"]

    up = rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(nome)
    a = _gh(up, dados, tipo="application/octet-stream")
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
