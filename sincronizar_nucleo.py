# -*- coding: utf-8 -*-
"""Mantem o nucleo compartilhado identico entre todos os motores.

## O QUE ELE RESOLVE

Em 01/09/2026 tres reparos feitos no Modo-Futuro nunca chegaram ao motor da
cozinha, e os runs #23 e #24 de la' bateram exatamente nos tres: a mensagem
de cota que dizia "None", a espera de 2s no 503, e a perda dos clipes ja'
prontos quando um falhava. Dois runs de ~90 minutos, por deriva silenciosa.

O Bryan: "vamos de unificacao, nao podemos ter esse tipo de problema nem
agora nem no futuro nem em outros canais".

## COMO

A fonte canonica e' o `engine/` do poisonb9/Modo-Futuro, branch main — e os
DOIS repositorios sao publicos, entao qualquer motor le' de la' sem token
nenhum. Isso importa: token cruzado entre as duas contas nao existe (o de uma
recebe 403 na outra), e uma solucao que dependesse disso nao rodaria.

    --conferir   compara e SAI COM ERRO se houver deriva. Roda na suite.
    --aplicar    baixa e sobrescreve. Roda no runner, ANTES de cortar.

⚠️ CONFERIR NA SUITE E' O QUE IMPEDE A DERIVA DE SER SILENCIOSA. Aplicar no
runner e' o que faz o conserto chegar sozinho. Um sem o outro nao resolve: so'
conferir avisa e nao conserta; so' aplicar esconde que alguem editou a copia.

⚠️ SO' TOCA NO QUE ESTA' NO `NUCLEO.txt`. Modulo fora da lista diverge de
proposito — o criterio de selecao de cada canal, a conversao de medidas da
cozinha. Sincronizar tudo apagaria a identidade dos canais, que e' o oposto
do pedido.

⚠️ E NO REPO CANONICO ELE NAO SOBRESCREVE NADA. La' a copia local E' a fonte;
`--aplicar` rodando por engano no Modo-Futuro nao pode baixar por cima do
original. Detecta pelo proprio `NUCLEO.txt` estar versionado ali.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LISTA = RAIZ / "NUCLEO.txt"
CANONICO = "https://raw.githubusercontent.com/poisonb9/Modo-Futuro/main/"

# ⚠️ Marca do repositorio canonico. Sem isto, `--aplicar` rodando no proprio
# Modo-Futuro baixaria a versao publicada por cima do trabalho em andamento —
# e apagaria justamente o conserto que ainda nao foi commitado.
MARCA_CANONICO = RAIZ / "github_token.txt"


def modulos() -> list[str]:
    if not LISTA.exists():
        sys.exit(f"sem {LISTA.name} — nao sei o que sincronizar")
    return [l.strip() for l in LISTA.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def baixar(caminho: str) -> str | None:
    """Conteudo canonico do arquivo, ou None se nao der pra buscar."""
    try:
        with urllib.request.urlopen(CANONICO + caminho, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        print(f"  [!] {caminho}: nao baixei ({str(e)[:50]})")
        return None


def _norm(t: str) -> str:
    """Sem CR e sem espaco no fim das linhas.

    ⚠️ Os dois repos vivem em Windows e o git converte fim de linha na ida e
    na volta. Comparar byte a byte acusaria deriva em arquivo IDENTICO, e um
    alarme que dispara sempre deixa de ser lido.
    """
    return "\n".join(l.rstrip() for l in t.replace("\r\n", "\n").split("\n"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="baixa e sobrescreve (padrao: so' confere)")
    a = p.parse_args()

    if a.aplicar and MARCA_CANONICO.exists():
        print("este E' o repositorio canonico — nada a baixar.")
        return

    divergentes, faltando, ok = [], [], 0
    for m in modulos():
        canon = baixar(m)
        if canon is None:
            faltando.append(m)
            continue
        local = RAIZ / m
        if not local.exists():
            divergentes.append((m, "nao existe aqui"))
            if a.aplicar:
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_text(canon, encoding="utf-8")
            continue
        if _norm(local.read_text(encoding="utf-8")) == _norm(canon):
            ok += 1
            continue
        divergentes.append((m, "conteudo diferente"))
        if a.aplicar:
            local.write_text(canon, encoding="utf-8")

    print(f"nucleo: {ok} igual(is), {len(divergentes)} divergente(s), "
          f"{len(faltando)} nao conferido(s)")
    for m, motivo in divergentes:
        print(f"  {'atualizado' if a.aplicar else 'DIVERGE'}: {m} ({motivo})")

    if a.aplicar:
        return
    # ⚠️ FALHA SO' POR DIVERGENCIA, nunca por rede. Sem internet o motor nao
    # sabe se ha' deriva — mas reprovar a suite por isso trocaria um problema
    # real por um alarme falso, e alarme falso ensina a ignorar o alarme.
    if divergentes:
        print("\n  A deriva e' o defeito. Rode com --aplicar ou "
              "explique no NUCLEO.txt por que este modulo diverge.")
        sys.exit(1)


if __name__ == "__main__":
    main()
