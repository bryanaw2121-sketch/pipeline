"""Bot de controle no Telegram — você manda /mais, ele despacha a próxima fila.

    python bot_telegram.py --descobrir-chat   # 1x, acha e grava seu chat_id
    python bot_telegram.py                    # fica escutando

Comandos no Telegram:
    /mais       manda os próximos 5 do rascunho + as legendas
    /mais 3     manda 3
    /fila       lista o que ainda falta, sem enviar
    /ajuda      lista os comandos

Fluxo pensado pro limite do TikTok: ele recusa novo rascunho com
`spam_risk_too_many_pending_share` quando há envios recentes demais. Então
você posta os pendentes no app, manda /mais, e a próxima leva entra — com a
legenda de cada vídeo chegando no Telegram pra copiar e colar.
"""
import argparse
import json
import sys
import time

import config
import publicar_tiktok as tt
from engine import descobertas, telegram

AJUDA = (
    "DESCOBRIR\n"
    "/lista — melhores candidatos, numerados\n"
    "/lista 12 — mostra 12\n"
    "/radar — busca candidatos novos (~2 min)\n"
    "\nCORTAR\n"
    "/cortar 3 — corta o item 3 do /lista\n"
    "/cortar <url> — corta uma URL qualquer\n"
    "\nPUBLICAR\n"
    "/fila — clipes prontos esperando\n"
    "/legendas — manda as legendas pra copiar\n"
    "/legendas 9 — manda 9 legendas\n"
    "/mais — 5 pro rascunho do TikTok + legendas\n"
    "/mais 3 — manda 3\n"
    "\n/ajuda — isso aqui"
)


def _texto_fila() -> str:
    fila = tt.fila_pendente()
    if not fila:
        return "Fila vazia — todos os clipes prontos já foram pro rascunho."
    linhas = [f"{len(fila)} na fila (melhor nota primeiro):", ""]
    for i, c in enumerate(fila, 1):
        try:
            nota = json.loads((c / "post.json").read_text(encoding="utf-8")).get("nota")
        except Exception:
            nota = "?"
        titulo = c.name.split("_", 2)[-1]
        linhas.append(f"{i:02d}. [{nota}] {titulo[:50]}")
    return "\n".join(linhas)


def _tratar(texto: str, chat: str):
    partes = texto.strip().split()
    if not partes:
        return
    cmd = partes[0].lower().lstrip("/").split("@")[0]   # /mais@MeuBot -> mais

    if cmd in ("mais", "more", "proximos"):
        qtd = config.TIKTOK_LOTE
        if len(partes) > 1:
            try:
                qtd = max(1, min(20, int(partes[1])))
            except ValueError:
                pass
        telegram.enviar(f"Ok, mandando {qtd}...", chat)
        try:
            tt.enviar_proximos(qtd)
        except Exception as e:
            telegram.enviar(f"Falhou: {e}", chat)

    elif cmd == "fila":
        telegram.enviar(_texto_fila(), chat)

    elif cmd in ("lista", "virais", "top"):
        n = 6
        if len(partes) > 1:
            try:
                n = max(1, min(15, int(partes[1])))
            except ValueError:
                pass
        telegram.enviar(descobertas.resumo_telegram(n), chat)

    elif cmd in ("cortar", "corta"):
        if len(partes) < 2:
            telegram.enviar("Use: /cortar 3   (o número que aparece no /lista)\n"
                            "ou:  /cortar https://youtube.com/watch?v=...", chat)
            return
        alvo = partes[1]
        url = alvo if alvo.startswith("http") else None
        if url is None:
            try:
                url = descobertas.url_por_numero(int(alvo))
            except (ValueError, IndexError):
                telegram.enviar(f"Não achei o item '{alvo}'. Veja /lista.", chat)
                return
        telegram.enviar(f"Cortando {url}\nIsso leva alguns minutos — te aviso.", chat)
        try:
            saida = descobertas.cortar_url(url)
            telegram.enviar(f"Pronto: {saida}\n\nMande /legendas pra pegar as "
                            f"legendas ou /fila pra ver tudo.", chat)
        except Exception as e:
            telegram.enviar(f"Falhou ao cortar: {e}", chat)

    elif cmd in ("legendas", "legenda"):
        n = 5
        if len(partes) > 1:
            try:
                n = max(1, min(20, int(partes[1])))
            except ValueError:
                pass
        tt.mandar_legendas(n)

    elif cmd == "radar":
        telegram.enviar("Rodando os 3 radares... isso leva ~2 min.", chat)
        try:
            resultado = descobertas.rodar_radares()
            telegram.enviar(f"Radares terminaram:\n{resultado}", chat)
            telegram.enviar(descobertas.resumo_telegram(6), chat)
        except Exception as e:
            telegram.enviar(f"Radar falhou: {e}", chat)

    elif cmd in ("ajuda", "help", "start"):
        telegram.enviar(AJUDA, chat)

    else:
        telegram.enviar(f"Não conheço '{cmd}'.\n\n{AJUDA}", chat)


def escutar():
    meu_chat = telegram.chat_id()
    print("Escutando o Telegram. Ctrl+C pra parar.")
    print(f"Fila agora: {len(tt.fila_pendente())} clipes\n")
    telegram.enviar(f"Bot ligado.\n\n{AJUDA}")

    offset = None
    while True:
        try:
            for upd in telegram.atualizacoes(offset):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                texto = msg.get("text") or ""
                chat = str((msg.get("chat") or {}).get("id", ""))
                if not texto or not chat:
                    continue
                # só obedece o dono do bot — qualquer um pode achar um bot
                if meu_chat and chat != str(meu_chat):
                    print(f"  [ignorado] chat {chat}: {texto[:40]}")
                    continue
                print(f"  > {texto[:60]}")
                _tratar(texto, chat)
        except KeyboardInterrupt:
            print("\nparando.")
            return
        except Exception as e:
            print(f"  [!] erro no loop: {e}")
            time.sleep(10)


def main():
    p = argparse.ArgumentParser(description="Bot de controle no Telegram")
    p.add_argument("--descobrir-chat", action="store_true",
                   help="1x: acha seu chat_id pelas mensagens e grava no .env")
    a = p.parse_args()

    if not telegram.configurado():
        sys.exit("Falta TELEGRAM_BOT_TOKEN no .env.\n"
                 "  1. no Telegram, fale com @BotFather -> /newbot\n"
                 "  2. ponha o token no .env como TELEGRAM_BOT_TOKEN=...\n"
                 "  3. mande qualquer mensagem pro seu bot\n"
                 "  4. rode: python bot_telegram.py --descobrir-chat")

    if a.descobrir_chat:
        telegram.descobrir_chat()
        return

    if not telegram.chat_id():
        sys.exit("Falta TELEGRAM_CHAT_ID. Mande uma mensagem pro seu bot e rode:\n"
                 "  python bot_telegram.py --descobrir-chat")

    escutar()


if __name__ == "__main__":
    main()
