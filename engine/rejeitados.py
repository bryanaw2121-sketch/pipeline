# -*- coding: utf-8 -*-
"""Clipes que o Bryan APAGOU da fila — nunca reagendar.

POR QUE EXISTE
Apagar um post AGENDADO no Buffer não deixa rastro: ele some da consulta de
`scheduled` e nunca aparece em `sent`. Pro agendador, o clipe volta a parecer
"disponível" — e ele reagenda. Em 26/08/2026 eu empurrei o mesmo clipe
("666 MILHOES de Transistores") três vezes, depois de o Bryan apagar as duas
primeiras.

Apagar da fila é uma DECISÃO EDITORIAL dele: "não quero esse vídeo". O
manifesto não tem como saber disso sozinho, então a decisão mora aqui.

Isso é diferente de republicação (`republicacao=true` no manifesto), que é o
caso oposto: clipe que ele apagou do TIKTOK justamente pra sair de novo.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "estado" / "rejeitados.json"


def _ler() -> dict:
    if ARQ.exists():
        try:
            return json.loads(ARQ.read_text(encoding="utf-8"))
        except Exception:
            print(f"[!] {ARQ.name} ilegível, tratando como vazio.")
    return {}


def chaves() -> set[str]:
    return set(_ler().keys())


def marcar(chave: str, titulo: str = "", motivo: str = "apagado da fila pelo Bryan") -> None:
    d = _ler()
    if chave in d:
        return
    d[chave] = {"titulo": titulo[:80], "motivo": motivo}
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def rejeitado(chave: str) -> bool:
    return chave in _ler()


def resumo() -> str:
    d = _ler()
    return f"{len(d)} clipe(s) rejeitado(s) — nunca reagendar"
