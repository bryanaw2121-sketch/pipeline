# -*- coding: utf-8 -*-
"""Baixa o video-fonte AQUI e sobe pra nuvem cortar.

POR QUE EXISTE
O YouTube recusa os IPs do GitHub Actions — "Sign in to confirm you're not a
bot". Testado em 28/08/2026 com as tres defesas do outro canal ligadas
(yt-dlp-invidious, provedor de PO token bgutil e o passo de cookies): recusou
do mesmo jeito. Da maquina do Bryan, com IP residencial, baixa sem reclamar.

Entao a divisao e': **download aqui, processamento na nuvem**. Baixar e' rede,
nao CPU — nao fere a regra de nao rodar peso nesta maquina.

O bruto vai pra um repo PRIVADO: e' material-fonte de terceiro, nao pode ficar
publico. O runner baixa com o token.

USO
    python enviar_bruto.py "https://youtu.be/XXXX"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import agendar_buffer as ab

REPO_BRUTOS = "bryanaw2121-sketch/brutos"
TAG = "brutos"
TRABALHO = Path(__file__).resolve().parent / "trabalho" / "bruto"


def _gh(url, dados=None, metodo=None, tipo="application/json"):
    r = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": "Bearer " + ab._token_github(),
        "Accept": "application/vnd.github+json",
        "User-Agent": "bruto", "Content-Type": tipo})
    resp = urllib.request.urlopen(r)
    b = resp.read()
    return json.loads(b) if b else {}


def baixar(url: str) -> Path:
    TRABALHO.mkdir(parents=True, exist_ok=True)
    destino = TRABALHO / "fonte.mp4"
    if destino.exists():
        destino.unlink()
    # Mesmo formato que o main.py pede: 480p e' suficiente pro 9:16 e mantem
    # o arquivo pequeno o bastante pra subir rapido.
    cmd = ["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]/b",
           "--merge-output-format", "mp4", "-o", str(destino), url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists():
        sys.exit(f"yt-dlp falhou:\n{(r.stderr or '')[-800:]}")
    return destino


def subir(arquivo: Path, nome: str) -> str:
    try:
        rel = _gh(f"https://api.github.com/repos/{REPO_BRUTOS}/releases/tags/{TAG}")
    except Exception:
        rel = _gh(f"https://api.github.com/repos/{REPO_BRUTOS}/releases",
                  json.dumps({"tag_name": TAG, "name": "brutos"}).encode())
    for a in rel.get("assets", []):
        if a["name"] == nome:
            _gh(f"https://api.github.com/repos/{REPO_BRUTOS}/releases/assets/{a['id']}",
                metodo="DELETE")
    up = rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(nome)
    a = _gh(up, arquivo.read_bytes(), tipo="application/octet-stream")
    return a["name"]


def main() -> None:
    p = argparse.ArgumentParser(description="Baixa o bruto aqui e sobe pra nuvem")
    p.add_argument("url")
    p.add_argument("--nome", default="", help="nome do asset (padrao: id do video)")
    a = p.parse_args()
    print("baixando (IP daqui, que o YouTube aceita)...")
    arq = baixar(a.url)
    mb = arq.stat().st_size / 1e6
    nome = a.nome or (a.url.rstrip("/").split("/")[-1].split("?")[0] + ".mp4")
    print(f"  {mb:.1f} MB -> subindo como {nome}")
    subir(arq, nome)
    arq.unlink()
    print(f"pronto. No Actions, rode 'Cortar de bruto' com bruto={nome}")


if __name__ == "__main__":
    main()
