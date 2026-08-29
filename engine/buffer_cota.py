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

  - **Orçamento**: conta as requisições em DUAS janelas — 15 minutos e 24h — e
    RECUSA passar de qualquer uma delas. Melhor a fila ficar desatualizada por
    algumas horas do que a conta inteira travar por um dia.
  - **Cache**: estado da fila lido no máximo uma vez a cada `IDADE_CACHE_S`.
    Chamada seguinte dentro da janela reaproveita, sem tocar na rede.

Os limites vieram do painel da API da conta do @modofuturo, lido em 29/08/2026.
Esta conta é SEPARADA e o painel dela nunca foi aberto — ver o aviso em
`TETO_24H` antes de confiar nos números.

⚠️ O painel avisa que "Keys and Active Integrations share this limit": o uso do
app do Buffer sai do mesmo bolo. Por isso a margem de 20%, e não zero.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "estado" / "buffer_cota.json"

# ⚠️ ESTES TETOS FORAM MEDIDOS NA OUTRA CONTA, NÃO NESTA.
#
# O painel da API foi lido em 29/08/2026 na conta do @modofuturo:
#
#   janela      limite real   teto nosso   margem
#   15 min          100           80         20%
#   24 h            250          200         20%
#   30 dias        3.000          --         (não vigiado; ver abaixo)
#
# O @cozinha.internacional usa uma conta do Buffer SEPARADA (decidido em
# 28/08), com orçamento próprio — que é justamente o que impede um canal de
# deixar o outro sem cota. Mas o painel dessa conta nunca foi aberto: se ela
# estiver em outro plano, estes números estão errados para cá.
#
# Herdados de propósito mesmo assim, porque o teto anterior (120, chutado)
# não tinha medição nenhuma por trás e ainda vigiava só uma das duas janelas.
# Trocar chute por medição-de-conta-vizinha é melhora; não é verificação.
#
# PARA FECHAR: abrir o painel da API na conta do Cozinha e conferir os três
# números. Se baterem, apagar este aviso.
TETO_24H = 200
JANELA_S = 24 * 3600

# A janela de 15 minutos é a que de fato pega a gente, e o módulo não a vigiava.
# O incidente de 25/08 foi lido como estouro de 24h, mas 288 chamadas/dia não
# passam de 250 — o que estourou foi a rajada: a consulta de fila PAGINA, então
# uma única reorganização dispara várias requisições em segundos.
TETO_15MIN = 80
JANELA_CURTA_S = 15 * 60

# O teto de 30 dias (3.000) não é vigiado de propósito: 200/dia por 30 dias dá
# 6.000, mas o uso real é de ~500/mês. Se algum dia encostar, é sintoma de laço,
# e o lugar de pegar laço é a janela de 15 min, não a de um mês.

# Quanto tempo o estado da fila é considerado fresco. A fila muda 4 vezes por
# dia; 15 min é bem mais rápido que isso e já corta a maior parte das chamadas.
#
# ⚠️ Este cache também engana QUEM CONFERE. Em 29/08 a conferência da fila logo
# depois de agendar devolveu "0 agendados" — era o cache de antes do
# agendamento, não o Buffer. Verificação de fila precisa furar o cache.
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


def usadas_curta() -> int:
    """Requisições nos últimos 15 minutos."""
    corte = time.time() - JANELA_CURTA_S
    return sum(1 for t in _limpar(_ler())["chamadas"] if t > corte)


def restantes() -> int:
    """Quantas cabem AGORA, considerando as duas janelas.

    É o mínimo das duas: de nada adianta ter folga no dia se a rajada dos
    últimos 15 minutos já encostou no limite curto.
    """
    return max(0, min(TETO_24H - usadas(), TETO_15MIN - usadas_curta()))


def registrar(n: int = 1) -> None:
    """Marca `n` requisições feitas agora."""
    d = _limpar(_ler())
    agora = time.time()
    d["chamadas"].extend([agora] * n)
    _gravar(d)


def checar(n: int = 1) -> None:
    """Levanta CotaEstourada se `n` requisições não couberem no orçamento.

    As duas janelas são checadas separadamente porque a espera é MUITO
    diferente: estourar a curta custa minutos, estourar a de 24h custa o dia.
    Dizer qual das duas travou é o que permite decidir se vale esperar.
    """
    if TETO_15MIN - usadas_curta() < n:
        raise CotaEstourada(
            f"rajada curta demais: {usadas_curta()}/{TETO_15MIN} requisições "
            f"nos últimos 15 minutos, pedido de {n}. Espere alguns minutos — "
            f"esta janela vira rápido, e a fila agendada continua saindo.")
    if TETO_24H - usadas() < n:
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
    txt = (f"Buffer: {usadas()}/{TETO_24H} requisições nas últimas 24h"
           f" | {usadas_curta()}/{TETO_15MIN} nos últimos 15 min")
    if idade is not None:
        txt += f" | cache de {idade} min"
    return txt
