# -*- coding: utf-8 -*-
"""Comparar clipe novo com o que ja' foi publicado — sem deixar passar.

O DEFEITO, MEDIDO EM 30/08/2026

A chave de dedup normaliza o texto e corta em 70 caracteres. Isso funciona
quando o titulo esta' numa linha e a descricao noutra. Nao e' o caso:

    dos 101 posts reais do @modofuturo, 88 tem titulo e descricao NA MESMA
    LINHA — 87% do historico.

Nesses 88 a chave vira titulo+descricao, e nunca casa com a chave de um clipe
novo, que e' so' o titulo:

    publicado:  aleidemoorerealmentemorreunvidiainteleibmrespondemleidemooreeofuturodo
    clipe novo: aleidemoorerealmentemorreunvidiainteleibmrespondem

Resultado: a dedup enxergava 13 posts de 101, e em 30/08 o run #185
reagendou pro dia 01/09 dois clipes publicados em 26/08. Duplicata e' a causa
MEDIDA dos colapsos de alcance de 02/08 e 25/08.

⚠️ Nao era paginacao. `MAX_PAGINAS = 4` busca as paginas 1 a 4, e as duas
duplicatas estavam na pagina 4 — foram VISTAS e passaram. Trocar o limite nao
teria consertado nada. (A hipotese da paginacao foi a primeira, e estava
errada.)

## A REGRA

Uma chave e' a mesma peca da outra quando **uma e' prefixo da outra**, com
piso de PISO caracteres. Prefixo, e nao corte fixo, porque titulo curto nao
sobrevive ao corte: "O segredo do Ryzen 9800X3D revelado!" normaliza pra 30
caracteres, e comparar os primeiros 45 de cada lado nunca casaria.

## O FALSO POSITIVO FOI MEDIDO, NAO SUPOSTO

Contra os 101 posts reais, a regra casa 4 pares. Os 4 sao duplicatas de
VERDADE — os mesmos colapsos que ja' estavam no handoff:

    A VERDADEIRA CORRIDA DA IA          25/08 e 26/08
    Exercito Cria Baratas Ciborgues     25/08 e 26/08
    A industria que controla todas...   25/08 12:44 e 14:30
    Testei um EXOESQUELETO              02/08 12:02 e 23:01

Zero falso positivo. O teste refaz essa conta com os 101 textos guardados em
`teste/dados/posts_modofuturo.json`, sem gastar API.

⚠️ Duas dessas quatro foram republicacoes DELIBERADAS (o Bryan apagou do
TikTok pra repostar). Isso continua funcionando: o manifesto marca
`republicacao`, e essa flag passa por cima da checagem — ver `cabe()` no
agendar_buffer.
"""
from __future__ import annotations

# Piso de caracteres para aceitar casamento por prefixo. Abaixo disso, so'
# igualdade exata.
#
# Calibragem: com 20, 25 ou 30 o resultado nos 101 posts reais e' identico —
# 4 pares, todos duplicatas de verdade. Com 35 cai pra 3, e um par real
# escapa. 25 fica no meio do patamar estavel, longe da borda que perde caso.
PISO = 25


def ja_visto(chave: str, conhecidas) -> bool:
    """A `chave` corresponde a alguma das `conhecidas`?

    Chave vazia nunca casa: clipe sem titulo nao pode ser confundido com
    todo o resto so' porque o texto ficou em branco.
    """
    if not chave:
        return False
    for k in conhecidas:
        if not k:
            continue
        if len(chave) < PISO or len(k) < PISO:
            # Curta demais pra confiar no prefixo — "bolo" seria prefixo de
            # metade do canal. Exige igualdade.
            if chave == k:
                return True
            continue
        if chave.startswith(k) or k.startswith(chave):
            return True
    return False
