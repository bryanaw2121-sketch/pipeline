"""Manda o vídeo bruto pra lixeira do Drive depois que o corte terminou.

    python limpar_bruto_drive.py --file-id XXXX

Roda como última etapa do cortar_de_bruto.yml, condicionada ao sucesso dos
passos anteriores: bruto de corte que falhou não pode sumir, senão perde-se
a fonte junto com a tentativa.

**Lixeira, não exclusão definitiva.** O Drive segura item na lixeira por 30
dias, então engano dá pra desfazer. `files().delete()` seria irreversível e
não vale o risco pra ganhar 30 dias de antecedência no espaço.

Por que existe: o bruto só precisa viver enquanto o Actions o baixa. Depois
é peso morto — e a conta tem 15 GB no total, com podcast em 1080p custando
0,4 a 0,7 GB cada. Sem isto, o Drive enche em poucas rodadas e o upload
passa a falhar no meio da fila (visto em 28/07 com a Service Account).
"""
import argparse
import json
import os
import sys


def _servico(conta: str = "principal"):
    from googleapiclient.discovery import build

    # Mesma precedência do subir_drive.py: OAuth primeiro (tem a cota da
    # conta), Service Account como reserva. Pra apagar, qualquer um dos dois
    # serve — o que a SA não consegue é ESCREVER conteúdo.
    try:
        import contas_drive
        return contas_drive.servico(contas_drive.conta_por_nome(conta))
    except Exception as e:
        print(f"[aviso] seleção de conta indisponível ({e}); usando fallback.")

    oauth = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if oauth:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        escopos = ["https://www.googleapis.com/auth/drive"]
        cred = Credentials.from_authorized_user_info(json.loads(oauth), escopos)
        if not cred.valid and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        return build("drive", "v3", credentials=cred)

    sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa:
        sys.exit("Falta GOOGLE_OAUTH_TOKEN_JSON ou GOOGLE_SERVICE_ACCOUNT_JSON.")
    from google.oauth2 import service_account
    cred = service_account.Credentials.from_service_account_info(
        json.loads(sa), scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=cred)


def limpar(file_id: str, conta: str = "principal"):
    servico = _servico(conta)
    try:
        info = servico.files().get(fileId=file_id, fields="name,size").execute()
    except Exception as e:
        # Já sumiu, ou sem acesso: não é motivo pra derrubar um corte que deu
        # certo. Avisa e sai limpo.
        print(f"[limpeza] não consegui ler {file_id}: {e}")
        return
    nome = info.get("name", file_id)
    mb = int(info.get("size", 0)) / 1e6
    try:
        servico.files().update(fileId=file_id, body={"trashed": True}).execute()
        print(f"[limpeza] '{nome}' ({mb:.0f} MB) foi pra lixeira do Drive.")
        print("[limpeza] recuperável por 30 dias, se precisar.")
    except Exception as e:
        print(f"[limpeza] falhou ao mandar pra lixeira: {e}")


def main():
    p = argparse.ArgumentParser(description="Manda o bruto pra lixeira do Drive")
    p.add_argument("--file-id", required=True)
    p.add_argument("--conta", default="principal")
    a = p.parse_args()
    limpar(a.file_id, a.conta)


if __name__ == "__main__":
    main()
