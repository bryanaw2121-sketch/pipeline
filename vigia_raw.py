"""Vigia a pasta RAW do Drive e dispara o corte na nuvem pra cada vídeo
novo que aparecer — fecha o ciclo sem ninguém precisar apertar nada.

    python vigia_raw.py              # fica rodando, checa a cada 5 min
    python vigia_raw.py --uma-vez    # checa uma vez e sai (pra Agendador)
    python vigia_raw.py --listar     # só mostra o que RAW tem e o que já foi

O que ele considera "novo": arquivo de vídeo em RAW cujo ID não está em
estado/raw_vistos.json. O nome não entra na conta — renomear no Drive não
faz reprocessar, e dois arquivos de mesmo nome não se confundem.

Por que ele mexe em permissão: a Service Account do GitHub Actions não
enxerga arquivo subido por login OAuth pessoal, nem dentro de pasta
compartilhada (404 "File not found", visto em 28/07/2026). Vídeo que você
arrastou pro Drive na mão cai nesse caso, então o vigia abre leitura por
link antes de disparar — mesma coisa que o enviar_bruto_drive.py já faz.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent
REGISTRO = RAIZ / "estado" / "raw_vistos.json"
CLIENT_SECRETS = RAIZ / "client_secrets.json"
TOKEN = RAIZ / "token_drive.json"

PASTA_RAW = "1gUK_okgnHg-V1MDyM90ffnFe4dqIYV2g"
# Onde os clipes prontos aterrissam: dentro de 'A POSTAR' nasce a pasta do
# dia (ex: 28-07). Apontar pra raiz 'tiktok' faria a pasta do dia aparecer
# ao lado de RAW, misturando entrada com saída.
PASTA_DRIVE = "1k8fh9qZPxEkr64IK1TIpucdSstVDxDFO"  # A POSTAR
REPO = "bryanaw2121-sketch/media-assets"
WORKFLOW = "cortar_de_bruto.yml"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

INTERVALO_S = 300

# Voltou pra 8 em 29/07/2026, depois que o Bryan aprovou a rodada de prova
# ("rodou liso, legenda boa, tudo certo"). Ficou em "1" durante o teste das
# cinco mudanças de qualidade — fonte 1080p, tracking em rampa, legenda a
# 30%, punch-in cíclico e volume -14 LUFS.
QTD_CLIPES = "8"

# Quantos cortes disparar por varredura. O resto espera a próxima passada
# (10 min), então uma leva de 15 vídeos entra aos poucos em vez de toda de
# uma vez.
#
# Por que existe: em 29/07 o vigia disparou ~15 runs juntos e cinco
# morreram com "Drive storage quota exceeded" DEPOIS de cortar. A primeira
# tentativa de conserto foi um `concurrency` group no workflow — e foi pior:
# o GitHub só guarda UM run pendente por grupo e CANCELA os demais, então
# sete runs sumiram sem rodar. Limitar aqui, na origem, não perde nada:
# o que não coube fica no Drive e entra na próxima passada.
# Era 2 e continuava rapido demais pra cota do Gemini: em 22/08/2026 dez
# brutos na RAW viraram dez runs em ~40 min, e NOVE falharam com todas as
# chaves esgotadas. Um por passada (10 min) da' 6 por hora no pior caso, e
# na pratica bem menos, porque cada corte leva ~83 min com qtd=5.
MAX_POR_PASSADA = 1
# Idioma da FALA do video fonte, nao o da legenda de saida. Era "pt" e
# isso quebrava calado: `main.processar` tem
#   precisa_traduzir = (traduzir or dublar) and idioma != "pt"
# entao com "pt" num video em ingles o run nao traduz, nao narra e NAO
# DUBLA — sai com o audio original. Medido no run #120 de 07/08/2026
# (rise_of_humanoids, ingles, despachado pelo vigia): zero traducoes,
# e mesmo assim o run terminou "success".
# O acervo do nicho e esmagadoramente em ingles (ver o radar), entao "en"
# e o padrao certo. Fonte em portugues precisa de disparo na mao com
# idioma=pt — ai a traducao e a dublagem sao puladas de proposito.
IDIOMA = "en"
# 1 = padrão do canal (Inter Black). 2 = réplica da referência Erica Bruno
# (Poppins Bold, corpo variável) — ver engine/legendas.py. Trocar aqui muda
# TODO disparo desta máquina; pra escolher por vídeo, disparar manual pelo
# GitHub Actions com o input estilo_legenda.
ESTILO_LEGENDA = "1"

SCOPES = ["https://www.googleapis.com/auth/drive"]
EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


# ------------------------------------------------------------------ drive

def servico():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

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


def _filhos(drive, pasta_id: str) -> list[dict]:
    """Itens diretos de uma pasta, paginando até o fim."""
    itens, pagina = [], None
    while True:
        r = drive.files().list(
            q=f"'{pasta_id}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,size,mimeType,modifiedTime)",
            orderBy="modifiedTime", pageToken=pagina, pageSize=100,
        ).execute()
        itens.extend(r.get("files", []))
        pagina = r.get("nextPageToken")
        if not pagina:
            return itens


def videos_todas_contas() -> list[dict]:
    """Vídeos novos nas pastas RAW de TODAS as contas configuradas.

    Cada item leva o nome da conta onde está. O vídeo é processado inteiro
    na conta onde o bruto vive — bruto e clipes na mesma conta — então essa
    informação viaja até o workflow. Ver contas_drive.py.
    """
    import contas_drive
    achados = []
    for c in contas_drive.CONTAS:
        try:
            drive = contas_drive.servico(c)
        except Exception as e:
            print(f"[!] conta '{c['nome']}' inacessível: {str(e)[:90]}")
            continue
        for v in videos_em_raw(drive, raiz=c["raw"]):
            v["conta"] = c["nome"]
            achados.append(v)
    return achados


def videos_em_raw(drive, profundidade_max: int = 3, raiz: str = PASTA_RAW) -> list[dict]:
    """Vídeos na RAW, **inclusive dentro de subpastas**.

    Antes só olhava os filhos diretos e pulava pasta. Em 28/07/2026 o Bryan
    subiu os vídeos em `RAW/2026-07-28/` e o vigia não enxergava nada —
    reportava "nada novo" indefinidamente, sem erro nenhum, que é o pior
    tipo de falha: silenciosa.

    Desce até `profundidade_max` níveis. O teto existe porque cada pasta
    custa uma chamada de API: sem ele, uma árvore grande (ou um atalho
    circular do Drive) viraria enxurrada de requisições.
    """
    achados: list[dict] = []
    vistos: set[str] = set()
    fila = [(raiz, "")]               # (id da pasta, caminho legível)

    for _ in range(profundidade_max):
        if not fila:
            break
        proxima: list[tuple[str, str]] = []
        for pasta_id, caminho in fila:
            if pasta_id in vistos:    # atalho circular não trava o vigia
                continue
            vistos.add(pasta_id)
            for f in _filhos(drive, pasta_id):
                if f["mimeType"].endswith("folder"):
                    proxima.append((f["id"], f"{caminho}{f['name']}/"))
                elif Path(f["name"]).suffix.lower() in EXTS:
                    f["caminho"] = caminho    # ex.: "2026-07-28/", só pro log
                    achados.append(f)
        fila = proxima

    return achados


def liberar_leitura(drive, file_id: str):
    """Abre leitura por link pra Service Account do Actions conseguir baixar.
    Se já estiver liberado, o Drive só devolve a permissão existente."""
    try:
        drive.permissions().create(
            fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    except Exception as e:
        print(f"   [!] não consegui abrir leitura ({e}); o corte pode dar 404")


# --------------------------------------------------------------- registro

def ler_registro() -> dict:
    if not REGISTRO.exists():
        return {}
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"[!] {REGISTRO.name} ilegível, tratando tudo como novo.")
        return {}


def marcar(file_id: str, dados: dict):
    reg = ler_registro()
    reg[file_id] = dados
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRO.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REGISTRO)


# ----------------------------------------------------------------- github

def _a_postar(conta: str) -> str:
    """A POSTAR da conta indicada. O vídeo inteiro fica numa conta só, então
    os clipes não podem cair no A POSTAR de outra."""
    try:
        import contas_drive
        return contas_drive.conta_por_nome(conta)["a_postar"]
    except Exception:
        return PASTA_DRIVE


def disparar(file_id: str, nome: str, conta: str = "principal",
             estilo_legenda: str = ESTILO_LEGENDA):
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "Falta GITHUB_TOKEN no .env — sem ele não dá pra disparar o corte. "
            "Crie um PAT com Actions: Read and write, Contents: Read and write."
        )
    r = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github+json"},
        json={"ref": "main", "inputs": {
            "drive_file_id": file_id, "nome_arquivo": nome,
            "qtd": QTD_CLIPES, "idioma": IDIOMA,
            "estilo_legenda": estilo_legenda,
            "pasta_drive": _a_postar(conta), "conta": conta,
        }},
        timeout=30,
    )
    if r.status_code != 204:
        raise RuntimeError(f"disparo falhou: {r.status_code} {r.text[:300]}")


def corte_em_andamento() -> bool:
    """Ja' existe um corte rodando na nuvem?

    Por que existe: `MAX_POR_PASSADA` limita quantos saem POR PASSADA, mas a
    passada e' de 10 min e cada corte leva ~83 min com qtd=5. Sem esta
    checagem o vigia enfileira ~6 por hora enquanto o pipeline consome menos
    de 1 — foi exatamente assim que 10 brutos viraram 10 runs simultaneos em
    22/08/2026 e NOVE falharam com as chaves do Gemini esgotadas.

    Na duvida (erro de rede, API fora), devolve True: e' melhor atrasar um
    corte 10 minutos do que torrar a cota do dia inteiro.
    """
    if not GITHUB_TOKEN:
        return False
    try:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                     "Accept": "application/vnd.github+json"},
            params={"per_page": 10}, timeout=30)
        r.raise_for_status()
        return any(x["status"] in ("queued", "in_progress", "waiting", "requested", "pending")
                   for x in r.json().get("workflow_runs", []))
    except Exception as e:
        print(f"[!] nao consegui checar runs em andamento ({str(e)[:70]}); "
              "seguro o disparo por esta passada")
        return True


# ------------------------------------------------------------------ ciclo

def uma_passada(drive) -> int:
    reg = ler_registro()
    novos = [v for v in videos_todas_contas() if v["id"] not in reg]
    if not novos:
        return 0
    if corte_em_andamento():
        # O marcador [espera] existe pro wrapper agendado distinguir "fila
        # parada de proposito" de "nao ha' nada novo". Sem ele a mensagem some:
        # main() ainda imprime "Nada novo." depois deste return, e o wrapper
        # casava so' essa string. Mesmo defeito que o [!] ja' tinha tido.
        print(f"[espera] {len(novos)} na fila, mas ja' ha' corte rodando "
              "— espero a proxima passada.")
        return 0
    espera = max(0, len(novos) - MAX_POR_PASSADA)
    novos = novos[:MAX_POR_PASSADA]
    print(f"{len(novos)} vídeo(s) novo(s) em RAW"
          + (f" (+{espera} na próxima passada)" if espera else "") + ":")
    for v in novos:
        tam = int(v.get("size", 0)) / 2**30
        print(f"  - [{v.get('conta','?')}] {v.get('caminho','')}{v['name']} ({tam:.2f} GB)")
        try:
            disparar(v["id"], v["name"], v.get("conta", "principal"))
        except Exception as e:
            # Não marca: na próxima passada ele tenta de novo.
            print(f"   [!] falhou, fica pra próxima passada: {e}")
            continue
        marcar(v["id"], {"nome": v["name"], "tamanho": v.get("size"),
                         "conta": v.get("conta", "principal"),
                         "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
        print("   corte disparado na nuvem.")
    return len(novos)


def auditar() -> list[dict]:
    """Vídeos que o vigia deu como despachados mas que NUNCA foram cortados.

    Existe porque o vigia marca no momento do DISPARO, não da conclusão —
    qualquer coisa que dê errado depois deixa o vídeo em limbo silencioso:
    ocupa espaço na RAW, consta como processado, e nunca virou clipe.

    Aconteceu de verdade em 29/07/2026: um `concurrency` group no workflow
    cancelou sete runs enfileirados (o GitHub guarda só UM pendente por
    grupo), e mais quatro morreram por cota ou erro do Gemini. Os onze
    ficaram invisíveis até alguém cruzar as duas listas na mão.

    O cruzamento é com `estado/videos_trabalhados.json`, que registra o que
    de fato saiu cortado — e pega qualquer causa, não só cancelamento.
    """
    import re
    reg = ler_registro()
    trabalhados = RAIZ / "estado" / "videos_trabalhados.json"
    if not trabalhados.exists():
        print("[!] videos_trabalhados.json não existe — rode registro_videos.py --sincronizar")
        return []
    feitos = {k for k, v in json.loads(trabalhados.read_text(encoding="utf-8")).items()
              if v.get("cortado")}

    pendentes = []
    for v in videos_todas_contas():
        m = re.search(r"\[([A-Za-z0-9_-]{11})\]", v["name"])
        yt = m.group(1) if m else ""
        if v["id"] in reg and yt not in feitos and not reg[v["id"]].get("obs"):
            v["yt"] = yt
            pendentes.append(v)
    return pendentes


def main():
    p = argparse.ArgumentParser(description="Vigia a pasta RAW do Drive")
    p.add_argument("--uma-vez", action="store_true", help="checa uma vez e sai")
    p.add_argument("--listar", action="store_true", help="só mostra o estado atual")
    p.add_argument("--auditar", action="store_true",
                   help="acha vídeo marcado como despachado que nunca virou clipe")
    p.add_argument("--devolver", action="store_true",
                   help="com --auditar: desmarca os achados pra entrarem na fila")
    p.add_argument("--intervalo", type=int, default=INTERVALO_S)
    a = p.parse_args()

    if a.auditar:
        pend = auditar()
        if not pend:
            print("Nada em limbo — tudo que foi despachado virou clipe.")
            return
        print(f"{len(pend)} vídeo(s) despachado(s) mas NUNCA cortado(s):")
        for v in pend:
            print(f"  [{v.get('conta','?')}] {v['name'][:62]}")
        if not a.devolver:
            print("\nPra devolver à fila: --auditar --devolver")
            return
        reg = ler_registro()
        for v in pend:
            reg.pop(v["id"], None)
        REGISTRO.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n{len(pend)} devolvido(s) — entram {MAX_POR_PASSADA} por varredura.")
        return

    drive = servico()

    if a.listar:
        reg = ler_registro()
        vids = videos_todas_contas()
        print(f"RAW tem {len(vids)} vídeo(s):")
        for v in vids:
            marca = "já processado" if v["id"] in reg else "NOVO"
            print(f"  [{marca}] [{v.get('conta','?')}] {v['name']}")
        return

    if a.uma_vez:
        n = uma_passada(drive)
        print("Nada novo." if not n else f"{n} disparado(s).")
        return

    print(f"Vigiando RAW a cada {a.intervalo}s. Ctrl+C pra parar.")
    while True:
        try:
            if not uma_passada(drive):
                print(f"[{time.strftime('%H:%M:%S')}] nada novo.")
        except KeyboardInterrupt:
            print("\nParei.")
            return
        except Exception as e:
            # Rede caiu, token expirou, Drive fora do ar: espera e insiste.
            print(f"[!] passada falhou ({e}); tento de novo no próximo ciclo.")
        time.sleep(a.intervalo)


if __name__ == "__main__":
    main()
