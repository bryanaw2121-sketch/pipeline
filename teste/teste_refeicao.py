# -*- coding: utf-8 -*-
"""Teste do pareamento receita x hora de comer.

OS CASOS NEGATIVOS

O positivo — "cafe da manha vai pro slot das 8h" — passaria tambem num
algoritmo que embaralha a fila por acaso e acerta as vezes. Entao o que
prende de verdade sao os outros tres:

  nao perde clipe    `casar` devolve exatamente os mesmos itens, sem sumir
                     nem duplicar. E' o unico erro aqui que apagaria
                     trabalho ja' pago em runner.

  nao inventa ordem  sem nenhuma refeicao reconhecida, a fila sai IDENTICA a
                     que entrou. Se este falhar, a regra 1 (por video-fonte,
                     depois por posicao no original) foi quebrada sem que
                     ninguem pedisse.

  nao trava          clipe que nao casa com hora nenhuma ainda e' agendado.
                     "Se nao tiver nada, posta aleatorio mesmo" — ordem do
                     Bryan em 30/08/2026.

Roda com: python teste/teste_refeicao.py
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import refeicao

falhas = 0


def clipe(titulo):
    return (titulo, {"titulo": titulo, "legenda": titulo})


def slots(*horas):
    d = datetime.date(2026, 9, 1)
    return [datetime.datetime.combine(d, datetime.time(h, 15)) for h in horas]


def checar(cond, recado):
    global falhas
    if cond:
        print(f"  ok  {recado}")
    else:
        print(f"  FALHOU  {recado}")
        falhas += 1


# ------------------------------------------------------------- classificar
print("--- classificacao ---")
checar(refeicao.classificar("3 Tacas de Queijo Cottage para o Cafe da Manha")
       == "cafe_da_manha", "titulo que diz a refeicao e' reconhecido")
checar(refeicao.classificar("Ensopado de Carne com Tomate") == "jantar",
       "ensopado e' jantar")
checar(refeicao.classificar("Bolo Floral com Merengue") == "sobremesa",
       "bolo e' sobremesa")
checar(refeicao.classificar("Como afiar uma faca") is None,
       "video que nao e' refeicao devolve None")

# O termo MAIS LONGO vence: senao "cafe" sozinho sequestraria qualquer titulo
# que mencione cafe de passagem.
checar(refeicao.classificar("Torta doce de limao") == "sobremesa",
       "'torta doce' ganha de 'torta' (termo mais longo vence)")

# ------------------------------------------------------------------ janela
print("\n--- janela (faixa, nao hora exata) ---")
checar(refeicao.combina("Panquecas fofinhas", 8), "panqueca as 8h combina")
checar(not refeicao.combina("Panquecas fofinhas", 16),
       "panqueca as 16h NAO combina")
checar(refeicao.combina("Batata-Doce com Frango a Fajita", 12),
       "almoco as 12:xx combina (a faixa nao e' so' a hora da grade)")
checar(refeicao.combina("Ensopado de Carne", 20), "jantar as 20h combina")
checar(refeicao.combina("Como afiar uma faca", 3),
       "clipe sem refeicao combina com QUALQUER hora")

# ------------------------------------------------------------------- casar
print("\n--- pareamento ---")
grade = slots(8, 11, 16, 19)

fila = [clipe("Ensopado de Carne Suculenta"),
        clipe("Panquecas Americanas Fofinhas"),
        clipe("Marmita de Arroz, Feijao e Bife"),
        clipe("Bolo de Chocolate Molhadinho")]
saida = refeicao.casar(fila, grade)
nomes = [t for t, _ in saida]
checar(nomes[0].startswith("Panquecas"), "8h recebeu a panqueca")
checar(nomes[1].startswith("Marmita"), "11h recebeu a marmita")
checar(nomes[3].startswith("Ensopado"), "19h recebeu o ensopado")

# NEGATIVO 1 — nao perde nem duplica clipe.
checar(sorted(nomes) == sorted(t for t, _ in fila),
       "os mesmos clipes saem, sem sumir nem duplicar")

# NEGATIVO 2 — sem refeicao reconhecida, a ordem original e' preservada.
neutros = [clipe("Como afiar uma faca"), clipe("Organizando a despensa"),
           clipe("Escolhendo uma panela"), clipe("Limpando o fogao")]
checar([t for t, _ in refeicao.casar(neutros, grade)] == [t for t, _ in neutros],
       "sem refeicao nenhuma, a fila sai IDENTICA (regra 1 intacta)")

# NEGATIVO 3 — nenhum clipe casa com o slot: ninguem fica sem horario.
so_cafe = [clipe("Panquecas Fofinhas"), clipe("Ovos Mexidos Cremosos")]
saida = refeicao.casar(so_cafe, slots(19, 20))
checar(len(saida) == 2,
       "so' cafe da manha pra slots da noite: os dois saem agendados assim mesmo")

# NEGATIVO 4 — mais clipes que horarios: a sobra fica no fim, nao some.
muitos = fila + [clipe("Sopa de Legumes"), clipe("Brownie de Nozes")]
saida = refeicao.casar(muitos, slots(8, 11))
checar(len(saida) == len(muitos), "sobra de clipe nao e' descartada")

if falhas:
    print(chr(10) + f"{falhas} FALHA(S)")
    sys.exit(1)
print(chr(10) + "17 verificacoes — tudo verde")
