# -*- coding: utf-8 -*-
"""Publica os clipes numa Release do GitHub e devolve a URL pública de cada um.

POR QUE EXISTE
Nenhum agendador de rede social aceita upload de arquivo pela API — nem o
Buffer, nem o Zoho. Todos pedem uma **URL pública** do vídeo. O Drive não
serve: o link de compartilhamento aponta pra uma página HTML de visualização,
não pro arquivo.

Release do GitHub resolve porque:
  - o repo de assets é público, então o asset baixa sem autenticação;
  - 2 GiB por arquivo (nossos clipes têm ~40 MB), sem limite de tamanho total
    nem de banda, até 1.000 assets por release;
  - o token e o repo já existem, custo zero.

NÃO SUBSTITUI O DRIVE. O Drive continua sendo onde o Bryan revisa e organiza;
a Release é só a vitrine com endereço fixo pra ferramenta de agendamento
puxar. Rodar este script depois do `subir_drive.py`.

Uso:
    python publicar_release.py                      # publica o que ainda não foi
    python publicar_release.py --tag clipes-08-2026
    python publicar_release.py --saida urls.json    # grava o mapa nome -> url
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

import config

REPO = os.environ.get("GITHUB_REPO", "bryanaw2121-sketch/media-assets")
API = "https://api.github.com"
# Uma release por mês: mantém cada uma bem abaixo do teto de 1.000 assets e
# deixa o histórico legível na aba Releases.
TAG_PADRAO = f"clipes-{date.today():%m-%Y}"

RAIZ = Path(__file__).resolve().parent
REGISTRO = RAIZ / "estado" / "release_publicados.json"


def _token() -> str:
    for nome in ("GITHUB_TOKEN", "GH_TOKEN"):
        v = (os.environ.get(nome) or "").strip()
        if v:
            return v
    arq = RAIZ / "github_token.txt"
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    sys.exit("Falta GITHUB_TOKEN — sem ele não dá pra publicar na Release.")


def _cabecalho(token: str) -> dict:
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"}


def nome_de_asset(caminho_clipe: Path, nome_arquivo: str) -> str:
    """Nome do asset: ASCII, sem espaço, único dentro da release.

    O GitHub troca caractere fora de `[A-Za-z0-9._-]` por ponto na URL, o que
    embaralharia o nome e quebraria o link que a gente devolve. Então a
    sanitização é feita aqui, e o nome já sai igual ao que vai virar URL.

    O prefixo é a data + o nome da pasta do clipe, que carrega nota e título —
    dois clipes de dias diferentes nunca colidem.
    """
    bruto = f"{date.today():%Y-%m-%d}_{caminho_clipe.name}_{nome_arquivo}"
    sem_acento = (unicodedata.normalize("NFKD", bruto)
                  .encode("ascii", "ignore").decode("ascii"))
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "_", sem_acento).strip("_")
    return re.sub(r"_+", "_", limpo)


def achar_ou_criar_release(token: str, tag: str) -> dict:
    r = requests.get(f"{API}/repos/{REPO}/releases/tags/{tag}",
                     headers=_cabecalho(token), timeout=30)
    if r.status_code == 200:
        return r.json()
    if r.status_code != 404:
        r.raise_for_status()
    r = requests.post(f"{API}/repos/{REPO}/releases", headers=_cabecalho(token),
                      json={"tag_name": tag, "name": f"Clipes {tag}",
                            "body": ("Clipes do Modo Futuro hospedados pra "
                                     "agendamento. Gerado por publicar_release.py."),
                            "draft": False, "prerelease": False}, timeout=60)
    r.raise_for_status()
    return r.json()


def enviar_asset(token: str, release: dict, arquivo: Path, nome: str) -> str:
    """Sobe o arquivo e devolve a URL pública. Se o nome já existe, reaproveita.

    Reaproveitar em vez de sobrescrever é de propósito: o mesmo clipe
    republicado com o mesmo nome é o mesmo vídeo, e trocar o asset invalidaria
    um link que talvez já esteja agendado no Buffer.
    """
    for a in release.get("assets", []):
        if a["name"] == nome:
            return a["browser_download_url"]
    url = release["upload_url"].split("{")[0]
    with arquivo.open("rb") as fh:
        r = requests.post(url, headers={**_cabecalho(token),
                                        "Content-Type": "video/mp4"},
                          params={"name": nome}, data=fh, timeout=600)
    if r.status_code == 422:      # já existe (corrida entre dois runs)
        r2 = requests.get(release["url"], headers=_cabecalho(token), timeout=30)
        r2.raise_for_status()
        for a in r2.json().get("assets", []):
            if a["name"] == nome:
                return a["browser_download_url"]
    r.raise_for_status()
    return r.json()["browser_download_url"]


def _ja_publicados() -> dict:
    if REGISTRO.exists():
        try:
            return json.loads(REGISTRO.read_text(encoding="utf-8"))
        except Exception:
            print(f"[!] {REGISTRO.name} ilegível, tratando tudo como novo.")
    return {}


def _gravar(mapa: dict) -> None:
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(mapa, indent=2, ensure_ascii=False),
                        encoding="utf-8")


def clipes_prontos() -> list[tuple[float, Path]]:
    """Mesma varredura do subir_drive, sem o registro dele (filas separadas)."""
    achados = []
    for pj in config.SAIDA.rglob("post.json"):
        clipe = pj.parent
        if clipe.parent.parent.name in config.LOTES_IGNORADOS:
            continue
        if not (clipe / "short_9x16.mp4").exists():
            continue
        try:
            nota = float(json.loads(pj.read_text(encoding="utf-8")).get("nota", 0))
        except Exception:
            nota = 0.0
        achados.append((nota, clipe))
    achados.sort(key=lambda x: -x[0])
    return achados


def _publicar_manifesto(token: str, tag: str, mapa: dict) -> None:
    """Sobe/atualiza `manifesto.json` como asset da release.

    Junta o que ja' estava la' com o que acabou de sair, porque cada run so'
    enxerga os proprios clipes.
    """
    rel = achar_ou_criar_release(token, tag)
    antigo = {}
    for a in rel.get("assets", []):
        if a["name"] == "manifesto.json":
            try:
                # ver a nota em agendar_buffer.manifesto: sem o ?t= o CDN
                # devolve versao antiga e o merge PERDE clipes de outro run
                antigo = requests.get(
                    a["browser_download_url"] + f"?t={int(time.time())}",
                    timeout=60).json()
            except Exception:
                antigo = {}
            requests.delete(f"{API}/repos/{REPO}/releases/assets/{a['id']}",
                            headers=_cabecalho(token), timeout=30)
    antigo.update(mapa)
    corpo = json.dumps(antigo, ensure_ascii=False, indent=2).encode("utf-8")
    url = rel["upload_url"].split("{")[0]
    r = requests.post(url, headers={**_cabecalho(token), "Content-Type": "application/json"},
                      params={"name": "manifesto.json"}, data=corpo, timeout=120)
    if r.status_code < 300:
        print(f"manifesto.json atualizado ({len(antigo)} clipes)")
    else:
        print(f"  [!] manifesto falhou: {r.status_code}")


def main() -> None:
    p = argparse.ArgumentParser(description="Publica clipes numa Release do GitHub")
    p.add_argument("--tag", default=TAG_PADRAO)
    p.add_argument("--saida", help="grava o mapa nome -> url neste JSON")
    p.add_argument("--arquivo", type=Path,
                   help="publica UM arquivo específico (teste solto)")
    a = p.parse_args()

    token = _token()
    release = achar_ou_criar_release(token, a.tag)
    print(f"release '{a.tag}' -> {release['html_url']}")

    if a.arquivo:
        url = enviar_asset(token, release, a.arquivo,
                           nome_de_asset(a.arquivo.parent, a.arquivo.name))
        print(f"  {a.arquivo.name} -> {url}")
        return

    ja = _ja_publicados()
    fila = clipes_prontos()
    if not fila:
        print("nenhum clipe pronto pra publicar.")
        return

    novos = {}
    for nota, clipe in fila:
        pj = clipe / "post.json"
        chave = str(clipe.relative_to(config.SAIDA))
        if chave in ja:
            continue
        video = clipe / "short_9x16.mp4"
        nome = nome_de_asset(clipe, "short_9x16.mp4")
        try:
            url = enviar_asset(token, release, video, nome)
        except Exception as e:
            print(f"  [!] {clipe.name}: {str(e)[:110]}")
            continue
        legenda = ""
        leg = clipe / "post.txt"
        if leg.exists():
            legenda = leg.read_text(encoding="utf-8").strip()
        # `fonte` e `inicio_s` viajam junto porque a ORDEM DE POSTAGEM depende
        # deles: clipes do mesmo video-fonte tem que sair na ordem em que
        # aparecem no original (pedido do Bryan em 25/08/2026). Ordenar por
        # nota faz o corte do desfecho ir ao ar antes do que monta o contexto.
        try:
            m = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            m = {}
        novos[chave] = {"url": url, "nota": nota, "legenda": legenda,
                        "fonte": m.get("fonte", ""),
                        "inicio_s": m.get("inicio_s"),
                        "titulo": m.get("titulo", ""),
                        "publicado_em": f"{date.today():%Y-%m-%d}"}
        print(f"  nota {nota:.0f}  {nome[:60]}")
        print(f"     {url}")

    ja.update(novos)
    _gravar(ja)
    # O registro local NAO sobrevive: cada run do Actions comeca num runner
    # limpo. Entao o manifesto vai pra propria release, que e' o unico lugar
    # que persiste — e e' de la' que o agendador le' ordem e legenda.
    if novos:
        _publicar_manifesto(token, a.tag, ja)
    print(f"\n{len(novos)} clipe(s) publicado(s); {len(ja)} no total.")
    if a.saida:
        Path(a.saida).write_text(json.dumps(novos, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        print(f"mapa gravado em {a.saida}")


if __name__ == "__main__":
    main()
