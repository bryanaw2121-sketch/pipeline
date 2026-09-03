# -*- coding: utf-8 -*-
"""A unidade tem de sumir junto com o numero convertido.

⚠️ ESTE DEFEITO FOI AO AR, medido em 03/09/2026. O Bryan viu no
@cozinha.internacional um clipe cuja legenda dizia:

    "Em seguida, leve ao forno a 220°C Fahrenheit ou 220 Celsius."

O original era "bake at 425 degrees Fahrenheit or 220 Celsius". O numero
converteu certo (425F = 220C) e a palavra "Fahrenheit" ficou ORFA, colada no
valor ja' convertido — uma frase que se contradiz sozinha e repete a
temperatura duas vezes. O mesmo texto alimenta a legendA e a DUBLAGEM, entao
o erro foi visto e ouvido.

⚠️ A CAUSA ERA UM LOOKAHEAD QUE COBRIA O CASO RARO E NAO O COMUM:

    re.sub(r"(\\d+)\\s*degrees?\\b(?!\\s*c)", graus, t)

Ele evitava casar quando vinha "c" depois (Celsius, certo), mas nao dizia
nada sobre "Fahrenheit" ou "F" — que sao o jeito MAIS COMUM de dizer
temperatura em receita americana.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from engine import conversoes


def _c(texto):
    r = conversoes.converter(texto)
    return r[0] if isinstance(r, tuple) else r


# ------------------------------------------------- o caso que foi ao ar

def teste_o_caso_exato_que_foi_ao_ar():
    saida = _c("Bake at 425 degrees Fahrenheit or 220 Celsius.")
    assert "Fahrenheit" not in saida, saida
    assert "220°C" in saida, saida


def teste_degrees_F_abreviado():
    saida = _c("Bake at 425 degrees F for 12 minutes.")
    assert "220°C" in saida and " F " not in saida, saida


def teste_o_jeito_mais_comum():
    saida = _c("Preheat the oven to 350 degrees Fahrenheit.")
    assert saida.strip().endswith("180°C."), saida
    assert "ahrenheit" not in saida, saida


def teste_dois_na_mesma_frase():
    saida = _c("at 425 degrees fahrenheit, then 350 degrees F")
    assert "220°C" in saida and "180°C" in saida, saida
    assert "ahrenheit" not in saida.lower(), saida


def teste_limpa_o_que_ja_esta_sujo_no_acervo():
    """Clipes cortados antes do conserto tem o texto ja' gravado."""
    assert _c("leve ao forno a 220°C Fahrenheit").endswith("220°C")


# ------------------------------------------------- os negativos

def teste_negativo_celsius_NAO_pode_ser_reconvertido():
    """⚠️ O RISCO DO CONSERTO. Se o lookahead de Celsius fosse perdido,
    "220 degrees Celsius" viraria 104°C — trocaria um erro VISIVEL por um
    silencioso, que e' muito pior: ninguem ve' um forno a 104 graus."""
    # ⚠️ O QUE IMPORTA E' O VALOR, NAO A GRAFIA. Ate' 03/09/2026 este teste
    # exigia o texto literalmente intacto — e reprovou quando "220 degrees
    # Celsius" passou a virar "220°C" de proposito, pra fala dizer "220 graus".
    # Aquilo era detalhe de implementacao; o perigo real e' 220 virar 104.
    saida = _c("cook at 220 degrees Celsius")
    assert "220" in saida and "104" not in saida, saida
    saida = _c("preheat to 180 degrees centigrade")
    assert "180" in saida and "82" not in saida, saida


def teste_negativo_degrees_sem_unidade_CONTINUA_convertendo():
    """Isso ja' funcionava e nao pode quebrar: "bake at 375 degrees" e' como
    a pessoa fala, e sem esta regra forno nenhum convertia na dublagem."""
    assert "190°C" in _c("bake at 375 degrees")


def teste_negativo_peso_e_volume_intactos():
    assert "115 g" in _c("a 4 ounce scoop works well")


def teste_negativo_temperatura_baixa_nao_e_forno():
    """Abaixo de 250 os dois sistemas se sobrepoem e nao da' pra saber qual e'
    — a regra original deixa quieto, e isso tem de continuar."""
    saida = _c("let it rest at 70 degrees")
    assert "°C" not in saida, saida


# ------------------------------------------------- fala: "220 graus", so'

def _fala(texto):
    from engine import numeros
    return numeros.por_extenso(_c(texto))


def teste_celsius_por_extenso_vira_graus_na_fala():
    """Pedido do Bryan em 03/09/2026: "quando for falar 220C falar 220 graus
    apenas". O simbolo °C ja' virava "graus", mas a PALAVRA "Celsius" nao
    passava pela tabela de fala e era dublada como estava escrita."""
    assert "Celsius" not in _fala("leve ao forno a 220 Celsius")
    assert "duzentos e vinte graus" in _fala("leve ao forno a 220 Celsius")
    assert "cento e oitenta graus" in _fala("asse a 180 graus Celsius")


def teste_a_temperatura_nao_e_dita_DUAS_vezes():
    """Receita americana fala as duas unidades; depois de converter, viram o
    mesmo valor e a dublagem repetia."""
    f = _fala("Bake at 425 degrees Fahrenheit or 220 Celsius.")
    assert f.count("duzentos e vinte graus") == 1, f


def teste_negativo_valores_DIFERENTES_nao_colapsam():
    """⚠️ TEOREMATICO. Colapsar por proximidade apagaria um passo da receita:
    "doure a 220°C e termine a 180°C" sao duas temperaturas de verdade."""
    saida = _c("doure a 425 degrees F e termine a 350 degrees F")
    assert "220°C" in saida and "180°C" in saida, saida


if __name__ == "__main__":
    n = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("teste_") and callable(fn):
            fn(); n += 1; print(f"  ok  {nome}")
    print(f"{n} testes verdes")
