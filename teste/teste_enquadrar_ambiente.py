# -*- coding: utf-8 -*-
"""Teste da guarda de ambiente do face tracking.

O CASO NEGATIVO

A guarda que so' RECUSA reprova em producao: se ela derrubasse o run tambem
quando o rastreio esta' funcionando, ninguem publicaria nada. E a que so'
ACEITA nao e' guarda nenhuma — era exatamente o estado ate' 30/08/2026, um
`[!]` no log e o run verde.

Entao os dois lados sao verificados:

  positivo  na nuvem, biblioteca faltando   -> DERRUBA, e o recado diz o que fazer
  negativo  na nuvem, biblioteca presente   -> nao derruba nada
            local, biblioteca faltando      -> avisa e segue (dev sem mediapipe)
            desligada de proposito          -> avisa e segue

Roda com: python teste/teste_enquadrar_ambiente.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import enquadrar

ERRO = OSError("libEGL.so.1: cannot open shared object file: No such file or directory")

falhas = 0


def ambiente(**kv):
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def caso(nome, esperado_derruba, **env):
    global falhas
    ambiente(GITHUB_ACTIONS=None, RASTREIO_OBRIGATORIO=None)
    ambiente(**env)
    derrubou, recado = False, ""
    try:
        r = enquadrar.sem_biblioteca(ERRO)
        if r != []:
            print(f"  FALHOU {nome}: devolveu {r!r} em vez de lista vazia")
            falhas += 1
    except RuntimeError as e:
        derrubou, recado = True, str(e)

    if derrubou != esperado_derruba:
        virou = "derrubou" if derrubou else "seguiu"
        queria = "derrubar" if esperado_derruba else "seguir"
        print(f"  FALHOU {nome}: {virou}, mas era pra {queria}")
        falhas += 1
        return

    # Derrubar sem dizer o conserto e' quase tao ruim quanto nao derrubar:
    # quem le o log as 3h da manha precisa do nome do pacote ali.
    if derrubou:
        for pedaco in ("libegl1", "AMBIENTE", "RASTREIO_OBRIGATORIO"):
            if pedaco.lower() not in recado.lower():
                print(f"  FALHOU {nome}: o recado nao menciona {pedaco!r}")
                falhas += 1
                return

    print(f"  ok  [{'derruba' if derrubou else ' segue ':>7}]  {nome}")


# POSITIVO — o caso que aconteceu de verdade nos runs #185 e #14.
caso("nuvem, biblioteca faltando", True, GITHUB_ACTIONS="true")

# NEGATIVOS — a guarda tem que ficar QUIETA aqui.
caso("maquina local, sem mediapipe", False)
caso("nuvem, mas desligada de proposito", False,
     GITHUB_ACTIONS="true", RASTREIO_OBRIGATORIO="0")
caso("GITHUB_ACTIONS com outro valor", False, GITHUB_ACTIONS="false")
caso("local, obrigatoriedade ligada a mao", True, RASTREIO_OBRIGATORIO="1")

# O caso que prova que a guarda nao e' cega: com a biblioteca PRESENTE ela
# nunca e' chamada. Aqui isso vira verificacao de que nada no import de
# `enquadrar` derruba por conta propria dentro da nuvem.
ambiente(GITHUB_ACTIONS="true", RASTREIO_OBRIGATORIO=None)
try:
    import importlib
    importlib.reload(enquadrar)
    print("  ok  [ segue ]  importar o modulo na nuvem nao derruba nada")
except Exception as e:
    print(f"  FALHOU: importar enquadrar na nuvem derrubou ({e})")
    falhas += 1

ambiente(GITHUB_ACTIONS=None, RASTREIO_OBRIGATORIO=None)

if falhas:
    print(chr(10) + f"{falhas} FALHA(S)")
    sys.exit(1)
print(chr(10) + "6 casos — tudo verde")
