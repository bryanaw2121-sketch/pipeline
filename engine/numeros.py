# -*- coding: utf-8 -*-
"""Número escrito em dígito vira número por extenso, antes de ir pro TTS.

Por que existe: em 22/08/2026 o Bryan ouviu o clipe "O dia em que a IA
decidiu eliminar a humanidade" e reportou que, ao aparecer **2030**, a voz
não falava "dois mil e trinta". Nem o Chatterbox nem o edge-tts recebem
qualquer normalização de número — o texto vai cru, com o dígito, e cada
motor chuta a leitura (às vezes em inglês, às vezes dígito a dígito).

Fica em módulo separado, e não dentro de `voz_clonada`, porque existem
DOIS caminhos de TTS (`voz_clonada.gerar_trilha` e `dublagem.gerar_trilha`)
e o defeito é dos dois. Consertar só o caminho ativo deixaria a mesma falha
esperando no outro.

Ordem das substituições importa: porcentagem antes de decimal, decimal
antes de inteiro. Senão "3,5%" viraria "três vírgula cinco%" e o símbolo
sobreviveria.
"""
import re

_LANG = "pt_BR"


def _por_extenso(n: int | float) -> str:
    from num2words import num2words
    # O num2words devolve "mil, novecentos e noventa e sete" pra 1997. A
    # vírgula faz o TTS pausar no meio do ano, então sai.
    return num2words(n, lang=_LANG).replace(",", "")


# 50% / 12,5%
_PORCENTAGEM = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
# 3,5 — decimal no padrão brasileiro. Ponto NÃO entra aqui: em português o
# ponto é separador de milhar ("1.500"), tratado como inteiro mais abaixo.
_DECIMAL = re.compile(r"\b(\d+),(\d+)\b")
# 2030, 1.500, 12 — inteiro, com ou sem separador de milhar.
_INTEIRO = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d+\b")


def _decimal(m: re.Match) -> str:
    inteira, fracao = m.group(1), m.group(2)
    return f"{_por_extenso(int(inteira))} vírgula {_por_extenso(int(fracao))}"


def _porcentagem(m: re.Match) -> str:
    bruto = m.group(1).replace(".", "").replace(",", ".")
    valor = float(bruto)
    if valor.is_integer():
        return f"{_por_extenso(int(valor))} por cento"
    inteira, fracao = str(valor).split(".")
    return (f"{_por_extenso(int(inteira))} vírgula "
            f"{_por_extenso(int(fracao))} por cento")


def _inteiro(m: re.Match) -> str:
    return _por_extenso(int(m.group(0).replace(".", "")))


def por_extenso(texto: str) -> str:
    """Troca todo número em dígito pelo equivalente falado em pt-BR.

    Silencioso por opção: se o `num2words` não estiver instalado, devolve o
    texto original em vez de derrubar o run. Um clipe com um ano mal falado
    é muito melhor que um run de ~40 min perdido no fim do pipeline.
    """
    try:
        import num2words  # noqa: F401
    except ImportError:
        return texto
    texto = _PORCENTAGEM.sub(_porcentagem, texto)
    texto = _DECIMAL.sub(_decimal, texto)
    return _INTEIRO.sub(_inteiro, texto)
