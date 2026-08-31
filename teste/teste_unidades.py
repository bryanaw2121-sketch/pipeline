# -*- coding: utf-8 -*-
"""Unidade de medida falada do jeito que brasileiro fala.

POR QUE EXISTE

Pedido do Bryan em 31/08/2026: "quando for falar mililitros pode falar ML,
'eme ele' transliterado". Ate' entao o `numeros.py` convertia numero e
ignorava unidade — "200 ml" ia pro TTS com o "ml" cru, e cada motor chutava
("mil", ou soletrando errado). Num canal de receita isso aparece o tempo todo.

⚠️ A LEITURA NAO E' UNIFORME. Quem fala "duzentos eme ele" fala "duzentos
GRAMAS", nao "duzentos ge". Cada unidade tem a sua convencao, e por isso a
tabela e' escrita a mao em vez de derivada.

⚠️ ORDEM IMPORTA: a unidade e' trocada ANTES do numero. Depois que "200" vira
"duzentos", o padrao `\\d+\\s*ml` nao casa mais e a unidade fica orfa — que e'
exatamente o defeito original.

O CASO NEGATIVO: unidade sem numero na frente nao pode ser tocada. "g" e "L"
sao letras comuns; so' viram medida quando ha' um numero antes. Sem essa
ancora, qualquer "g" do texto viraria "gramas" no meio de uma frase.

Roda com: python teste/teste_unidades.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from engine import numeros  # noqa: E402

falhas = []


def checar(entra, contem, msg, nao_contem=None):
    saiu = numeros.por_extenso(entra)
    ok = contem in saiu and (nao_contem is None or nao_contem not in saiu)
    print(("  ok    " if ok else "  FALHA ") + msg)
    if not ok:
        print(f"          entrou: {entra}")
        print(f"          saiu:   {saiu}")
        falhas.append(msg)


print(__doc__.splitlines()[0])

print("\n[1] o pedido: mililitro se fala 'eme ele'")
checar("Use 200 ml de creme", "duzentos eme ele", "200 ml -> duzentos eme ele")
checar("Adicione 500ml de leite", "quinhentos eme ele", "sem espaco tambem")
checar("Junte 250 mL agora", "duzentos e cinquenta eme ele", "mL maiusculo")

print("\n[2] cada unidade com a SUA convencao, nao uma regra so'")
checar("250 g de manteiga", "duzentos e cinquenta gramas", "g -> gramas")
checar("1,5 kg de batata", "quilos", "kg -> quilos")
checar("2 L de agua", "dois litros", "L -> litros")
checar("12 cm de largura", "doze centimetros", "cm -> centimetros")
checar("3 nm no chip", "três nanometros", "nm -> nanometros")

print("\n[3] kg nao pode ser lido como 'k' + 'gramas'")
saiu = numeros.por_extenso("1 kg")
checar("1 kg", "quilos", "kg inteiro vira quilos", nao_contem="gramas")

print("\n[4] temperatura")
checar("Asse a 180°C", "cento e oitenta graus", "180°C -> graus")
checar("Nos EUA 350°F", "graus fahrenheit", "350°F -> graus fahrenheit")

print("\n[5] o CASO NEGATIVO: sem numero na frente, nao mexe")
for texto in ("uma pitada de sal, g de nada",
              "a letra L do alfabeto",
              "ml sozinho no meio da frase",
              "kg escrito sem medida"):
    saiu = numeros.por_extenso(texto)
    ok = saiu == texto
    print(("  ok    " if ok else "  FALHA ") + f"intacto: {texto[:38]}")
    if not ok:
        print(f"          virou: {saiu}")
        falhas.append(texto)

print("\n[6] o que ja' funcionava continua")
checar("Em 2030 a IA muda", "dois mil e trinta", "ano continua por extenso")
checar("com 50% de chance", "cinquenta por cento", "porcentagem continua")
checar("são 3,5 vezes", "três vírgula cinco", "decimal continua")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("tudo verde")
