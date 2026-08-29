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

Escreva a receita para a descricao do post. Formato EXATO:

<A LINHA MAIS IMPORTANTE DE TODAS. E' a unica que aparece antes do "ver mais"
do TikTok, junto com o titulo. Escreva o RESUMO DA RECEITA em uma linha:
os 3 ou 4 ingredientes principais com as quantidades ja convertidas, mais a
temperatura ou o tempo. Separe com "·". Ex:
"2 ovos · 120 ml de leite · 180°C por 25 min"
"500 g de farinha · 300 ml de agua · 2 h de descanso"
Sem verbo, sem frase, sem enfeite. E' um cartao, nao uma apresentacao.>

<uma linha: rende quantas porcoes e tempo total. Ex: "Rende 2 porcoes - 15 min">

INGREDIENTES
- item com quantidade
- item com quantidade

MODO DE PREPARO
1. passo curto
2. passo curto

SUBSTITUICOES
- <ingrediente dificil de achar no Brasil> -> <o que usar no lugar>

MEDIDAS
- <so se voce converteu alguma medida: uma linha curta explicando. Ex:
  "1 xicara americana = 240 ml. A brasileira varia de 150 a 250 ml, por isso
  convertemos.">

REGRAS DE MEDIDA — leia com atencao, e' o diferencial do canal:
- LIQUIDO (leite, agua, oleo, caldo): converta para ml. 1 xicara = 240 ml.
- SECO E PESAVEL (farinha, acucar, manteiga, mel, aveia): converta para GRAMAS.
  Farinha 1 xic = 120 g, acucar = 200 g, manteiga = 227 g, mel = 340 g,
  aveia = 90 g.
- INGREDIENTE PICADO OU EM PEDACOS (legume, fruta, queijo, castanha): NUNCA em
  ml e NUNCA em gramas. Mantenha a medida de volume que a fala usou
  ("1/4 de xicara de pimentao picado") ou use a unidade natural
  ("1 pimentao medio"). Ninguem pesa pimentao picado nem mede legume em ml —
  "60 ml de pimentao" e "35 g de pimentao picado" foram os dois erros reais de
  28/08/2026. A ambiguidade da xicara so' importa em farinha e liquido, onde a
  diferenca muda a receita; em legume picado, nao muda nada.
- COLHER de sopa e de cha ficam como estao: a brasileira e a americana sao
  equivalentes (15 ml e 5 ml).
- Temperatura sempre em Celsius.

OUTRAS REGRAS:
- MEDIDAS: essa secao e a promessa do canal ("350F e 180C. De nada."), entao
  so aparece quando houve conversao DE VERDADE. Se a receita nao tinha nenhuma
  medida americana, OMITA a secao — enfeite vazio tira a credibilidade do
  resto.
- Maximo 1600 caracteres no total.
- NAO invente ingrediente, quantidade nem passo que nao esta na fala. Se a fala
  nao disser a quantidade, escreva "a gosto". Numero chutado numa receita
  destroi a confianca, que e' o unico ativo deste canal.
- SUBSTITUICOES: so' liste o que e' de fato dificil no Brasil (endro, buttermilk,
  feta, xarope de bordo). Se tudo for facil de achar, OMITA a secao inteira.
- Se a fala nao deixar claro o rendimento ou o tempo, estime pelo contexto de
  forma conservadora, ou omita a linha.
- REVISE o portugues antes de responder: palavra inventada numa receita
  destroi a confianca. Em 28/08/2026 saiu "macios e meciosos" — "meciosos"
  nao existe.
- Sem introducao, sem despedida, sem hashtag. So' a receita.

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
