# -*- coding: utf-8 -*-
"""Troca palavra sensível por versão escrita "segura" — só no TEXTO, nunca no áudio.

POR QUE EXISTE
Ordem do Bryan em 25/08/2026: "não quero perder vídeos bons, temos a
oportunidade de modificar para evitar certas palavras". O clipe é bom, o
assunto é do núcleo, e a única coisa que atrapalha é uma palavra escrita que
a moderação do TikTok lê mal.

A convenção já existe no TikTok brasileiro e apareceu no nosso próprio radar:
um vídeo com 0,3M de views escreve **"M0RTE"** com zero no lugar do O. Não é
invenção nossa, é o idioma da plataforma.

⚠️ O PONTO MAIS IMPORTANTE: a troca vale SÓ PRO TEXTO ESCRITO — legenda na
tela, título do card e legenda do post. O áudio da dublagem continua com a
palavra original, porque:
  - o TTS leria "m0rte" como "m zero érre tê é";
  - moderação de áudio é outro caminho, e a fala natural é o que sustenta a
    retenção, que é o gargalo medido do canal.

Ou seja: quem ouve, ouve normal. Quem lê (e o robô que lê), vê a versão
adaptada. Mesma lógica invertida do `engine/numeros.py`, que age só no áudio.
"""
from __future__ import annotations

import re
import unicodedata

# Chave = palavra como aparece no texto; valor = como deve ser ESCRITA.
# Preserva a leitura humana: quem lê entende na hora, o casador de palavra
# exato não casa. Mantém o sentido — não é censura do conteúdo, é grafia.
TROCAS = {
    "morte": "m0rte",
    "mortes": "m0rtes",
    "morto": "m0rto",
    "mortos": "m0rtos",
    "morta": "m0rta",
    "morrer": "m0rrer",
    "morreu": "m0rreu",
    "morrem": "m0rrem",
    "matar": "m4tar",
    "matou": "m4tou",
    "mataram": "m4taram",
    "mata": "m4ta",
    "assassinato": "assassin4to",
    "assassino": "assassin0",
    "assassinar": "assassin4r",
    "suicídio": "suic1dio",
    "suicidio": "suic1dio",
    "suicida": "suic1da",
    "massacre": "mass4cre",
    "genocídio": "genoc1dio",
    "genocidio": "genoc1dio",
    "exterminar": "extermin4r",
    "extermínio": "extermin1o",
    "estupro": "estupr0",
    "tortura": "tortur4",
    "arma": "arm4",
    "armas": "arm4s",
}

# `arma` é do núcleo do canal (drones militares, armas autônomas) e aparece
# muito. Fica na lista mas pode ser desligado por aqui se atrapalhar a leitura.
SEMPRE_MANTER = {"arma", "armas"}


def _chave(p: str) -> str:
    p = unicodedata.normalize("NFKD", p.lower())
    return p.encode("ascii", "ignore").decode("ascii")


_MAPA = {}
for _orig, _novo in TROCAS.items():
    _MAPA.setdefault(_chave(_orig), _novo)


def _casar_caixa(original: str, novo: str) -> str:
    """Devolve `novo` na mesma caixa do `original` (ALTA, Título, ou minúscula).

    O título do card vem em caixa alta em boa parte das palavras (ver
    destaque.PROMPT_TITULO), então trocar sem respeitar isso deixaria
    "M0rte" no meio de "A M0RTE CHEGOU".
    """
    if original.isupper():
        return novo.upper()
    if original[:1].isupper():
        return novo[:1].upper() + novo[1:]
    return novo


def texto(t: str, incluir_armas: bool = False) -> str:
    """Aplica as trocas preservando pontuação e caixa. Só pra texto ESCRITO."""
    if not t:
        return t

    def trocar(m: re.Match) -> str:
        palavra = m.group(0)
        k = _chave(palavra)
        if k not in _MAPA:
            return palavra
        if not incluir_armas and k in SEMPRE_MANTER:
            return palavra
        return _casar_caixa(palavra, _MAPA[k])

    return re.sub(r"[A-Za-zÀ-ÿ]+", trocar, t)


def palavras(ps: list[dict], incluir_armas: bool = False) -> list[dict]:
    """Mesma troca na lista de palavras da legenda karaokê.

    Cada item é {"palavra"/"texto", "inicio", "fim"} — o timing NÃO muda,
    porque a troca não altera a contagem de palavras nem a fala.
    """
    saida = []
    for p in ps or []:
        q = dict(p)
        for campo in ("palavra", "texto", "word"):
            if campo in q and isinstance(q[campo], str):
                q[campo] = texto(q[campo], incluir_armas)
        saida.append(q)
    return saida
