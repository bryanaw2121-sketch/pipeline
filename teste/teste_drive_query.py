# -*- coding: utf-8 -*-
"""Teste da guarda de aspas na consulta do Drive.

O CASO NEGATIVO E' O QUE IMPORTA

Um teste que so' verifica "S'mores agora funciona" passaria tambem numa
funcao que devolve o texto sem tocar em nada — porque a consulta MONTADA
continuaria quebrada e ninguem veria. Entao cada caso aqui tem dois lados:

  positivo — com a guarda, a consulta fica com aspas balanceadas
  negativo — SEM a guarda, a mesma consulta fica desbalanceada

Se um dia alguem transformar `aspas()` em identidade, o lado negativo passa a
falhar imediatamente. E' o que reprovou em 30/08/2026 nos testes que "passaram
pelo motivo errado".

Roda com: python teste/teste_drive_query.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.drive_query import aspas

BARRA = chr(92)
APOS = chr(39)


def monta(nome, pasta="PASTA123"):
    """A consulta exatamente como o subir_cortes_drive.py a monta."""
    return (f"name={APOS}{nome}{APOS} and {APOS}{pasta}{APOS} in parents "
            "and trashed=false")


def balanceada(q):
    """Conta apostrofos que NAO estao escapados.

    Consulta valida do Drive tem numero PAR deles: cada string abre e fecha.
    Impar significa que uma string ficou aberta — foi o 400 'Invalid Value'.
    """
    soltos = 0
    i = 0
    while i < len(q):
        if q[i] == BARRA:
            i += 2
            continue
        if q[i] == APOS:
            soltos += 1
        i += 1
    return soltos % 2 == 0


CASOS = [
    # (nome do arquivo, quebra sem a guarda?)
    ("04_nota88_Bolo Floral Degrade e Bolo S" + APOS + "mores com Merengu.mp4", True),
    ("Shepherd" + APOS + "s Pie com Pure Rustico.mp4", True),
    ("Hershey" + APOS + "s: o chocolate que virou padrao.mp4", True),
    ("Bolo de Cenoura com Cobertura.mp4", False),
    ("03_nota90_Como fazer rosas vermelhas.mp4", False),
]

falhas = 0

for nome, quebrava in CASOS:
    antes = falhas
    com = monta(aspas(nome))
    sem = monta(nome)

    # POSITIVO: com a guarda, sempre balanceada.
    if not balanceada(com):
        print(f"  FALHOU positivo: {nome[:45]!r} continua quebrando com a guarda")
        falhas += 1

    # NEGATIVO: sem a guarda, tem que quebrar exatamente onde esperamos.
    if balanceada(sem) != (not quebrava):
        estado = "quebrou" if not balanceada(sem) else "passou"
        esperado = "quebrar" if quebrava else "passar"
        print(f"  FALHOU negativo: {nome[:45]!r} {estado} sem a guarda, "
              f"mas era pra {esperado}")
        falhas += 1

    if falhas == antes:
        marca = "quebrava" if quebrava else "ja' passava"
        print(f"  ok  [{marca:>11}]  {nome[:52]}")

# A barra invertida tem que ser escapada ANTES do apostrofo, senao a barra
# que a propria funcao insere seria escapada de novo e sobraria uma solta.
if aspas(BARRA) != BARRA + BARRA:
    print("  FALHOU: barra invertida nao foi duplicada")
    falhas += 1
ordem_antes = falhas
if aspas(BARRA + APOS) != BARRA + BARRA + BARRA + APOS:
    print("  FALHOU: ordem errada — apostrofo escapado antes da barra")
    falhas += 1
if falhas == ordem_antes:
    print("  ok  [      ordem]  barra invertida antes do apostrofo")

# A guarda nao pode mexer em nome limpo: renomear arquivo em massa por causa
# de escape seria pior que o defeito.
limpo = "Bolo de Cenoura.mp4"
if aspas(limpo) != limpo:
    print("  FALHOU: nome sem caractere especial foi alterado")
    falhas += 1
else:
    print("  ok  [   intocado]  nome limpo passa identico")

if falhas:
    print(chr(10) + f"{falhas} FALHA(S)")
    sys.exit(1)
print(chr(10) + f"{len(CASOS)} nome(s) + 3 invariantes — tudo verde")
