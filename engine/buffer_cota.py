# -*- coding: utf-8 -*-
"""Orçamento de requisições da API do Buffer — guarda contra estourar a conta.

POR QUE EXISTE
Em 25/08/2026 a API do Buffer devolveu `RATE_LIMIT_EXCEEDED` com janela de 24h,
e o canal ficou sem poder ser reorganizado. A causa foi minha, e foram três
coisas somadas:

  1. um monitor consultando a API de 5 em 5 minutos (~288 chamadas/dia);
  2. a consulta de fila PAGINA sobre o histórico inteiro (68 posts na época),
     então cada "consulta" custava várias requisições;
  3. reorganizações repetidas da fila no mesmo dia, cada uma relendo tudo.

Nada disso era necessário. A fila muda no máximo 4 vezes por dia (é a cadência
de postagem), então consultar de 5 em 5 minutos era 60x mais do que o problema
pedia.

COMO ESTE MÓDULO RESOLVE

  - **Orçamento**: conta as requisições numa janela de 24h e RECUSA passar do
    teto. Melhor a fila ficar desatualizada por algumas horas do que a conta
    inteira travar por um dia.
  - **Cache**: estado da fila lido no máximo uma vez a cada `IDADE_CACHE_S`.
    Chamada seguinte dentro da janela reaproveita, sem tocar na rede.

O teto é conservador de propósito. O limite real do Buffer não é documentado —
só descobrimos que existe batendo nele.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "estado" / "buffer_cota.json"

# Teto por janela de 24h. Chutado pra baixo: com 4 postagens/dia e o agendador
# rodando depois de cada corte (~16 vezes/dia), 120 dá folga de sobra.
TETO_24H = 120
JANELA_S = 24 * 3600
# Quanto tempo o estado da fila é considerado fresco. A fila muda 4 vezes por
# dia; 15 min é bem mais rápido que isso e já corta a maior parte das chamadas.
IDADE_CACHE_S = 15 * 60


class CotaEstourada(RuntimeError):
    """Levantada ANTES de chamar a rede, quando o orçamento acabou."""


def _ler() -> dict:
    if ARQ.exists():
        try:
            return json.loads(ARQ.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"chamadas": [], "cache": None, "cache_em": 0}


def _gravar(d: dict) -> None:
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _limpar(d: dict) -> dict:
    corte = time.time() - JANELA_S
    d["chamadas"] = [t for t in d.get("chamadas", []) if t > corte]
    return d


def usadas() -> int:
    return len(_limpar(_ler())["chamadas"])


def restantes() -> int:
    return max(0, TETO_24H - usadas())


def registrar(n: int = 1) -> None:
    """Marca `n` requisições feitas agora."""
    d = _limpar(_ler())
    agora = time.time()
    d["chamadas"].extend([agora] * n)
    _gravar(d)


def checar(n: int = 1) -> None:
    """Levanta CotaEstourada se `n` requisições não couberem no orçamento."""
    livre = restantes()
    if livre < n:
        raise CotaEstourada(
            f"orçamento da API do Buffer esgotado: {usadas()}/{TETO_24H} nas "
            f"últimas 24h, pedido de {n}. Espere a janela virar — a fila que "
            f"já está agendada continua saindo normalmente.")


def cache_valido() -> dict | None:
    """Estado da fila guardado, se ainda estiver fresco."""
    d = _ler()
    if d.get("cache") and (time.time() - d.get("cache_em", 0)) < IDADE_CACHE_S:
        return d["cache"]
    return None


def guardar_cache(estado: dict) -> None:
    d = _limpar(_ler())
    d["cache"] = estado
    d["cache_em"] = time.time()
    _gravar(d)


def resumo() -> str:
    d = _limpar(_ler())
    idade = int(time.time() - d.get("cache_em", 0)) // 60 if d.get("cache") else None
    txt = f"Buffer: {usadas()}/{TETO_24H} requisições nas últimas 24h"
    if idade is not None:
        txt += f" | cache de {idade} min"
    return txt
