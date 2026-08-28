"""Escreve o estado atual do motor em JSON, pro painel (painel/index.html)
ler via polling. Não tem servidor nem push — é só um arquivo que o main.py
e o descobrir.py atualizam a cada etapa."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

import config

load_dotenv()

ARQ_STATUS = config.RAIZ / "estado" / "status.json"
ARQ_FILA = config.RAIZ / "estado" / "fila_atual.json"
ARQ_HISTORICO = config.RAIZ / "estado" / "historico.json"
ARQ_CONTAS = config.RAIZ / "estado" / "contas.json"

_lock_dummy = None  # processo único por vez; sem concorrência real aqui


def _gravar(caminho: Path, dado: dict):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # nome de tmp único por chamada — se cair no meio de uma leitura do
    # painel, a próxima gravação não esbarra num .tmp de outra thread
    tmp = caminho.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=2), encoding="utf-8")
    # no Windows, o servidor do painel pode estar com o arquivo aberto no
    # exato instante da troca — isso é passageiro, alguns ms de retry resolve
    for tentativa in range(10):
        try:
            tmp.replace(caminho)
            return
        except PermissionError:
            if tentativa == 9:
                raise
            time.sleep(0.05)


def etapa(fonte: str, passo: str, detalhe: str = "", clipe: int | None = None,
          total_clipes: int | None = None):
    _gravar(ARQ_STATUS, {
        "fonte": fonte,
        "passo": passo,
        "detalhe": detalhe,
        "clipe": clipe,
        "total_clipes": total_clipes,
        "atualizado_em": time.time(),
    })


def ocioso():
    _gravar(ARQ_STATUS, {"passo": "ocioso", "atualizado_em": time.time()})


def ler_status() -> dict:
    if not ARQ_STATUS.exists():
        return {"passo": "ocioso"}
    try:
        return json.loads(ARQ_STATUS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"passo": "ocioso"}


# ------------------------------------------------------------------ fila
def gravar_fila(itens: list[dict]):
    """itens: [{id, titulo, url, status}], status em
    pendente|processando|concluido|erro"""
    _gravar(ARQ_FILA, {"itens": itens, "atualizado_em": time.time()})


def ler_fila() -> list[dict]:
    if not ARQ_FILA.exists():
        return []
    try:
        return json.loads(ARQ_FILA.read_text(encoding="utf-8")).get("itens", [])
    except (json.JSONDecodeError, OSError):
        return []


def marcar_item(url: str, status: str, **extra):
    itens = ler_fila()
    item_atual = None
    for it in itens:
        if it.get("url") == url:
            it["status"] = status
            it.update(extra)
            item_atual = it
            break
    if item_atual is None and url:
        # processamento manual (main.py --url direto, fora da fila do
        # descobrir.py) — cria a entrada na hora, pro painel mostrar também
        item_atual = {"id": url, "url": url, "titulo": extra.get("titulo", url),
                      "canal": "", "nota": None, "origem": "manual",
                      "status": status, **extra}
        itens.append(item_atual)
    gravar_fila(itens)
    if url:
        campos = {"titulo": item_atual.get("titulo"), "canal": item_atual.get("canal")}
        campos.update(extra)
        _registrar_historico(url, status=status, **campos)


# ------------------------------------------------------------------ histórico
# Ao contrário da fila (que o descobrir.py sobrescreve a cada rodada), o
# histórico é permanente — cada vídeo processado fica registrado aqui pra
# sempre, com os horários de cada marco.
def _ler_historico() -> dict:
    if not ARQ_HISTORICO.exists():
        return {}
    try:
        return json.loads(ARQ_HISTORICO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _registrar_historico(url: str, **campos):
    hist = _ler_historico()
    reg = hist.get(url, {"url": url})
    reg.update({k: v for k, v in campos.items() if v is not None})
    hist[url] = reg
    _gravar(ARQ_HISTORICO, hist)


def ler_historico() -> list[dict]:
    hist = _ler_historico()
    return sorted(hist.values(), key=lambda r: r.get("iniciado_em") or 0, reverse=True)


# ------------------------------------------------------------------ contas
# Não existe API de billing plugada aqui — isso conta quantas chaves cada
# provedor tem NO .env e mostra limite/preço de referência (o que está
# documentado publicamente pelos provedores). Gasto real só no painel de
# cada provedor; não inventamos número de "quanto já gastou".
_PROVEDORES = [
    {"chave": "GEMINI_API_KEY", "nome": "Gemini (Google)",
     "uso": "escolhe os momentos + traduz",
     "limite": "free tier: 1500 req/dia por chave (varia por modelo)"},
    {"chave": "GROQ_API_KEY", "nome": "Groq",
     "uso": "transcrição palavra a palavra",
     "limite": "whisper-large-v3: US$ 0,111/hora de áudio"},
    {"chave": "YOUTUBE_API_KEY", "nome": "YouTube Data API v3",
     "uso": "descoberta de vídeos (descobrir.py)",
     "limite": "10.000 unidades/dia (search=100, videos.list=1)"},
    {"chave": "NVIDIA_API_KEY", "nome": "NVIDIA NIM",
     "uso": "não usado no motor atual (reserva)",
     "limite": "varia por modelo"},
    {"chave": "OPENROUTER_API_KEY", "nome": "OpenRouter",
     "uso": "não usado no motor atual (reserva)",
     "limite": "varia por modelo, tem opções grátis"},
    {"chave": "MISTRAL_API_KEY", "nome": "Mistral",
     "uso": "não usado no motor atual (reserva)",
     "limite": "varia por modelo"},
    {"chave": "DEEPSEEK_API_KEY", "nome": "DeepSeek",
     "uso": "não usado no motor atual (reserva)",
     "limite": "varia por modelo"},
]


def _contar_chaves(prefixo: str) -> int:
    n = 1 if os.getenv(prefixo) else 0
    i = 2
    while os.getenv(f"{prefixo}_{i}"):
        n += 1
        i += 1
    return n


def contas_conectadas() -> list[dict]:
    saida = []
    for p in _PROVEDORES:
        n = _contar_chaves(p["chave"])
        saida.append({
            "nome": p["nome"], "chaves_configuradas": n,
            "conectado": n > 0, "uso": p["uso"], "limite_referencia": p["limite"],
        })
    # publicação no YouTube usa OAuth, não chave — status separado
    saida.append({
        "nome": "YouTube (upload, OAuth)",
        "chaves_configuradas": 1 if TOKEN_OAUTH.exists() else 0,
        "conectado": TOKEN_OAUTH.exists(),
        "uso": "publicar.py — sobe os cortes",
        "limite_referencia": "10.000 unidades/dia (upload ≈ 100 cada)",
    })
    return saida


TOKEN_OAUTH = config.RAIZ / "token.json"
