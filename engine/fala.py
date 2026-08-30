# -*- coding: utf-8 -*-
"""Guarda contra clipe MUDO — vídeo sem fala nunca deveria virar corte.

POR QUE EXISTE

Em 29/08/2026 o Bryan rejeitou uma leva inteira de sete clipes de usinagem
CNC. O motivo que ele deu: **"são clipes sem fala"**.

O problema não foram os sete arquivos. Foi a nota que o motor deu a eles:

    nota 96  Fabricacao e Teste de Helice de Ventilador  <- a MAIOR do lote
    nota 93  Revelando a Cavidade do Molde
    nota 90  Usinagem CNC de Alta Precisao
    nota 88, 86, 84, 82  os outros quatro

O clipe mais bem avaliado do lote inteiro não tem uma palavra falada. O
`selecao.py` pontua por gancho, progresso e clímax — todos conceitos de FALA —
mas nada no caminho verifica que existe fala para começo de conversa. Imagem
bonita de máquina operando passa como se fosse um argumento bem construído.

Sem esta guarda, qualquer fonte silenciosa volta a entrar, e volta com nota
alta. O canal irmão (Cozinha Internacional) já tinha aprendido isso pelo lado
das fontes — descartou os três maiores canais de comida do radar por serem
silenciosos, "nada pra transcrever, traduzir ou dublar". Aqui a lição chega
pelo lado do clipe.

POR QUE DENSIDADE, E NÃO CONTAGEM

Contar palavras não serve: um clipe de 110s com 12 palavras tem "fala", mas é
uma legenda ocasional sobre imagem muda. O que separa narração de ruído é
quantas palavras por segundo o trecho sustenta.

O piso é deliberadamente BAIXO. Ele não existe pra julgar ritmo — existe pra
pegar o mudo. Fala normal de vídeo desse tipo fica entre 2 e 3,5 palavras/s
(120-210 palavras/min, e o `main.py` já avisa acima de 200). Meio segundo de
palavra por segundo é um quinto do piso da fala natural: qualquer coisa que
seja narração de verdade passa folgado, e só passa raspando quem é mudo.
"""
from __future__ import annotations

# Palavras por segundo abaixo disso = clipe mudo, descartado.
#
# Calibragem: fala natural sustenta 2,0-3,5 p/s. Este piso é ~1/4 disso, então
# a margem contra falso positivo é enorme. Se algum dia um clipe legítimo for
# descartado por aqui, o número está alto demais — mas o caso que motivou a
# guarda tinha densidade ZERO, não 0,4.
DENSIDADE_MIN = 0.5

# Piso absoluto de palavras. Protege o caso degenerado do clipe curtíssimo em
# que 2 palavras soltas já bateriam a densidade.
PALAVRAS_MIN = 10


def densidade(palavras: list[dict], duracao_s: float) -> float:
    """Palavras por segundo. Zero se não der pra calcular."""
    if not palavras or duracao_s <= 0:
        return 0.0
    return len(palavras) / duracao_s


def mudo(palavras: list[dict], duracao_s: float) -> tuple[bool, str]:
    """(É mudo?, motivo legível).

    Devolve o motivo junto porque quem descarta precisa DIZER por quê — um
    descarte silencioso é indistinguível de um clipe que nunca existiu, e foi
    exatamente assim que os sete CNC chegaram até a fila sem ninguém notar.
    """
    n = len(palavras or [])
    d = densidade(palavras, duracao_s)

    if n == 0:
        return True, "nenhuma palavra transcrita — vídeo sem fala"
    if n < PALAVRAS_MIN:
        return True, (f"só {n} palavra(s) em {duracao_s:.0f}s — "
                      f"mínimo é {PALAVRAS_MIN}")
    if d < DENSIDADE_MIN:
        return True, (f"densidade de fala {d:.2f} palavra/s em {duracao_s:.0f}s "
                      f"(mínimo {DENSIDADE_MIN}) — imagem com fala esparsa")
    return False, f"densidade de fala {d:.2f} palavra/s, ok"
