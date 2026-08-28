# -*- coding: utf-8 -*-
"""Clipes que o Bryan quer deixar pro FIM da fila — mas nao descartar.

POR QUE EXISTE, e por que nao e' o `rejeitados.py`
`rejeitados` significa "nunca mais reagendar": decisao editorial definitiva.
Em 27/08/2026 o Bryan pediu outra coisa para tres clipes — *"vamos deixar eles
para os ultimos dos ultimos"*. Nao e' descarte: e' prioridade minima. Marcar
como rejeitado perderia o clipe pra sempre; nao marcar nada o traz de volta na
proxima rodada, porque apagar post agendado no Buffer nao deixa rastro.

COMO AGE
`ordenar()` poe o adiado atras de TODO mundo, inclusive das republicacoes.
O clipe continua no manifesto e continua elegivel — so' que por ultimo. Com
dezenas de clipes esperando vaga, na pratica ele so' aparece quando a
prateleira esvaziar, e sai da lista na hora que o Bryan quiser.

A chave e' a mesma de `agendar_buffer._chave_texto`, calculada sobre a
LEGENDA (com o titulo como reserva) — que e' o que o `cabe()` compara. Calcular
sobre o titulo NAO serve: foi assim que eu deixei tres clipes passarem pro
agendamento em 27/08 depois de o Bryan dizer que nao os queria.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "estado" / "adiados.json"


def _ler() -> dict:
    if ARQ.exists():
        try:
            return json.loads(ARQ.read_text(encoding="utf-8"))
        except Exception:
            print(f"[!] {ARQ.name} ilegivel, tratando como vazio.")
    return {}


def chaves() -> set[str]:
    return set(_ler().keys())


def adiado(chave: str) -> bool:
    return chave in _ler()


def marcar(chave: str, titulo: str = "", motivo: str = "adiado pelo Bryan") -> bool:
    d = _ler()
    if chave in d:
        return False
    d[chave] = {"titulo": titulo[:80], "motivo": motivo}
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def desmarcar(chave: str) -> bool:
    """Devolve o clipe a' ordem normal."""
    d = _ler()
    if chave not in d:
        return False
    d.pop(chave)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def resumo() -> str:
    return f"{len(_ler())} clipe(s) adiado(s) — vao pro fim da fila"
