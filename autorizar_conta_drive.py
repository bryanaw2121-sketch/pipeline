"""Gera um token OAuth do Drive para MAIS UMA conta Google.

    python autorizar_conta_drive.py --saida token_drive_2.json

Reaproveita o `client_secrets.json` que já existe: o cliente OAuth pertence
ao projeto do Google Cloud, não a uma conta — qualquer conta Google pode
autorizar contra ele. Não é preciso criar projeto novo nem reativar a API.

**Rode numa máquina com navegador** (o Dell, não a VPS): o fluxo abre uma
janela para você escolher a conta e aceitar. Depois é só copiar o arquivo
gerado de volta para o clip_engine.

Se a tela disser "app não verificado", é esperado — o app é seu, em modo de
teste. Clique em "Avançado" → "Acessar (não seguro)". E se der
`access_denied` antes mesmo de pedir permissão, a conta precisa estar
cadastrada como **usuário de teste** na tela de consentimento do projeto
(console.cloud.google.com → APIs e Serviços → Tela de permissão OAuth →
Usuários de teste → Adicionar).
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ESCOPOS = ["https://www.googleapis.com/auth/drive"]


def main():
    p = argparse.ArgumentParser(description="Autoriza mais uma conta Google no Drive")
    p.add_argument("--saida", default="token_drive_2.json",
                   help="nome do arquivo de token a gerar")
    p.add_argument("--client-secrets", default="client_secrets.json")
    a = p.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    segredos = RAIZ / a.client_secrets
    if not segredos.exists():
        sys.exit(f"Não achei {segredos}. Copie o client_secrets.json pra cá.")

    destino = RAIZ / a.saida
    if destino.exists():
        r = input(f"{destino.name} já existe. Sobrescrever? [s/N] ").strip().lower()
        if r != "s":
            sys.exit("Cancelado — nada foi alterado.")

    print("Abrindo o navegador. ESCOLHA A CONTA NOVA, não a que já está em uso.\n")
    flow = InstalledAppFlow.from_client_secrets_file(str(segredos), ESCOPOS)
    cred = flow.run_local_server(port=0, prompt="consent")

    # Mostra de QUAL conta é o token antes de gravar — o engano mais fácil
    # aqui é autorizar de novo a mesma conta e achar que criou a segunda.
    servico = build("drive", "v3", credentials=cred)
    sobre = servico.about().get(fields="user(emailAddress),storageQuota").execute()
    email = sobre["user"]["emailAddress"]
    q = sobre["storageQuota"]
    usado, limite = int(q.get("usage", 0)), int(q.get("limit", 0))

    destino.write_text(cred.to_json(), encoding="utf-8")

    print(f"\nToken gravado: {destino.name}")
    print(f"  conta  : {email}")
    if limite:
        print(f"  espaço : {usado/2**30:.2f} GB usados de {limite/2**30:.0f} GB "
              f"({(limite-usado)/2**30:.2f} GB livres)")
    print("\nSe a conta acima for a MESMA de antes, apague este arquivo e rode de "
          "novo, escolhendo a outra conta na tela de seleção.")


if __name__ == "__main__":
    main()
