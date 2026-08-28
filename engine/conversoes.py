# -*- coding: utf-8 -*-
"""Medida americana vira medida brasileira, antes de virar fala.

POR QUE EXISTE
E' o diferencial do canal. Receita americana vem em cup, oz e F; o brasileiro
cozinha em grama, ml e C. Converter e' o produto, nao um detalhe.

A ARMADILHA CENTRAL
"1 cup" NAO tem valor fixo em gramas — depende da densidade do ingrediente:

    1 cup de farinha = 120 g      1 cup de acucar = 200 g
    1 cup de mel     = 340 g

Quase o triplo entre o mais leve e o mais pesado. Por isso a tabela e' POR
INGREDIENTE. Ingrediente desconhecido cai pra **ml**, que e' conversao exata de
volume e vale pra qualquer coisa. Chutar grama quebra a receita, e a confianca e'
o unico ativo deste canal.

ORDEM NO PIPELINE
Roda ANTES de `engine/numeros.py`. O numeros.py transforma digito em palavra pro
TTS ("180" -> "cento e oitenta"), entao se a conversao rodar depois, o valor
convertido chega no TTS como digito e a voz chuta a leitura.
"""
from __future__ import annotations

import re
import unicodedata

ML_POR_CUP = 240.0

# gramas em 1 cup. Arredondado de proposito: receita nao usa decimal, e numero
# redondo le' melhor na tela.
DENSIDADE = {
    "agua": 240, "leite": 240, "caldo": 240, "suco": 240,
    "farinha de trigo": 120, "farinha": 120, "farinha integral": 130,
    "farinha de amendoa": 96, "amido de milho": 120,
    "acucar": 200, "acucar mascavo": 220, "acucar de confeiteiro": 120,
    "mel": 340, "melado": 340, "xarope": 340,
    "manteiga": 227, "oleo": 218, "azeite": 216,
    "creme de leite": 240, "iogurte": 245,
    "arroz": 185, "aveia": 90, "farinha de rosca": 108,
    "cacau em po": 85, "chocolate": 175,
    "queijo ralado": 100, "castanhas": 120, "nozes": 117,
    "sal": 273, "sal grosso": 220,
}

# ingrediente em ingles -> (nome em portugues, chave da densidade)
GLOSSARIO = {
    "all-purpose flour": ("farinha de trigo", "farinha de trigo"),
    "flour": ("farinha de trigo", "farinha de trigo"),
    "whole wheat flour": ("farinha integral", "farinha integral"),
    "almond flour": ("farinha de amendoa", "farinha de amendoa"),
    "cornstarch": ("amido de milho", "amido de milho"),
    "sugar": ("acucar", "acucar"),
    "granulated sugar": ("acucar", "acucar"),
    "brown sugar": ("acucar mascavo", "acucar mascavo"),
    "powdered sugar": ("acucar de confeiteiro", "acucar de confeiteiro"),
    "confectioners sugar": ("acucar de confeiteiro", "acucar de confeiteiro"),
    "honey": ("mel", "mel"),
    "maple syrup": ("xarope de bordo", "xarope"),
    "butter": ("manteiga", "manteiga"),
    "oil": ("oleo", "oleo"),
    "olive oil": ("azeite", "azeite"),
    "milk": ("leite", "leite"),
    "water": ("agua", "agua"),
    "heavy cream": ("creme de leite fresco", "creme de leite"),
    "cream": ("creme de leite", "creme de leite"),
    "yogurt": ("iogurte", "iogurte"),
    "rice": ("arroz", "arroz"),
    "rolled oats": ("aveia em flocos", "aveia"),
    "oats": ("aveia", "aveia"),
    "breadcrumbs": ("farinha de rosca", "farinha de rosca"),
    "cocoa powder": ("cacau em po", "cacau em po"),
    "chocolate chips": ("gotas de chocolate", "chocolate"),
    "grated cheese": ("queijo ralado", "queijo ralado"),
    "walnuts": ("nozes", "nozes"),
    "salt": ("sal", "sal"),
    "broth": ("caldo", "caldo"), "stock": ("caldo", "caldo"),
}

# termos que traducao literal estraga — sem medida associada
TERMOS = {
    "baking soda": "bicarbonato de sodio",
    "baking powder": "fermento quimico em po",
    "buttermilk": "leite fermentado",
    "half-and-half": "metade leite, metade creme",
    "shortening": "gordura vegetal",
    "to fold": "incorporar delicadamente",
    "broil": "gratinar",
    "mirin": "mirin (vinho doce de arroz)",
    "dashi": "dashi (caldo de peixe e alga)",
    "creme fraiche": "creme de leite azedo",
    "roux": "roux (farinha tostada na manteiga)",
    "passata": "molho de tomate peneirado",
    "guanciale": "guanciale (papada suina)",
}

FRACOES = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1/3, "⅔": 2/3, "⅛": 0.125}


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def _num(txt: str) -> float | None:
    txt = txt.strip()
    if txt in FRACOES:
        return FRACOES[txt]
    m = re.fullmatch(r"(\d+)\s*([½¼¾⅓⅔⅛])", txt)
    if m:
        return int(m.group(1)) + FRACOES[m.group(2)]
    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", txt)
    if m:
        return int(m.group(1)) / int(m.group(2))
    try:
        return float(txt.replace(",", "."))
    except ValueError:
        return None


def _bonito(v: float) -> str:
    """Numero pra tela: sem decimal inutil, arredondado ao util."""
    if v >= 100:
        v = round(v / 5) * 5
    elif v >= 10:
        v = round(v)
    else:
        return f"{v:.1f}".replace(".0", "").replace(".", ",")
    return str(int(v))


def _ingrediente(resto: str) -> tuple[str | None, str | None, str]:
    """Acha o ingrediente logo depois da medida.

    Devolve tambem o TEXTO QUE SOBROU. Sem isso o " and " que vem depois do
    ingrediente era engolido pela captura, e duas medidas na mesma frase
    grudavam: "240 g de farinha de trigo200 g de acucar".

    Casa o nome MAIS LONGO primeiro: 'brown sugar' antes de 'sugar', senao
    vira acucar comum.
    """
    bruto = resto
    r = _sem_acento(resto.lower()).lstrip()
    corte = len(resto) - len(r)
    m = re.match(r"(of|de|da|do)\s+", r)
    if m:
        r = r[m.end():]; corte += m.end()
    for en in sorted(GLOSSARIO, key=len, reverse=True):
        if r.startswith(en):
            nome, chave = GLOSSARIO[en]
            return nome, chave, bruto[corte + len(en):]
    return None, None, bruto


def converter(texto: str) -> tuple[str, list[str]]:
    """Devolve (texto convertido, lista de conversoes pra mostrar na tela)."""
    achados: list[str] = []

    def volume(m):
        qtd = _num(m.group(1))
        if qtd is None:
            return m.group(0)
        unidade = m.group(2).lower()
        nome, chave, sobra = _ingrediente(m.group(3) or "")
        rotulo = f"de {nome}" if nome else ""
        if unidade.startswith(("tbsp", "tablespoon", "tsp", "teaspoon")):
            # Colher NAO vira grama. A colher de sopa brasileira e' ~15 ml e a
            # de cha' ~5 ml, entao a traducao e' direta e e' como a pessoa
            # realmente mede. "5,7 g de sal" nao ajuda ninguem na cozinha.
            colher = "sopa" if unidade.startswith(("tbsp", "tablespoon")) else "cha"
            n_ = _bonito(qtd)
            plural = "colheres" if qtd > 1 else "colher"
            saida = f"{n_} {plural} de {colher}"
            achados.append(f"{m.group(1).strip()} {unidade} = {saida}")
            return f"{saida} {rotulo}".strip() + " " + sobra.lstrip()
        ml = qtd * ML_POR_CUP
        if chave and chave in DENSIDADE:
            saida = f"{_bonito(qtd * DENSIDADE[chave])} g"
        else:
            # FALLBACK HONESTO: ingrediente desconhecido -> ml, nunca chutar grama
            saida = f"{_bonito(ml)} ml"
        achados.append(f"{m.group(1).strip()} {unidade} = {saida}")
        return f"{saida} {rotulo}".strip() + " " + sobra.lstrip()

    t = re.sub(r"(\d+\s*[½¼¾⅓⅔⅛]|[½¼¾⅓⅔⅛]|\d+\s*/\s*\d+|\d+(?:[.,]\d+)?)\s*"
               r"(cups?|tbsp|tablespoons?|tsp|teaspoons?)\b\s*"
               r"((?:of\s+)?[a-zA-Z\- ]{0,25})", volume, texto, flags=re.I)

    def temperatura(m):
        # Forno se arredonda a 10, nao a 5: 350F da' 176,7 e a convencao
        # brasileira e' 180. Arredondar a 5 dava 175, que contradizia ate' a
        # bio do canal ("350F e' 180C"). Abaixo de 100 mantem precisao.
        f = _num(m.group(1))
        c = (f - 32) / 1.8
        c = round(c / 10) * 10 if c >= 100 else round(c)
        achados.append(f"{int(f)}°F = {int(c)}°C")
        return f"{int(c)}°C"
    t = re.sub(r"(\d+)\s*°?\s*F\b", temperatura, t)

    def peso(m):
        q = _num(m.group(1)); u = m.group(2).lower()
        g = q * (453.6 if u.startswith("lb") or u.startswith("pound") else 28.35)
        achados.append(f"{m.group(1)} {u} = {_bonito(g)} g")
        return f"{_bonito(g)} g"
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*(oz|ounces?|lbs?|pounds?)\b", peso, t, flags=re.I)

    # Forma/assadeira em polegadas: "9 by 13 pan" -> "23 por 33 cm". Vem ANTES
    # da polegada solta, porque "9 by 13" tem dois numeros e a regra simples
    # converteria so' o primeiro. Sem isto o Gemini improvisava a conversao e
    # errava: disse "20 por 30" onde o certo e' 23x33.
    def forma(m):
        a = _num(m.group(1)); b = _num(m.group(2))
        ca, cb = round(a * 2.54), round(b * 2.54)
        achados.append(f"forma {m.group(1)}x{m.group(2)} pol = {ca}x{cb} cm")
        return f"{ca} por {cb} cm "
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:x|by|por)\s*(\d+(?:[.,]\d+)?)\s*"
               r"(?:-?\s*inch(?:es)?)?\s*(?=pan|dish|baking|forma|assadeira|tin)",
               forma, t, flags=re.I)

    def polegada(m):
        v_ = _num(m.group(1))
        cm = v_ * 2.54
        achados.append(f"{m.group(1)} pol = {_bonito(cm)} cm")
        return f"{_bonito(cm)} cm"
    t = re.sub(r"(\d+\s*/\s*\d+|\d+(?:[.,]\d+)?|[½¼¾])\s*(?:-\s*)?inch(?:es)?", polegada, t, flags=re.I)

    def stick(m):
        q = _num(m.group(1)) or 1
        achados.append(f"{m.group(1)} stick(s) de manteiga = {_bonito(q*113)} g")
        return f"{_bonito(q*113)} g de manteiga"
    t = re.sub(r"(\d+(?:\s*[½¼¾])?)\s*sticks?\s+of\s+butter", stick, t, flags=re.I)

    for en, pt in sorted(TERMOS.items(), key=lambda x: -len(x[0])):
        t = re.sub(re.escape(en), pt, t, flags=re.I)
    # A remontagem deixa espaco sobrando: espaco duplo, e espaco antes de
    # pontuacao. Passa na legenda, mas o TTS respira nesse espaco e a fala
    # sai truncada — e o Bryan pediu que dubagem e legenda ficassem redondas.
    t = re.sub(r"[ 	]{2,}", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return t.strip(), achados


# ---------------------------------------------------------------- fala x tela
# A legenda quer "240 g"; a boca quer "duzentos e quarenta gramas". Sao dois
# textos diferentes a partir da mesma conversao.
#
# Sem isto o TTS le' a abreviacao como letra — "240 g" sai "duzentos e quarenta
# ge'", e "180 C" sai "cento e oitenta ce'". O `engine/numeros.py` resolve o
# digito, mas nao sabe nada de unidade.
#
# ORDEM: converter() -> para_fala() -> numeros.py -> TTS.
# Concordancia antes de tudo: o numeros.py troca "1" por "um" sem olhar o
# genero do substantivo, e "um colher de cha" e' erro de portugues saindo
# pela boca do narrador. O Bryan pediu a dubagem redonda; isto e' parte.
FEMININAS = ['colher', 'colheres', 'xicara', 'xicaras', 'xícara', 'xícaras', 'pitada', 'pitadas', 'lata', 'latas', 'fatia', 'fatias']

UNIDADES_FALADAS = [
    (r"\b1 (?=(?:colher|colheres|xicara|xicaras|xícara|xícaras|pitada|pitadas|lata|latas|fatia|fatias)\b)", "uma "),
    (r"\b2 (?=(?:colher|colheres|xicara|xicaras|xícara|xícaras|pitada|pitadas|lata|latas|fatia|fatias)\b)", "duas "),
    (r"(\d)\s*°\s*C\b", r"\1 graus"),
    (r"(\d)\s*°\s*F\b", r"\1 graus Fahrenheit"),
    (r"(\d)\s*ml\b", r"\1 mililitros"),
    (r"(\d)\s*kg\b", r"\1 quilos"),
    (r"\b1\s*g\b", r"1 grama"),
    (r"(\d)\s*g\b", r"\1 gramas"),
    (r"\b1\s*cm\b", r"1 centimetro"),
    (r"(\d)\s*cm\b", r"\1 centimetros"),
    (r"\b1\s*min\b", r"1 minuto"),
    (r"(\d)\s*min\b", r"\1 minutos"),
]


def para_fala(texto: str) -> str:
    """Expande unidade abreviada em palavra, pro TTS nao soletrar.

    Roda DEPOIS de converter() e ANTES de numeros.py. A ordem importa: se
    numeros.py rodar antes, "240" ja' virou "duzentos e quarenta" e o digito
    nao casa mais com nada.
    """
    t = texto
    for padrao, troca in UNIDADES_FALADAS:
        t = re.sub(padrao, troca, t)
    return t
