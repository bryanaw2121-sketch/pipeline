# -*- coding: utf-8 -*-
r"""Escapar o valor que entra numa consulta do Drive.

POR QUE EXISTE

Em 30/08/2026 o run #14 do `pipeline` cortou os seis clipes de bolo, deu nota
neles (95, 92, 90, 88, 87, 85), subiu os dois primeiros pro Drive e MORREU no
terceiro:

    04_nota88_Bolo Floral Degrade e Bolo S'mores com Merengu.mp4
    HttpError 400 ... 'Invalid Value', location: 'q'

O apostrofo de "S'mores" fechou a aspa da consulta antes da hora:

    name='...Bolo S'mores...' and '<pasta>' in parents

O Drive recebeu uma expressao quebrada e recusou. O run inteiro caiu — duas
horas de corte perdidas por UM caractere que veio do titulo que o proprio
modelo escreveu.

Nao e' um caso exotico. Titulo de receita em ingles vive de apostrofo:
"S'mores", "Shepherd's Pie", "Hershey's". O motor nomeia o arquivo com o
titulo, entao a chance de repetir e' alta.

POR QUE UMA FUNCAO, E NAO UM `.replace` EM CADA LUGAR

Sao QUATRO lugares no motor que montam consulta com nome de arquivo dentro
(`subir_cortes_drive.py`, `enviar_bruto_drive.py`, `subir_drive.py`,
`renumerar_a_postar.py`) e mais alguns que montam com id de pasta. Consertar
so' o que quebrou hoje deixa os outros tres esperando a vez — foi assim que a
conversao de medidas precisou de tres rodadas.

A REGRA DO DRIVE

Dentro de uma string entre aspas simples, o Drive v3 aceita `\` para barra
invertida e `\'` para apostrofo. A barra tem que ser trocada PRIMEIRO, senao
a barra que a gente mesmo acabou de inserir seria escapada de novo.
"""
from __future__ import annotations


# A barra invertida e o apostrofo, escritos assim para que ninguem os perca
# ao editar este arquivo com script ou heredoc — foi o que aconteceu na
# primeira tentativa de escrever esta funcao, em 30/08/2026.
BARRA = '\\'
APOSTROFO = "'"


def aspas(valor: str) -> str:
    """Devolve `valor` pronto pra ir entre aspas simples numa consulta do Drive.

    Nao poe as aspas — quem monta a consulta e' que poe. Assim a funcao serve
    igual pra `name='...'`, pra `'...' in parents` e pra qualquer outra.
    """
    return (str(valor)
            .replace(BARRA, BARRA + BARRA)
            .replace(APOSTROFO, BARRA + APOSTROFO))
