# -*- coding: utf-8 -*-
"""A receita escrita, pra descricao do post.

POR QUE EXISTE
Ideia do Bryan em 28/08/2026. Num canal de receita a descricao vale mais que na
maioria dos nichos: e' o texto que a pessoa le' **com a mao na massa**, sem
pausar o video. E e' texto indexavel, que ajuda a busca do TikTok.

E resolve o furo que apareceu no primeiro lote: a conversao de medida quase nao
aparecia na FALA, porque a fonte fala numero por extenso ("half a cup") e o
`conversoes.py` so' entende digito. Aqui quem converte e' o modelo, com a regra
na mao — e o resultado do teste foi "120 ml de leite" no lugar de "meia xicara".

O comentario fixado, que seria o outro lugar natural, NAO da' pra automatizar:
a API do TikTok foi recusada em definitivo (22/08). Fixar comentario e' na mao.

LIMITE: o TikTok aceita 2200 caracteres na legenda. O prompt pede no maximo
1400 pra sobrar espaco pro titulo e as hashtags.
"""
from __future__ import annotations

import re

PROMPT_RECEITA_TEXTO = """Abaixo esta a fala de um video de receita, ja em
portugues.

Escreva a RECEITA em texto, para a descricao do post. Formato exato:

INGREDIENTES
- item com quantidade
- item com quantidade

MODO DE PREPARO
1. passo curto
2. passo curto

REGRAS:
- Maximo 1400 caracteres no total.
- Quantidade em medida BRASILEIRA. Onde a fala disser "xicara", converta para
  gramas ou ml: a xicara brasileira varia de 150 a 250 ml e a americana e 240 ml
  fixos, entao deixar "xicara" e' ambiguo. Farinha 1 xic = 120 g, acucar = 200 g,
  leite/agua = 240 ml, manteiga = 227 g, mel = 340 g.
  Colher de sopa e de cha PODEM ficar como estao — a brasileira e a americana
  sao equivalentes (15 ml e 5 ml).
- Temperatura sempre em Celsius.
- NAO invente ingrediente nem passo que nao esta na fala.
- Se a fala nao disser a quantidade, escreva "a gosto" ou omita. NUNCA chute:
  numero errado numa receita destroi a confianca, que e' o unico ativo deste
  canal.
- Sem introducao, sem despedida, sem hashtag. So a receita.

Fala:
{texto}"""


def da_fala(segmentos: list[dict]) -> str:
    """Junta os segmentos traduzidos num texto corrido, sem marca de tempo."""
    return " ".join(s["texto"].strip() for s in segmentos if s.get("texto"))


def gerar(segmentos: list[dict]) -> str:
    """Devolve a receita em texto, ou string vazia se nao der.

    Nunca levanta: descricao e' enfeite, e derrubar um clipe pronto por causa
    dela seria perder 20 minutos de render por nada.
    """
    from . import traducao
    texto = da_fala(segmentos)
    if len(texto) < 120:
        return ""
    try:
        r = traducao._traduzir_texto(texto, prompt=PROMPT_RECEITA_TEXTO)
    except Exception:
        return ""
    r = re.sub(r"^```.*?$|^```$", "", r, flags=re.M).strip()
    return r[:1900]
