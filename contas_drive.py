"""As contas do Drive e a regra de qual usar.

Modelo escolhido pelo Bryan em 29/07/2026: **um vídeo vive inteiro numa conta
só**. O bruto entra na RAW dela, os clipes saem no A POSTAR dela, e ele entra
na conta que precisar para baixar o que quiser. Quando a conta ativa encosta
no limite, a próxima assume — sem migrar nada do que já está lá.

Isso evita o problema que derrubaria o desenho anterior: rastrear conta por
arquivo. Aqui basta saber **onde o bruto está**, e o resto do fluxo daquele
vídeo acontece na mesma conta.

Por que não bastou compartilhar pasta entre contas (testado em 29/07): no
Drive a cota é de **quem cria o arquivo**, não de quem hospeda a pasta. A
conta 1 subiu 60 MB dentro de uma pasta da conta 2 e os 60 MB saíram da cota
da conta 1. Compartilhar dá acesso, não empresta espaço.
"""
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Reserva de segurança. A conta para de receber vídeo novo quando o livre cai
# abaixo disto — o espaço restante fica para os clipes dos cortes que já estão
# na fila terminarem. Em 29/07 cinco runs cortaram com sucesso e falharam no
# upload por cota: o trabalho de Gemini e Groq foi perdido na última etapa, e
# é exatamente isso que a reserva existe para evitar.
RESERVA_GB = 3.0

CONTAS = [
    {
        "nome": "principal",
        "token": "token_drive.json",
        "email": "fatoseacontecimentoscontato@gmail.com",
        "raiz": "1uYzc71yxlYvl-aJeTFf0whDuwDXVoXxU",   # tiktok
        "raw": "1gUK_okgnHg-V1MDyM90ffnFe4dqIYV2g",
        "a_postar": "1k8fh9qZPxEkr64IK1TIpucdSstVDxDFO",
        "secret": "GOOGLE_OAUTH_TOKEN_JSON",
    },
    {
        "nome": "reserva",
        "token": "token_drive_2.json",
        "email": "cryptozpin@gmail.com",
        "raiz": "1yrNBlKXw8WExdY-sCMsYhtva5RU5HX_s",
        "raw": "1l7fT_wRsdsWfAtDsOkmTG4q3qq-oyVT8",
        "a_postar": "1aM22tjWvoWLTv9v1PrICUzk0_763xcUK",
        "secret": "GOOGLE_OAUTH_TOKEN_JSON_2",
    },
    {
        "nome": "labzirkonart",
        "token": "token_drive_3.json",
        "email": "zirkonartlaboratorio@gmail.com",
        "raiz": "15_jJUWfjvPdmrdaju5Me2b67OO7_jZpA",
        "raw": "1yt0JvJMeqiRkyDF9IS4vl2QOV-Wtt0yd",
        "a_postar": "1QoJwIYvZ-gOYvaxBXOY7xjX4JTJkWa_Z",
        "secret": "GOOGLE_OAUTH_TOKEN_JSON_3",
    },
]

SCOPES = ["https://www.googleapis.com/auth/drive"]


def servico(conta: dict):
    """Cliente do Drive autenticado como a conta indicada.

    Aceita o token por variável de ambiente (nome em `secret`) — é assim que
    o GitHub Actions recebe — ou pelo arquivo local, para uso na VPS.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    bruto = os.getenv(conta["secret"])
    if bruto:
        cred = Credentials.from_authorized_user_info(json.loads(bruto), SCOPES)
    else:
        caminho = RAIZ / conta["token"]
        if not caminho.exists():
            raise FileNotFoundError(f"Falta {caminho} e a variável {conta['secret']}")
        cred = Credentials.from_authorized_user_file(str(caminho), SCOPES)
    if not cred.valid and cred.expired and cred.refresh_token:
        cred.refresh(Request())
    return build("drive", "v3", credentials=cred)


def livre_gb(conta: dict) -> float:
    """Espaço livre, em GB. Devolve 0 se a conta estiver inacessível — assim
    uma conta com token quebrado é simplesmente pulada, em vez de derrubar
    a escolha inteira."""
    try:
        q = servico(conta).about().get(fields="storageQuota").execute()["storageQuota"]
        if "limit" not in q:
            return float("inf")          # conta sem limite
        return (int(q["limit"]) - int(q["usage"])) / 2 ** 30
    except Exception:
        return 0.0


def conta_por_nome(nome: str) -> dict:
    for c in CONTAS:
        if c["nome"] == nome:
            return c
    raise KeyError(f"conta desconhecida: {nome}")


def escolher(minimo_gb: float = RESERVA_GB) -> dict | None:
    """Primeira conta com folga acima da reserva, na ordem da lista.

    Ordem fixa de propósito, não a mais vazia: assim o sistema esgota a
    principal antes de espalhar arquivo entre contas, e o Bryan sabe onde
    procurar sem adivinhar.
    """
    for c in CONTAS:
        if livre_gb(c) >= minimo_gb:
            return c
    return None


def situacao() -> list[dict]:
    """Retrato das contas, para log e diagnóstico."""
    out = []
    for c in CONTAS:
        livre = livre_gb(c)
        out.append({**c, "livre_gb": livre, "apta": livre >= RESERVA_GB})
    return out


if __name__ == "__main__":
    print(f"reserva mínima: {RESERVA_GB} GB\n")
    for c in situacao():
        marca = "APTA " if c["apta"] else "CHEIA"
        print(f"  [{marca}] {c['nome']:<10} {c['email']:<40} {c['livre_gb']:6.2f} GB livres")
    ativa = escolher()
    print(f"\nconta ativa agora: {ativa['nome'] if ativa else 'NENHUMA — todas cheias'}")
