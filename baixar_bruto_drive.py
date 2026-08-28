"""Baixa um arquivo do Drive pelo ID — usado pelo workflow do GitHub
Actions no fluxo híbrido (download local, resto na nuvem).

    python baixar_bruto_drive.py --file-id XXXX --destino fonte.mp4

Usa Service Account (GOOGLE_SERVICE_ACCOUNT_JSON), igual ao subir_drive.py.
"""
import argparse
import json
import os
import sys


def _servico(conta: str = "principal"):
    """Cliente do Drive para a conta indicada.

    O bruto vive na conta onde foi subido, e o vídeo inteiro é processado
    nela — então quem dispara o corte informa qual é. OAuth primeiro: a
    Service Account lê, mas não escreve (não tem cota de armazenamento), e
    manter as duas etapas na mesma credencial evita surpresa.
    """
    from googleapiclient.discovery import build

    try:
        import contas_drive
        return contas_drive.servico(contas_drive.conta_por_nome(conta))
    except Exception as e:
        # Sem o contas_drive (ou conta desconhecida) cai no caminho antigo,
        # pra não quebrar quem chamar sem passar --conta.
        print(f"[aviso] seleção de conta indisponível ({e}); usando fallback.")

    oauth = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if oauth:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        cred = Credentials.from_authorized_user_info(
            json.loads(oauth), ["https://www.googleapis.com/auth/drive"])
        if not cred.valid and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        return build("drive", "v3", credentials=cred)

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        sys.exit("Falta GOOGLE_OAUTH_TOKEN_JSON ou GOOGLE_SERVICE_ACCOUNT_JSON.")
    from google.oauth2 import service_account
    info = json.loads(sa_json)
    scopes = ["https://www.googleapis.com/auth/drive"]
    cred = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build("drive", "v3", credentials=cred)


def baixar(file_id: str, destino: str, conta: str = "principal"):
    from googleapiclient.http import MediaIoBaseDownload

    servico = _servico(conta)
    req = servico.files().get_media(fileId=file_id)
    with open(destino, "wb") as f:
        downloader = MediaIoBaseDownload(f, req)
        concluido = False
        while not concluido:
            status, concluido = downloader.next_chunk()
            if status:
                print(f"  {int(status.progress() * 100)}%")
    print(f"Baixado: {destino}")


def main():
    p = argparse.ArgumentParser(description="Baixa arquivo do Drive pelo ID")
    p.add_argument("--file-id", required=True)
    p.add_argument("--destino", required=True)
    p.add_argument("--conta", default="principal",
                   help="conta do Drive onde o bruto está (ver contas_drive.py)")
    a = p.parse_args()
    baixar(a.file_id, a.destino, a.conta)


if __name__ == "__main__":
    main()
