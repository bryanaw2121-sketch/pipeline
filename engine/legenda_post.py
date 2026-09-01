# -*- coding: utf-8 -*-
"""A legenda do POST — uma so', usada pelo Buffer e pelo .txt do Drive.

POR QUE ESTE MODULO EXISTE

Ate' 31/08/2026 havia DUAS funcoes montando a legenda, e elas discordavam:

    main._legenda                     titulo + descricao + premium + hashtags
    publicar_tiktok.legenda_do_clipe  titulo + hashtags

A segunda escreve o `.txt` que vai pro Drive ao lado do clipe. O mesmo clipe
saia com legenda COMPLETA no post e POBRE no arquivo.

MEDIDO nos arquivos do Drive naquele dia:

    @truque.importado (31-08 v2)   0,1 KB   x4
    cozinha                        5,4 a 12,1 KB

⚠️ E A LEGENDA PREMIUM ERA GERADA. O log do run #196 registrou "legenda
premium: 1646 chars" nos quatro clipes: o texto existia no post.json e se
perdia na hora de escrever o arquivo. Nao era falta de conteudo — eram duas
fontes de verdade.

⚠️ Por que passou despercebido: o post no Buffer ficava CERTO, porque usa a
outra funcao. So' quem abrisse o .txt no Drive veria a diferenca — e o Drive
so' virou caminho de revisao quando o Bryan decidiu postar as estreias na mao.

⚠️ E a primeira tentativa de conserto foi COPIAR a logica pra segunda funcao.
O teste com caso negativo pegou: com descricao vazia, uma deixava duas linhas
em branco a mais que a outra. Copiar logica cria a proxima divergencia. Por
isso agora e' UMA funcao, e as duas chamam esta.
"""
from __future__ import annotations

import unicodedata


def hashtag(tag: str) -> str:
    """`#` + tag sem acento, sem espaco, so' alfanumerico.

    Hashtag nao pode ter espaco nem acento: "#Elon Musk" viraria "#Elon" mais
    o texto solto "Musk". E acento e' ruim pra descoberta — quem busca digita
    sem —, entao normaliza pra ASCII.
    """
    sem_acento = (unicodedata.normalize("NFKD", tag)
                  .encode("ascii", "ignore").decode("ascii"))
    return "#" + "".join(ch for ch in sem_acento if ch.isalnum())


def montar(meta: dict, nome_padrao: str = "") -> str:
    """A legenda pronta pra colar: titulo, descricao, premium e hashtags.

    A ordem importa: a DESCRICAO PREMIUM entra entre a descricao curta e as
    hashtags — e' o contexto que nao coube nos 90s do corte, e e' texto
    indexavel que a busca do TikTok le'. Ver engine/legenda_premium.py.

    Campo vazio nao deixa linha em branco sobrando: um clipe sem descricao
    nao pode sair com um buraco no meio da legenda.
    """
    partes = [str(meta.get("titulo") or nome_padrao or "").strip()]
    for campo in ("descricao", "legenda_premium"):
        v = str(meta.get(campo) or "").strip()
        if v:
            partes.append(v)
    tags = " ".join(hashtag(t) for t in (meta.get("tags") or []) if t).strip()
    if tags:
        partes.append(tags)
    return "\n\n".join(p for p in partes if p).strip()


# Quantas linhas em branco sobram no fim do .txt. Pedido do Bryan em
# 31/08/2026: no celular, o seletor de texto agarra melhor quando ha' area
# vazia depois da ultima linha — sem isso a selecao esbarra no fim do arquivo
# e ele precisa mirar no ultimo caractere.
LINHAS_VAZIAS_NO_FIM = 8


def para_arquivo(meta: dict, nome_padrao: str = "") -> str:
    """A mesma legenda, com espaco vazio no fim, pro .txt que o Bryan copia.

    ⚠️ SO' PRA ARQUIVO. O `montar` continua sem sobra, porque o mesmo texto
    vira o corpo do post no Buffer e a mensagem do Telegram — linhas em
    branco no fim de um post publicado sao lixo visivel.
    """
    return montar(meta, nome_padrao) + chr(10) * LINHAS_VAZIAS_NO_FIM
