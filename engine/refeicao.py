# -*- coding: utf-8 -*-
"""Que REFEICAO e' este clipe — para casar o post com a hora de comer.

A IDEIA

A grade de postagem da cozinha ja' cai em cima das refeicoes, por acidente:

    08:15 SP   cafe da manha
    11:33 SP   almoco
    16:27 SP   lanche da tarde
    19:30 SP   jantar

Mas o pareamento e' `zip(fila, horarios)`: o primeiro clipe pega o primeiro
slot livre, sem olhar o que ele e'. Entao uma receita de cafe da manha pode
cair as 16:27, que e' quando ninguem esta' pensando em ovo mexido.

## POR QUE ISSO PODE IMPORTAR (e por que pode nao importar)

O gargalo MEDIDO do @modofuturo e' retencao: a audiencia sai aos 0:02. Casar
a receita com a hora e' uma aposta de RELEVANCIA — quem ve panqueca as 8h da
manha tem mais motivo pra ficar do que quem ve as 16h.

⚠️ Mas isto e' HIPOTESE, nao medicao. O proprio projeto ja' provou que a nota
do motor nao preve views (nota 88 deu 1822, nota 98 deu 584). Casar horario
pode nao mudar nada. A implementacao existe pra permitir MEDIR a diferenca,
nao porque a diferenca esta' provada.

## A REGRA DO FALLBACK

Clipe que nao e' de refeicao nenhuma — ou que serve pra qualquer uma — cai no
comportamento de hoje: o proximo slot livre, na ordem que ja' existe. Nada
fica sem horario por nao ter sido classificado.
"""
from __future__ import annotations

import re
import unicodedata

# FAIXA de horas (SP) em que cada refeicao faz sentido, inclusive nas duas
# pontas.
#
# ⚠️ Sao FAIXAS, nao as horas exatas da grade. A primeira versao amarrou cada
# refeicao a hora do slot — e ai a medicao acusou "Batata-Doce com Frango a
# Fajita as 12:30" e "Ensopado de Carne as 20:00" como fora de hora, quando
# 12:30 e' almoco e 20:00 e' jantar em qualquer casa do Brasil. O erro era do
# criterio, nao do agendamento: a grade mudou ao longo do tempo (ja' teve slot
# as 12:30 e as 20:00) e amarrar na grade de hoje reprova o passado sem
# motivo.
#
# As faixas se sobrepoem de proposito: sobremesa serve de tarde e de noite, e
# lanche cobre o vao entre almoco e jantar.
JANELAS = {
    "cafe_da_manha": (5, 10),
    "almoco": (11, 14),
    "lanche": (15, 17),
    "sobremesa": (15, 22),
    "jantar": (18, 22),
}

# Termos por refeicao. Sao os que aparecem em titulo de receita de verdade —
# tirados dos posts reais do @cozinha.internacional, nao inventados.
TERMOS = {
    "cafe_da_manha": [
        "cafe da manha", "breakfast", "panqueca", "pancake", "ovo mexido",
        "ovos mexidos", "omelete", "torrada", "toast", "granola", "aveia",
        "overnight oats", "iogurte", "muffin", "waffle", "cereal", "tapioca",
        "pao de queijo", "vitamina", "smoothie", "huevos rancheros", "bacon",
        "cottage",
    ],
    "almoco": [
        "almoco", "lunch", "marmita", "meal prep", "arroz", "feijao",
        "macarrao", "massa", "salada", "frango grelhado", "bife", "quentinha",
        "prato feito", "lasanha", "risoto", "batata-doce", "bowl",
    ],
    "lanche": [
        "lanche", "snack", "sanduiche", "sandwich", "wrap", "pita",
        "hamburguer", "burger", "pipoca", "petisco", "bolinho", "pastel",
        "coxinha", "cafe da tarde", "chips",
    ],
    "jantar": [
        "jantar", "dinner", "sopa", "caldo", "ensopado", "assado", "torta",
        "pizza", "peixe", "carne", "costela", "curry", "guisado", "cozido",
    ],
    "sobremesa": [
        "sobremesa", "dessert", "bolo", "cake", "brownie", "pudim", "mousse",
        "doce", "chocolate", "sorvete", "cheesecake", "cookie", "biscoito",
        "torta doce", "brigadeiro", "cobbler", "merengue", "chantilly",
        "buttercream",
    ],
}


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.lower())


def classificar(texto: str) -> str | None:
    """A refeicao do clipe, ou None se nada casar.

    Quando mais de uma casa, vence a que tiver o termo MAIS LONGO — "cafe da
    manha" ganha de "cafe", e "torta doce" ganha de "torta". Casar por termo
    curto e' como a chave de dedup errou em 30/08: prefixo demais, identidade
    de menos.
    """
    t = _normalizar(texto)
    melhor, tamanho = None, 0
    for refeicao, termos in TERMOS.items():
        for termo in termos:
            if termo in t and len(termo) > tamanho:
                melhor, tamanho = refeicao, len(termo)
    return melhor


def combina(texto: str, hora_sp: int) -> bool:
    """Este clipe faz sentido neste slot?

    Clipe sem refeicao combina com QUALQUER hora — nao classificar nunca pode
    impedir um clipe de ser agendado.
    """
    r = classificar(texto)
    if r is None:
        return True
    ini, fim = JANELAS[r]
    return ini <= hora_sp <= fim


def casar(fila: list, horarios: list) -> list:
    """Reordena `fila` para que cada horario receba um clipe que combine.

    Recebe a fila JA' ordenada pela regra 1 (por video-fonte, e dentro dele
    por posicao no original) e devolve uma permutacao dela. Nao inventa nem
    descarta clipe: `len` e conteudo sao os mesmos, so' a ordem muda.

    O algoritmo e' guloso e CONSERVADOR: para cada horario, pega o PRIMEIRO
    da fila restante que combine. Como varre na ordem original, um clipe so'
    "fura" a fila quando o que estava na frente nao combina — entao a regra 1
    e' preservada em tudo que a refeicao nao exigir mudar.

    Se nenhum dos restantes combinar com o horario, pega o primeiro mesmo.
    E' o comportamento de hoje, e e' o que o Bryan pediu: "se nao tiver nada,
    posta aleatorio mesmo". Nada fica sem horario por causa desta funcao.
    """
    restantes = list(fila)
    saida = []
    for quando in horarios:
        if not restantes:
            break
        escolhido = 0
        for i, (_, clipe) in enumerate(restantes):
            texto = (clipe.get("legenda") or clipe.get("titulo") or "")
            if combina(texto, quando.hour):
                escolhido = i
                break
        saida.append(restantes.pop(escolhido))
    # Sobra vai no fim, na ordem original: mais clipes que horarios e' normal.
    return saida + restantes
