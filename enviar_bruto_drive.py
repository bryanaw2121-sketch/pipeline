"""Sobe um vídeo-fonte BRUTO (ainda não cortado) pra uma pasta do Drive,
pro GitHub Actions baixar de lá e processar o resto (Gemini, corte,
legenda, render) sem precisar baixar do YouTube na nuvem — o download
continua sendo feito aqui, local, porque IP de datacenter é bloqueado
pelo YouTube (ver handoff 28/07/2026).

    python enviar_bruto_drive.py --arquivo caminho\fonte.mp4 --pasta-id 1uYzc71...

Reaproveita a mesma autenticação (client_secrets.json / token_drive.json)
já usada pelo subir_drive.py.
"""
import argparse
import datetime
import sys
from pathlib import Path

import config

SCOPES = ["https://www.googleapis.com/auth/drive"]
CLIENT_SECRETS = config.RAIZ / "client_secrets.json"
TOKEN = config.RAIZ / "token_drive.json"


def _servico(conta: str = "principal"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # A conta vem de quem chamou (o processar_lista escolhe pela folga de
    # espaço). Antes daqui só existia o token_drive.json, ou seja: a conta
    # principal, sempre — e quando ela enchia o upload morria com 403, com o
    # trabalho de Gemini e Groq já pago. Ver contas_drive.py.
    if conta and conta != "principal":
        import contas_drive
        return contas_drive.servico(contas_drive.conta_por_nome(conta))

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


def _achar_ou_criar_subpasta(servico, pai_id: str, nome: str) -> str:
    def procurar():
        q = (f"'{pai_id}' in parents and name = '{nome}' and "
             "mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        return servico.files().list(
            q=q, fields="files(id, name, createdTime)",
            orderBy="createdTime").execute().get("files", [])

    achados = procurar()
    if achados:
        return achados[0]["id"]
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder", "parents": [pai_id]}
    novo = servico.files().create(body=meta, fields="id").execute()["id"]
    # O Drive deixa criar duas pastas com o MESMO nome, e o processar_lista
    # roda dois downloads em paralelo: em 30/07 os dois criaram sua própria
    # `2026-07-30` e os brutos ficaram espalhados em duas pastas iguais.
    # Depois de criar, procura de novo e fica com a MAIS ANTIGA — as duas
    # threads convergem para a mesma.
    achados = procurar()
    return achados[0]["id"] if achados else novo


def enviar(arquivo: Path, pasta_pai_id: str, apagar_local: bool = False,
           conta: str = "principal", subpasta: str = "brutos") -> str:
    from googleapiclient.http import MediaFileUpload

    servico = _servico(conta)
    # `subpasta` vazia = grava direto no pai. É o que o processar_lista usa ao
    # mandar pra RAW, que já tem o nível de data e é o que o vigia varre.
    pasta_brutos = (_achar_ou_criar_subpasta(servico, pasta_pai_id, subpasta)
                    if subpasta else pasta_pai_id)
    # Um nível a mais por data: brutos/AAAA-MM-DD agrupa tudo que entrou no
    # dia, senão a pasta brutos vira um monte só depois de algumas semanas.
    hoje = datetime.date.today().isoformat()
    pasta_dia = _achar_ou_criar_subpasta(servico, pasta_brutos, hoje)
    meta = {"name": arquivo.name, "parents": [pasta_dia]}
    media = MediaFileUpload(str(arquivo), resumable=True)
    arq = servico.files().create(body=meta, media_body=media, fields="id").execute()
    file_id = arq["id"]
    # A Service Account do GitHub Actions não herda acesso automaticamente
    # a arquivos subidos por login OAuth pessoal, mesmo dentro de pasta
    # compartilhada (erro 404 "File not found" na prática, 28/07/2026) —
    # abre leitura pra "qualquer um com o link". Não é sensível, é só
    # vídeo-fonte bruto, não credencial.
    servico.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    print(f"Enviado: {arquivo.name}")
    print(f"DRIVE_FILE_ID={file_id}")
    return file_id


def main():
    p = argparse.ArgumentParser(description="Sobe vídeo bruto pro Drive (fluxo híbrido)")
    p.add_argument("--arquivo", required=True, help="caminho do vídeo baixado")
    p.add_argument("--pasta-id", required=True, help="ID da pasta pai do Drive")
    p.add_argument("--conta", default="principal",
                   help="conta do Drive a usar (principal | reserva)")
    p.add_argument("--subpasta", default="brutos",
                   help="subpasta a criar dentro do destino; vazio grava direto")
    a = p.parse_args()
    enviar(Path(a.arquivo), a.pasta_id, conta=a.conta, subpasta=a.subpasta)


if __name__ == "__main__":
    main()
