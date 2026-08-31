# -*- coding: utf-8 -*-
"""Fecha o ciclo: quem do registro ja' foi ao ar, e por onde.

Pedido do Bryan em 31/08/2026: "ter o controle do que foi postado ou nao,
atraves do buffer ou da minha mao ou de prints. Nunca repostar video ja'
postado. E de maneira automatica ao maximo possivel."

O QUE E' AUTOMATICO E O QUE NAO PODE SER

  - Buffer: automatico. Le' os posts `sent` dos 5 canais e marca.
  - Mao:    `--mao "<titulo>"`. ⚠️ NAO TEM COMO SER AUTOMATICO — a API de
            publicacao do TikTok foi recusada em definitivo (22/08/2026, uso
            pessoal nao e' suportado). Nao existe caminho pra perguntar ao
            TikTok o que esta' no ar. Fingir que existe seria pior que a
            lacuna.
  - Print:  `--print <arquivo>`, mesmo caminho manual.

⚠️ E O BUFFER NAO SABE DE TUDO. As estreias do @atefalhar e do
@truque.importado foram postadas na mao; pro Buffer esses canais tem ZERO
publicados. Uma lista antirrepeticao que so' olhasse o Buffer autorizaria
justamente a repeticao que ela existe pra impedir.

⚠️ O CASAMENTO COM O BUFFER E' POR TITULO, e titulo e' chave fraca — o Buffer
nao sabe o sha do arquivo. E' o melhor disponivel desse lado, e por isso o
registro guarda o sha na ORIGEM (no publicar_release), onde o arquivo esta' na
mao. Quando os dois discordam, o sha manda.

⚠️ CADA MOTOR CONFERE OS SEUS CANAIS, E SO' OS SEUS. O registro vive dentro
do repositorio, entao sao DOIS registros: um aqui e um no outro motor. Se
este script olhasse os 5 canais, todo post do canal do outro motor viraria
"orfao" — e orfao e' o sinal de que a lista esta' incompleta. Um sinal que
acusa 100% no caso normal nao serve pra avisar de nada.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

from engine import registro_clipes as reg

API = "https://api.buffer.com/"
CANAIS = {
    "cozinha.internacional": ("6a90dddb9bb05f07b058e9bc",
                              "6a90de80ccaf649a672ebe15",
                              "BUFFER_TOKEN"),
}
Q = ("query($i: PostsInput!){ posts(input:$i){ edges{ node{ dueAt text } } } }")


def publicados(token: str, org: str, canal: str) -> list[dict]:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": Q, "variables": {"i": {
            "organizationId": org,
            "filter": {"status": ["sent"], "channelIds": [canal]}}}}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    if not d.get("data"):
        raise RuntimeError(json.dumps(d.get("errors"))[:150])
    return [e["node"] for e in d["data"]["posts"]["edges"]]


def do_buffer() -> list[str]:
    linhas = []
    for nome, (org, ch, env) in CANAIS.items():
        token = (os.environ.get(env) or "").strip()
        if not token:
            linhas.append(f"  {nome}: sem token — NAO conferido")
            continue
        try:
            posts = publicados(token, org, ch)
        except Exception as e:
            linhas.append(f"  {nome}: Buffer recusou ({str(e)[:50]})")
            continue
        casou = orfaos = 0
        for p in posts:
            sha = reg.sha_por_titulo(p["text"])
            if sha is None:
                orfaos += 1
                continue
            reg.marcar_postado(sha, origem="buffer", quando=p["dueAt"],
                               canal=nome, detalhe=p["text"].splitlines()[0][:70])
            casou += 1
        # ⚠️ ORFAO NAO E' RUIDO: e' post no ar que o registro nao conhece.
        # Enquanto houver orfao, a lista antirrepeticao esta' incompleta.
        linhas.append(f"  {nome}: {len(posts)} publicados, {casou} casados, "
                      f"{orfaos} SEM registro")
    return linhas


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mao", metavar="TITULO",
                   help="marca como postado na mao (titulo ou trecho dele)")
    p.add_argument("--print", dest="prova", metavar="TITULO",
                   help="marca como postado, comprovado por print")
    p.add_argument("--canal", default="")
    p.add_argument("--pendentes", action="store_true",
                   help="lista o que saiu do pipeline e nunca foi postado")
    a = p.parse_args()

    if a.mao or a.prova:
        titulo = a.mao or a.prova
        sha = reg.sha_por_titulo(titulo)
        if sha is None:
            raise SystemExit(f"nao achei no registro: {titulo!r}\n"
                             "confira o titulo — o registro so' conhece o que "
                             "saiu do pipeline.")
        reg.marcar_postado(sha, origem="mao" if a.mao else "print",
                           canal=a.canal, detalhe=titulo)
        print(f"marcado ({'mao' if a.mao else 'print'}): {titulo[:60]}")
        return

    linhas = ["Conferencia do que ja' foi ao ar", ""] + do_buffer()

    pend = reg.nao_postados()
    linhas.append("")
    linhas.append(f"{len(pend)} clipe(s) sairam do pipeline e NAO foram postados:")
    for x in pend[:20]:
        linhas.append(f"  {x['idade_dias']:>3}d  {x['canal']:<18} {x['titulo'][:52]}")
    if pend:
        # ⚠️ LISTA, NAO APAGA. O Bryan quer conferir antes de eliminar — um
        # clipe parado pode estar so' esperando a vez na fila.
        linhas.append("  (conferir antes de eliminar — nada e' apagado aqui)")

    Path("relato_postados.txt").write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
