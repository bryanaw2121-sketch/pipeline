# -*- coding: utf-8 -*-
"""Guarda contra corte que abre ORFAO — preso na receita anterior.

POR QUE EXISTE

O video-fonte deste canal e' compilacao: cinco, seis receitas num video so'.
Quando o corte comeca no meio, o espectador NUNCA VIU a receita anterior — e
uma frase que se apoia nela nao significa nada.

Medido em 30/08/2026, nos 32 cortes ja' produzidos:

     24 (75%)  abrem com gancho — prato, beneficio ou promessa
      6 (19%)  abrem ORFAOS
      2  (6%)  abrem em processo ("pegue uma tigela")

Os seis abriam assim:

     "Coloque a MESMA frigideira de volta ao fogo."
     "TERMINAMOS o nosso grao-de-bico. Em seguida..."
     "Abacate. Para a segunda combinacao..."

"A mesma frigideira" qual? O espectador chegou agora. Isso e' confusao nos
dois primeiros segundos — exatamente onde a retencao morre: a medicao do canal
irmao mostrou 14% de retencao media e a audiencia saindo em 0:01.

E o contrario tambem esta' medido: o melhor video do canal (536 views) e' o
que abre mais limpo, com beneficio — "Sustenta bastante e me mantem
satisfeita sem me deixar muito pesada".

POR QUE GUARDA E NAO SO' REGRA NO PROMPT

A regra entrou no PROMPT_RECEITA junto com esta guarda. Mas prompt PEDE e
modelo as vezes nao obedece — os seis cortes orfaos sairam de um prompt que
ja' mandava "comece com o prato pronto". Guarda MEDE o resultado.
"""
from __future__ import annotations

import re
import unicodedata

# Palavras que so' fazem sentido se voce viu o que veio antes.
ANCORAS = [
    "mesma", "mesmo", "terminamos", "terminei", "acabamos",
    "em seguida", "de volta", "agora que", "depois disso",
    "como eu disse", "como falei", "aquele", "aquela", "esse ai",
    "novamente", "de novo", "outra vez",
    # "os NOSSOS graos-de-bico" pressupoe que voce viu a gente fazer. Achado
    # em 30/08 num corte que passou pela primeira versao desta guarda: a
    # frase era longa o bastante pra escapar do piso de palavras.
    "nossos", "nossas", "nosso ", "nossa ",
]

# Ordinal apontando pra fora do trecho: "para a SEGUNDA combinacao" pressupoe
# a primeira. "primeira" NAO entra — abrir na primeira e' legitimo.
ORDINAIS = ["segunda", "segundo", "terceira", "terceiro", "quarta", "quarto",
            "quinta", "quinto", "sexta", "sexto"]

# Abaixo disso a primeira "frase" e' so' um resto da fala anterior: uma
# palavra solta que era o fim da frase de tras ("Abacate.", "Peito de frango!").
PALAVRAS_MIN_1A_FRASE = 4


def _limpo(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.lower()).strip()


def primeira_frase(palavras: list[dict], limite: int = 30) -> str:
    """Junta as primeiras palavras ate' o primeiro ponto final."""
    txt = " ".join((p.get("palavra") or "") for p in (palavras or [])[:limite])
    corte = re.split(r"[.!?]", txt, maxsplit=1)
    return (corte[0] if corte else txt).strip()


# Fala de ENCERRAMENTO do canal-fonte. Um corte feito so' disso nao e' receita
# nenhuma — e ainda divulga o site e o podcast de outra pessoa.
#
# Achado em 30/08/2026: o corte "Dica de Ouro para Guardar suas Marmitas" era
# o outro inteiro do Fit Men Cook — "clique no botao de curtir, se inscrever
# no canal... confira o nosso podcast... o endereco e' thetabletalks.com...
# tchau, pessoal!".
#
# O PROMPT_RECEITA ja' proibia ("nao inclua se inscreva, resumo do que foi
# dito ou qualquer fala de encerramento") e o modelo produziu assim mesmo.
# Prompt pede, guarda mede.
ENCERRAMENTO = [
    "se inscrever", "se inscreva", "clicar no botao", "clique no botao",
    "botao de curtir", "ative o sininho", "ativar o sininho",
    "link na descricao", "nosso podcast", "confira tambem",
    "ate a proxima", "tchau, pessoal", "tchau pessoal", "e isso por hoje",
    "comente aqui embaixo", "nos vemos", "obrigado por assistir",
]
# Um "se inscreva" solto no meio de uma receita longa nao condena o corte; o
# que condena e' o corte SER encerramento. Por isso conta ocorrencias e olha
# a densidade, em vez de barrar na primeira.
ENCERRAMENTO_MIN = 2


def so_encerramento(palavras: list[dict]) -> tuple[bool, str]:
    """(O corte e' so' o outro do canal-fonte?, motivo)."""
    if not palavras:
        return False, "sem transcricao, nada a checar"
    txt = _limpo(" ".join((p.get("palavra") or "") for p in palavras))
    achados = [m for m in ENCERRAMENTO if m in txt]
    if len(achados) >= ENCERRAMENTO_MIN:
        return True, ("corte e' o encerramento do canal-fonte: "
                      + ", ".join(f'"{a}"' for a in achados[:4]))
    return False, "sem marca de encerramento"


def orfa(palavras: list[dict]) -> tuple[bool, str]:
    """(Abre orfao?, motivo legivel).

    Devolve o motivo porque descarte silencioso e' indistinguivel de clipe
    que nunca existiu — foi assim que os seis passaram sem ninguem notar.
    """
    if not palavras:
        return False, "sem transcricao, nada a checar"

    frase = primeira_frase(palavras)
    n = len(frase.split())
    if n and n < PALAVRAS_MIN_1A_FRASE:
        return True, (f'abre com resto da fala anterior: "{frase}" '
                      f"({n} palavra(s) antes do ponto)")

    baixo = f" {_limpo(frase)} "
    for a in ANCORAS:
        if f" {a} " in baixo:
            return True, f'abre apoiado no que veio antes: "{a}" em "{frase[:60]}"'
    for o in ORDINAIS:
        if f" {o} " in baixo:
            return True, (f'abre num ordinal que pressupoe o anterior: '
                          f'"{o}" em "{frase[:60]}"')
    return False, f'abertura sustenta sozinha: "{frase[:60]}"'
