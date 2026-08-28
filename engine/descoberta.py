"""Descoberta de vídeos candidatos via YouTube Data API v3.

Mistura duas fontes:
    canais fixos    -> uploads recentes de config.CANAIS_MONITORADOS
    busca aberta    -> config.TERMOS_HYPE, ordenado por relevância/views

Sem nicho, sem intenção editorial: o critério é hype puro (visto pra
monetizar), medido por views, velocidade de views e engajamento.
"""
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import config

_ISO_DUR = re.compile(
    r"P(?:(?P<d>\d+)D)?T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
)


def _chave() -> str:
    k = os.getenv("YOUTUBE_API_KEY")
    if not k:
        raise RuntimeError(
            "YOUTUBE_API_KEY não encontrada. Preencha o .env (veja .env.sample)."
        )
    return k


def _get(caminho: str, **params) -> dict:
    params["key"] = _chave()
    r = requests.get(f"{config.YOUTUBE_URL}/{caminho}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _duracao_s(iso: str) -> float:
    m = _ISO_DUR.match(iso or "")
    if not m:
        return 0.0
    d, h, mi, s = (int(g) if g else 0 for g in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _resolver_canal_id(handle: str) -> str | None:
    if handle.startswith("UC"):
        return handle
    alvo = handle.lstrip("@")
    j = _get("channels", part="id", forHandle=alvo)
    itens = j.get("items", [])
    return itens[0]["id"] if itens else None


def _uploads_do_canal(canal_id: str, desde: datetime) -> list[str]:
    j = _get(
        "search", part="id", channelId=canal_id, order="date", type="video",
        publishedAfter=desde.strftime("%Y-%m-%dT%H:%M:%SZ"), maxResults=25,
    )
    return [it["id"]["videoId"] for it in j.get("items", []) if it["id"].get("videoId")]


def _busca_aberta(termo: str, desde: datetime) -> list[str]:
    j = _get(
        "search", part="id", q=termo, order="viewCount", type="video",
        publishedAfter=desde.strftime("%Y-%m-%dT%H:%M:%SZ"), maxResults=25,
    )
    return [it["id"]["videoId"] for it in j.get("items", []) if it["id"].get("videoId")]


def _detalhes(ids: list[str]) -> list[dict]:
    """videos.list aceita até 50 IDs por chamada."""
    saida = []
    for i in range(0, len(ids), 50):
        lote = ids[i:i + 50]
        j = _get("videos", part="snippet,statistics,contentDetails", id=",".join(lote))
        saida.extend(j.get("items", []))
    return saida


def _pontuar(v: dict) -> dict | None:
    stats = v.get("statistics", {})
    snippet = v.get("snippet", {})
    dur = _duracao_s(v.get("contentDetails", {}).get("duration", ""))
    if dur < config.DESCOBERTA_DUR_MIN_S:
        return None

    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    comentarios = int(stats.get("commentCount", 0))
    if views <= 0:
        return None

    publicado = datetime.strptime(snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    horas = max(1.0, (datetime.now(timezone.utc) - publicado).total_seconds() / 3600)

    views_score = math.log10(views + 1)
    velocidade_score = math.log10(views / horas + 1)
    engajamento = (likes + comentarios) / views

    nota = (
        config.PESO_VIEWS * views_score
        + config.PESO_VELOCIDADE * velocidade_score
        + config.PESO_ENGAJAMENTO * engajamento * 10   # engajamento é uma fração pequena
    )

    return {
        "id": v["id"],
        "url": f"https://www.youtube.com/watch?v={v['id']}",
        "titulo": snippet.get("title", ""),
        "canal": snippet.get("channelTitle", ""),
        "canal_id": snippet.get("channelId", ""),
        "views": views,
        "views_por_hora": round(views / horas, 1),
        "engajamento_pct": round(engajamento * 100, 3),
        "duracao_min": round(dur / 60, 1),
        "publicado": snippet.get("publishedAt", ""),
        "nota": round(nota, 3),
    }


def _canais_cortados() -> set[str]:
    p = config.REGISTRO_CANAIS_CORTADOS
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")))


def marcar_canal_cortado(canal_id: str):
    """Chame depois de renderizar um corte, pra esse canal sair da fila de podcasts."""
    if not canal_id:
        return
    p = config.REGISTRO_CANAIS_CORTADOS
    p.parent.mkdir(parents=True, exist_ok=True)
    cortados = _canais_cortados()
    cortados.add(canal_id)
    p.write_text(json.dumps(sorted(cortados), ensure_ascii=False, indent=2), encoding="utf-8")


def _pontuar_podcast(v: dict, ja_cortados: set[str]) -> dict | None:
    snippet = v.get("snippet", {})
    canal_id = snippet.get("channelId", "")
    if canal_id in ja_cortados:
        return None

    stats = v.get("statistics", {})
    views = int(stats.get("viewCount", 0))
    if not (config.VIEWS_MIN_PODCAST <= views <= config.VIEWS_MAX_PODCAST):
        return None

    publicado = datetime.strptime(snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    horas = (datetime.now(timezone.utc) - publicado).total_seconds() / 3600
    if horas > config.JANELA_HORAS_PODCAST:
        return None
    horas = max(1.0, horas)

    likes = int(stats.get("likeCount", 0))
    comentarios = int(stats.get("commentCount", 0))
    engajamento = (likes + comentarios) / views if views else 0.0

    velocidade_score = math.log10(views / horas + 1)
    nota = (
        config.PESO_VIEWS * math.log10(views + 1)
        + config.PESO_VELOCIDADE * velocidade_score
        + config.PESO_ENGAJAMENTO * engajamento * 10
    )

    dur = _duracao_s(v.get("contentDetails", {}).get("duration", ""))
    return {
        "id": v["id"],
        "url": f"https://www.youtube.com/watch?v={v['id']}",
        "titulo": snippet.get("title", ""),
        "canal": snippet.get("channelTitle", ""),
        "canal_id": canal_id,
        "views": views,
        "views_por_hora": round(views / horas, 1),
        "engajamento_pct": round(engajamento * 100, 3),
        "duracao_min": round(dur / 60, 1),
        "publicado": snippet.get("publishedAt", ""),
        "horas_desde_publicado": round(horas, 1),
        "nota": round(nota, 3),
    }


def descobrir_podcasts(qtd: int = config.FILA_QTD) -> list[dict]:
    """Episódios de podcast recentes (<=48h), 100k-500k views, de canais que
    você ainda não cortou. videoDuration=long garante que é episódio de
    verdade, não short/trailer."""
    desde = datetime.now(timezone.utc) - timedelta(hours=config.JANELA_HORAS_PODCAST)
    termos = config.PODCAST_TERMOS_HYPE or ["podcast"]

    ids: set[str] = set()
    for termo in termos:
        j = _get(
            "search", part="id", q=termo, order="date", type="video",
            videoDuration="long",
            publishedAfter=desde.strftime("%Y-%m-%dT%H:%M:%SZ"), maxResults=25,
        )
        ids.update(it["id"]["videoId"] for it in j.get("items", []) if it["id"].get("videoId"))

    if not ids:
        return []

    cortados = _canais_cortados()
    candidatos = [_pontuar_podcast(v, cortados) for v in _detalhes(list(ids))]
    candidatos = [c for c in candidatos if c is not None]
    candidatos.sort(key=lambda c: -c["nota"])
    return candidatos[:qtd]


def descobrir(qtd: int = config.FILA_QTD) -> list[dict]:
    """Junta canais fixos + busca aberta, pontua e devolve os top `qtd`."""
    desde = datetime.now(timezone.utc) - timedelta(days=config.JANELA_DIAS)

    ids: set[str] = set()

    for handle in config.CANAIS_MONITORADOS:
        cid = _resolver_canal_id(handle)
        if not cid:
            print(f"   [!] canal não encontrado: {handle}")
            continue
        ids.update(_uploads_do_canal(cid, desde))

    for termo in config.TERMOS_HYPE:
        ids.update(_busca_aberta(termo, desde))

    if not ids:
        return []

    candidatos = [_pontuar(v) for v in _detalhes(list(ids))]
    candidatos = [c for c in candidatos if c is not None]
    candidatos.sort(key=lambda c: -c["nota"])
    return candidatos[:qtd]
