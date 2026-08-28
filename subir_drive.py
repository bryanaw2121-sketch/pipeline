"""Sobe os clipes prontos pro Google Drive, todos numa pasta por dia
(ex: '28-07'), com a legenda num .txt ao lado (pro iPhone: baixa o vídeo
+ abre o txt e cola no TikTok). O nome começa por um número sequencial e
depois a nota (003_nota91_...), então dá pra ordenar por nome, ver as
melhores primeiro e achar um clipe pelo número numa lista longa —
ver numeracao.py.

Existe como alternativa ao rascunho via API quando a fila do TikTok trava
(ver sabedoria/SABEDORIA_TIKTOK.md, "REGRA DE OURO").

    python subir_drive.py --pasta-id 1uYzc71yxlYvl-aJeTFf0whDuwDXVoXxU

Reaproveita o client_secrets.json já usado pro YouTube (publicar.py), mas
com escopo Drive e token separado (token_drive.json) — não mistura com o
token.json do YouTube.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import config
import numeracao
from engine import telegram
from publicar_tiktok import legenda_do_clipe

SCOPES = ["https://www.googleapis.com/auth/drive"]
CLIENT_SECRETS = config.RAIZ / "client_secrets.json"
TOKEN = config.RAIZ / "token_drive.json"
REGISTRO = config.RAIZ / "estado" / "enviados_drive.json"


def _servico(conta: str = "principal"):
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Conta escolhida por quem disparou o corte: o vídeo inteiro vive numa
    # conta só, então os clipes vão pro A POSTAR da mesma conta onde o bruto
    # estava. Ver contas_drive.py.
    try:
        import contas_drive
        return contas_drive.servico(contas_drive.conta_por_nome(conta))
    except Exception as e:
        print(f"[aviso] seleção de conta indisponível ({e}); usando fallback.")

    # OAuth por variável de ambiente — é ESTE o caminho pro GitHub Actions.
    #
    # Service Account NÃO serve pra subir arquivo: o Drive responde
    # "Service Accounts do not have storage quota" (403), porque SA não tem
    # armazenamento próprio. Ela cria pasta (pasta não ocupa espaço) e
    # BAIXA normalmente, mas nunca grava conteúdo. As saídas que o Google
    # sugere — Shared Drive e OAuth delegation — exigem Workspace pago, e
    # a conta do projeto é Gmail comum. Medido em 28/07/2026, run #8.
    #
    # Por isso o token OAuth (que carrega a cota da conta pessoal) vem
    # ANTES da SA aqui. O refresh_token renova sozinho, sem tela.
    oauth_json = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if oauth_json:
        cred = Credentials.from_authorized_user_info(json.loads(oauth_json), SCOPES)
        if not cred.valid and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        return build("drive", "v3", credentials=cred)

    # Service Account continua servindo pra LEITURA (baixar_bruto_drive.py).
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        from google.oauth2 import service_account
        info = json.loads(sa_json)
        cred = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("drive", "v3", credentials=cred)

    cred = None
    if TOKEN.exists():
        cred = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            if not CLIENT_SECRETS.exists():
                sys.exit(f"Falta {CLIENT_SECRETS}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
            cred = flow.run_local_server(port=0)
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=cred)


def _chave(clipe: Path) -> str:
    return f"{clipe.parent.parent.name}/{clipe.name}"


def _enviados() -> set[str]:
    if not REGISTRO.exists():
        return set()
    return set(json.loads(REGISTRO.read_text(encoding="utf-8")))


def _marcar(chave: str):
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    atual = _enviados()
    atual.add(chave)
    REGISTRO.write_text(json.dumps(sorted(atual), ensure_ascii=False, indent=2), encoding="utf-8")


def fila_pendente_drive() -> list[tuple[float, Path]]:
    """Igual à fila do TikTok (mesmo critério de nota/lote ignorado), mas com
    registro PRÓPRIO — subir pro Drive não marca como enviado pro TikTok e
    vice-versa, são filas independentes."""
    ja = _enviados()
    achados = []
    for pj in config.SAIDA.rglob("post.json"):
        clipe = pj.parent
        lote = clipe.parent.parent.name
        if lote in config.LOTES_IGNORADOS:
            continue
        if not (clipe / "short_9x16.mp4").exists():
            continue
        if _chave(clipe) in ja:
            continue
        try:
            nota = float(json.loads(pj.read_text(encoding="utf-8")).get("nota", 0))
        except Exception:
            nota = 0.0
        achados.append((nota, clipe))
    achados.sort(key=lambda x: -x[0])
    return achados


def _achar_ou_criar_subpasta(servico, pai_id: str, nome: str) -> str:
    """Acha a subpasta pelo nome; cria se não existir — usado pra pasta do
    dia (ex: '26-07') dentro da pasta pai."""
    q = (f"'{pai_id}' in parents and name = '{nome}' "
         "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    r = servico.files().list(q=q, fields="files(id, name)").execute()
    arquivos = r.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder", "parents": [pai_id]}
    nova = servico.files().create(body=meta, fields="id").execute()
    return nova["id"]


def _upload(servico, pasta_id: str, caminho: Path, mimetype: str):
    from googleapiclient.http import MediaFileUpload
    meta = {"name": caminho.name, "parents": [pasta_id]}
    media = MediaFileUpload(str(caminho), mimetype=mimetype, resumable=True)
    servico.files().create(body=meta, media_body=media, fields="id").execute()


def subir(pasta_pai_id: str, avisar_telegram: bool = True, conta: str = "principal"):
    fila = fila_pendente_drive()
    if not fila:
        print("Nada pendente pra subir no Drive.")
        return

    print(f"{len(fila)} clipe(s) pra subir.\n")
    servico = _servico(conta)
    # A pasta do dia se divide em `parte 01`, `parte 02`... com 15 clipes cada
    # (numeracao.POR_PASTA). Antes tudo do dia caía numa pasta só, e em 29/07
    # isso deu 138 clipes — rolagem longa no celular pra achar qualquer um.
    # A classificação continua no NOME (003_nota91_...), e o número é do DIA:
    # não reinicia a cada parte.
    # O nome carrega a versão do motor (`31-07 v2`) — assim dá pra ver de
    # olho, no Drive, o que saiu do motor novo. Ver numeracao.MARCA_MOTOR.
    hoje = numeracao.nome_do_dia(date.today().strftime("%d-%m"))
    pasta_dia = _achar_ou_criar_subpasta(servico, pasta_pai_id, hoje)

    # A numeração continua de onde o lote anterior do dia parou — a pasta do
    # dia recebe vários runs, e reiniciar em 001 criaria dois clipes com o
    # mesmo apelido. Ver numeracao.py.
    numero = numeracao.maior_numero_na_pasta(servico, pasta_dia)

    # Medido em 30/07: DOIS runs do GitHub Actions cortaram em paralelo, cada
    # um contou o maior número antes de o outro subir, e os dois começaram no
    # 013 — dois clipes com o mesmo apelido, 3 segundos de diferença. Contar
    # uma vez por run não basta quando há mais de um run.
    #
    # Por isso a contagem é refeita a cada clipe (abaixo), o que estreita a
    # janela de colisão de "a duração do run" para "a duração de um upload".
    # Não elimina: a rede de segurança é o renumerar_a_postar.py, que
    # reordena a pasta inteira e é idempotente.

    # As subpastas `parte NN` são criadas sob demanda e ficam em cache aqui:
    # sem isso seria uma consulta ao Drive por clipe só pra achar a mesma
    # pasta de novo.
    partes: dict[str, str] = {}

    enviados = 0
    for nota, clipe in fila:
        numero = max(numero + 1,
                     numeracao.maior_numero_na_pasta(servico, pasta_dia) + 1)
        parte = numeracao.nome_da_parte(numero)
        if parte not in partes:
            partes[parte] = _achar_ou_criar_subpasta(servico, pasta_dia, parte)
        destino = partes[parte]
        video = clipe / "short_9x16.mp4"
        legenda = legenda_do_clipe(clipe)

        txt = clipe / "_legenda_drive.txt"
        txt.write_text(legenda, encoding="utf-8")

        base = numeracao.com_numero(f"nota{int(nota)}_{clipe.name}", numero)
        nome_video = f"{base}.mp4"
        nome_txt = f"{base}.txt"
        print(f"  [{hoje}/{parte}] {numeracao.formatar(numero)}  "
              f"nota {nota:.0f}  {clipe.name}")
        try:
            _upload_renomeado(servico, destino, video, nome_video, "video/mp4")
            _upload_renomeado(servico, destino, txt, nome_txt, "text/plain")
        finally:
            txt.unlink(missing_ok=True)

        _marcar(_chave(clipe))
        if avisar_telegram:
            telegram.enviar(f"[Drive · {hoje}/{parte} · "
                            f"{numeracao.formatar(numero)}] {legenda}")
        enviados += 1

    print(f"\n{enviados} clipe(s) enviado(s) pro Drive"
          f"{' (legendas mandadas pro Telegram)' if avisar_telegram else ''}.")


def _upload_renomeado(servico, pasta_id: str, caminho: Path, nome: str, mimetype: str):
    from googleapiclient.http import MediaFileUpload
    meta = {"name": nome, "parents": [pasta_id]}
    media = MediaFileUpload(str(caminho), mimetype=mimetype, resumable=True)
    servico.files().create(body=meta, media_body=media, fields="id").execute()


def main():
    p = argparse.ArgumentParser(description="Sobe os clipes prontos pro Google Drive, por nota")
    p.add_argument("--pasta-id", required=True,
                   help="ID da pasta pai do Drive (onde nasce a pasta do dia)")
    p.add_argument("--conta", default="principal",
                   help="conta do Drive a usar (ver contas_drive.py)")
    p.add_argument("--sem-telegram", action="store_true",
                   help="não manda as legendas pro Telegram")
    a = p.parse_args()
    subir(a.pasta_id, avisar_telegram=not a.sem_telegram, conta=a.conta)


if __name__ == "__main__":
    main()
