"""Telegram: manda legenda pro celular e recebe comandos.

Existe porque o rascunho do TikTok NÃO carrega legenda (a API de inbox só
aceita o arquivo de vídeo), então a legenda é colada na mão no celular.
Telegram é a ponte: legenda sai do desktop e chega no celular já formatada,
uma mensagem por clipe — dá pra tocar e copiar.

Setup (1x):
  1. no Telegram, fale com @BotFather -> /newbot -> copie o token
  2. .env:  TELEGRAM_BOT_TOKEN=...
  3. mande qualquer mensagem pro seu bot (bot não pode iniciar conversa)
  4. python bot_telegram.py --descobrir-chat
"""
import json
import os

import requests
from dotenv import load_dotenv

import config

load_dotenv()

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_MSG = 4000          # o limite real é 4096, deixa folga


def configurado() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN"))


def _token() -> str:
    t = os.getenv("TELEGRAM_BOT_TOKEN")
    if not t:
        raise RuntimeError(
            "Falta TELEGRAM_BOT_TOKEN no .env. Fale com @BotFather no Telegram, "
            "/newbot, e ponha o token no .env.")
    return t


def chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID")


def chamar(metodo: str, **params) -> dict:
    r = requests.post(API.format(token=_token(), metodo=metodo),
                      json=params, timeout=40)
    r.raise_for_status()
    return r.json()


def enviar(texto: str, destino: str | None = None) -> bool:
    """Manda uma mensagem. Devolve False (sem estourar) se não configurado —
    o envio pro TikTok não deve falhar só porque o Telegram não está pronto."""
    destino = destino or chat_id()
    if not configurado() or not destino:
        return False
    try:
        for pedaco in _picar(texto):
            chamar("sendMessage", chat_id=destino, text=pedaco,
                   disable_web_page_preview=True)
        return True
    except Exception as e:
        print(f"      [!] Telegram falhou: {e}")
        return False


def _picar(texto: str) -> list[str]:
    """Quebra em pedaços dentro do limite do Telegram, cortando em linha."""
    if len(texto) <= LIMITE_MSG:
        return [texto]
    pedacos, atual = [], ""
    for linha in texto.splitlines(keepends=True):
        if len(atual) + len(linha) > LIMITE_MSG:
            pedacos.append(atual)
            atual = ""
        atual += linha
    if atual:
        pedacos.append(atual)
    return pedacos


def atualizacoes(offset: int | None = None, espera: int = 50) -> list[dict]:
    """Long polling. `espera` alto = menos requisições, sem perder mensagem."""
    params = {"timeout": espera}
    if offset is not None:
        params["offset"] = offset
    return chamar("getUpdates", **params).get("result", [])


def descobrir_chat() -> str:
    """Acha o chat_id pelas mensagens recentes e grava no .env."""
    chats = {}
    for upd in atualizacoes(espera=0):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            chats[str(chat["id"])] = (chat.get("username")
                                      or chat.get("first_name")
                                      or chat.get("title", "?"))
    if not chats:
        raise RuntimeError("Nenhuma mensagem encontrada. Mande qualquer mensagem "
                           "pro seu bot no Telegram e rode de novo.")

    for cid, nome in chats.items():
        print(f"  chat_id={cid}  ({nome})")
    cid = next(iter(chats))
    _gravar_env("TELEGRAM_CHAT_ID", cid)
    print(f"\nGravado TELEGRAM_CHAT_ID={cid} no .env")
    return cid


def _gravar_env(chave: str, valor: str):
    env = config.RAIZ / ".env"
    texto = env.read_text(encoding="utf-8") if env.exists() else ""
    if f"{chave}=" in texto:
        linhas = [f"{chave}={valor}" if l.startswith(f"{chave}=") else l
                  for l in texto.splitlines()]
        env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    else:
        env.write_text(texto.rstrip() + f"\n{chave}={valor}\n", encoding="utf-8")
