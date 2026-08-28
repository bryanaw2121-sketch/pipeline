"""Baixa uma lista de vídeos, sobe cada um bruto pro Drive, e dispara o
corte na nuvem (GitHub Actions) pra cada um — tudo automático depois de
colar a lista.

Uso:
    1. Coloque uma URL por linha em lista_videos.txt (nesta pasta)
    2. python processar_lista.py

    --incluir-longos   processa também os vídeos acima do limite do radar
    --refazer          ignora o registro e processa tudo de novo

Aguenta queda de internet: o download volta de onde parou, e o que já
terminou fica registrado em estado/lista_processados.json — rodar de novo
retoma só o que falta.

Precisa de:
    - GITHUB_TOKEN no .env (Personal Access Token com permissão
      Actions: Read and write, Contents: Read and write)
    - yt-dlp e ffmpeg no PATH, e o resto das dependências do clip_engine
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent
LISTA = RAIZ / "lista_videos.txt"
REGISTRO = RAIZ / "estado" / "lista_processados.json"
TRABALHO = RAIZ / "trabalho" / "lista"
# Fallback só. O destino de verdade vem de contas_drive, por vídeo, pela
# folga de espaço — ver escolher_conta(). Este id é a raiz da conta
# principal e sobrou de quando existia uma conta só.
PASTA_DRIVE = "1uYzc71yxlYvl-aJeTFf0whDuwDXVoXxU"
REPO = "bryanaw2121-sketch/media-assets"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Dois de cada vez: mais que isso satura CPU/RAM (o yt-dlp junta vídeo e
# áudio com ffmpeg no fim de cada download, e é aí que pesa).
SIMULTANEOS = 2

# Radar: acima disso o vídeo é sinalizado e fica de fora por padrão.
# 90min não é número redondo à toa — é onde o Gemini estoura o limite de
# ~10.800 frames e o pipeline cai pra modo só-áudio (ver LEIA_PRIMEIRO.md,
# 28/07/2026). Acima daqui o corte sai analisado sem imagem, então o alerta
# marca a perda de qualidade, não só o tamanho do arquivo.
LIMITE_ALERTA_S = 90 * 60

# Quantas vezes reencarar cada etapa antes de desistir. A espera cresce até
# 5 min, então isso cobre uma queda de internet de mais ou menos uma hora.
TENTATIVAS = 20
ESPERA_MAX_S = 300

_lock_saida = threading.Lock()
_lock_registro = threading.Lock()


def log(msg: str):
    with _lock_saida:
        print(msg, flush=True)


# ---------------------------------------------------------------- registro

def ler_registro() -> dict:
    if not REGISTRO.exists():
        return {}
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Registro corrompido (queda de energia no meio da escrita) não pode
        # impedir a fila de rodar — no pior caso reprocessa.
        log(f"[!] {REGISTRO.name} ilegível, começando do zero.")
        return {}


def marcar(vid: str, dados: dict):
    """Grava um vídeo como concluído. Escreve o arquivo inteiro a cada vez:
    é barato nesse tamanho e sobrevive a interrupção melhor que append."""
    with _lock_registro:
        reg = ler_registro()
        reg[vid] = dados
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        tmp = REGISTRO.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(REGISTRO)


# ------------------------------------------------------------- utilitários

def _roda(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        # Com dois vídeos em paralelo a saída se mistura, então o erro viaja
        # junto da exceção em vez de ir direto pro print.
        raise RuntimeError(f"falhou: {' '.join(cmd[:3])}...\n{r.stderr.strip()}")
    return r.stdout


def insistindo(rotulo: str, funcao):
    """Repete a função até dar certo, com espera crescente. Serve pra queda
    de internet: o yt-dlp retoma o arquivo de onde parou, então cada nova
    tentativa continua o download em vez de recomeçar."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return funcao()
        except Exception as e:
            if tentativa == TENTATIVAS:
                raise
            espera = min(2 ** tentativa, ESPERA_MAX_S)
            log(f"   [{rotulo}] tentativa {tentativa}/{TENTATIVAS} falhou "
                f"({str(e).splitlines()[0][:90]}); nova tentativa em {espera}s")
            time.sleep(espera)


# ----------------------------------------------------------------- etapas

def sondar(url: str) -> dict:
    """Pega id, duração e título sem baixar nada."""
    saida = _roda(["yt-dlp", "--skip-download", "--no-warnings",
                   "--print", "%(id)s\t%(duration)s\t%(title)s", url])
    vid, dur, titulo = saida.strip().splitlines()[0].split("\t", 2)
    return {"id": vid, "duracao": int(float(dur)) if dur != "NA" else 0,
            "titulo": titulo, "url": url}


def baixar(url: str, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    # 1080p quando o vídeo tiver; senão cai pro melhor abaixo disso. Nunca 4K.
    # Acima de 360p o YouTube só serve vídeo e áudio separados, então o ffmpeg
    # precisa estar no PATH pra juntar — sem ele o yt-dlp despenca pra 360p.
    #
    # Prefere H.264 (avc1) + AAC, mesmo pesando mais que o VP9/AV1 que o
    # YouTube serve por padrão em 1080p: o bruto existe só pra ser cortado, e
    # o corte no GitHub Actions é CPU pura (sem NVENC). H.264 decodifica e faz
    # seek muito mais rápido, que é o que o triar/cortar faz o tempo todo.
    # Se não houver avc1 na resolução, o segundo ramo aceita qualquer codec.
    #
    # --continue (padrão) retoma o .part; os retries internos seguram quedas
    # curtas sem nem devolver erro pro insistindo() lá de fora.
    _roda([
        "yt-dlp", "-f",
        "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/"
        "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "--continue",
        "--retries", "infinite",
        "--fragment-retries", "infinite",
        "--retry-sleep", "exp=1:60",
        "-o", str(destino), url,
    ])


def escolher_conta() -> dict:
    """A conta do Drive que recebe ESTE vídeo: a primeira com folga acima da
    reserva, na ordem da lista (contas_drive.escolher).

    Chamada uma vez por vídeo, não uma vez por execução: a principal pode
    encher no meio de uma fila de treze, e o vídeo seguinte precisa ir pra
    reserva sozinho. O vídeo inteiro vive numa conta só — bruto e clipes na
    mesma —, então a conta escolhida aqui viaja junto até o corte na nuvem.

    Se as duas estiverem cheias, PARA. Baixar 400 MB para o upload morrer
    com 403 é o pior desfecho: gasta banda, Gemini e Groq, e não entrega.
    """
    import contas_drive
    conta = contas_drive.escolher()
    if conta is None:
        raise RuntimeError(
            "TODAS as contas do Drive estão cheias (menos de "
            f"{contas_drive.RESERVA_GB} GB livres). Esvazie a lixeira do Drive "
            "— só isso devolve cota — ou autorize outra conta com "
            "autorizar_conta_drive.py. Nada foi baixado à toa.")
    return conta


def subir_bruto(arquivo: Path, conta: dict) -> str:
    # Destino: a pasta RAW da conta — a MESMA que o vigia_raw varre a cada 10
    # minutos na VPS. Até 30/07 isto subia pra `raiz/brutos`, que ninguém
    # vigia: os brutos subiam, o corte não disparava, e sem GITHUB_TOKEN no
    # notebook o vídeo ficava parado sem ninguém perceber. Mandando pra RAW,
    # quem dispara é o vigia, que já tem o token — o notebook não precisa de
    # credencial nenhuma do GitHub.
    saida = _roda([sys.executable, "-X", "utf8", "enviar_bruto_drive.py",
                   "--arquivo", str(arquivo), "--pasta-id", conta["raw"],
                   "--conta", conta["nome"], "--subpasta", ""])
    for linha in saida.splitlines():
        if linha.startswith("DRIVE_FILE_ID="):
            return linha.split("=", 1)[1].strip()
    raise RuntimeError("não achei o DRIVE_FILE_ID na saída")


def disparar_corte(file_id: str, nome_arquivo: str, idioma: str = "pt",
                   conta: dict | None = None):
    if not GITHUB_TOKEN:
        # Não é problema: o bruto foi pra RAW, e o vigia_raw da VPS varre essa
        # pasta a cada 10 minutos e dispara o corte com o token DELE. Este
        # aviso existia como erro e assustava à toa.
        log("   bruto na RAW — o vigia da VPS dispara o corte em até 10 min "
            "(2 por passada, pra não brigar por cota).")
        return
    r = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/cortar_de_bruto.yml/dispatches",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github+json"},
        # `pasta_drive` é a pasta ONDE NASCE a pasta do dia, ou seja o
        # A POSTAR da conta — não a raiz. Passar a raiz (como era aqui até
        # 30/07) fazia os clipes caírem em `tiktok/<dd-mm>` em vez de
        # `A POSTAR/<dd-mm>`, fora de onde o Bryan procura e fora das
        # subpastas `parte NN`. O vigia_raw.py já fazia certo; só este
        # caminho estava fora do padrão.
        json={"ref": "main", "inputs": {
            "drive_file_id": file_id, "nome_arquivo": nome_arquivo,
            "qtd": "8", "idioma": idioma,
            "pasta_drive": (conta or {}).get("a_postar", PASTA_DRIVE),
            "conta": (conta or {}).get("nome", "principal"),
        }},
    )
    if r.status_code != 204:
        raise RuntimeError(f"disparo do corte falhou: {r.status_code} {r.text}")
    log("   corte disparado na nuvem.")


# -------------------------------------------------------------------- fila

def hms(s: int) -> str:
    return f"{s // 3600}h{(s % 3600) // 60:02d}"


def main():
    incluir_longos = "--incluir-longos" in sys.argv
    refazer = "--refazer" in sys.argv

    if not LISTA.exists():
        LISTA.write_text("# uma URL do YouTube por linha\n", encoding="utf-8")
        sys.exit(f"Criei {LISTA} — cole as URLs (uma por linha) e rode de novo.")

    urls = [l.strip() for l in LISTA.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    if not urls:
        sys.exit(f"{LISTA} está vazio — cole as URLs primeiro.")

    registro = {} if refazer else ler_registro()

    # --- radar: sonda tudo antes de baixar qualquer coisa ---------------
    print(f"Sondando {len(urls)} vídeo(s)...\n")
    fila, longos, ja_feitos = [], [], []
    for url in urls:
        try:
            info = sondar(url)
        except Exception as e:
            print(f"  [!] não consegui sondar {url}: {str(e).splitlines()[0][:90]}")
            continue
        if info["id"] in registro:
            ja_feitos.append(info)
        elif info["duracao"] > LIMITE_ALERTA_S and not incluir_longos:
            longos.append(info)
        else:
            fila.append(info)

    if ja_feitos:
        print(f"Já processados antes ({len(ja_feitos)}), pulando:")
        for i in ja_feitos:
            print(f"  - {i['titulo'][:60]}")
        print()

    if longos:
        print(f"{'='*70}\nRADAR: {len(longos)} vídeo(s) acima de "
              f"{hms(LIMITE_ALERTA_S)} — FORA da fila:")
        for i in longos:
            print(f"  ! {hms(i['duracao'])}  {i['titulo'][:55]}")
        print("  Pra incluir mesmo assim: python processar_lista.py --incluir-longos"
              f"\n{'='*70}\n")

    if not fila:
        sys.exit("Nada a fazer.")

    print(f"{len(fila)} vídeo(s) na fila, {SIMULTANEOS} por vez:")
    for i in fila:
        print(f"  - {hms(i['duracao'])}  {i['titulo'][:55]}")
    print()

    total = len(fila)

    def processar(par):
        n, info = par
        vid, nome = info["id"], f"{info['id']}.mp4"
        destino = TRABALHO / nome
        try:
            insistindo(f"{n}/{total} baixar", lambda: baixar(info["url"], destino))
            # A conta é escolhida DEPOIS do download e por vídeo: entre o
            # primeiro e o décimo da fila a principal pode ter enchido, e é
            # aqui que a reserva assume. Ver escolher_conta().
            conta = escolher_conta()
            log(f"   [{n}/{total}] conta do Drive: {conta['nome']}")
            file_id = insistindo(f"{n}/{total} subir",
                                 lambda: subir_bruto(destino, conta))
            insistindo(f"{n}/{total} disparar",
                       lambda: disparar_corte(file_id, nome, conta=conta))
        except Exception as e:
            log(f"[{n}/{total}] [!] falhou: {info['titulo'][:50]}\n      {e}")
            return (info["url"], str(e))
        # Só entra no registro depois das três etapas: se parar no meio, a
        # próxima rodada refaz esse vídeo (o download já estará no disco).
        marcar(vid, {"titulo": info["titulo"], "url": info["url"],
                     "drive_file_id": file_id, "arquivo": str(destino),
                     "conta": conta["nome"],
                     "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
        log(f"[{n}/{total}] ok: {info['titulo'][:50]}")
        return None

    with ThreadPoolExecutor(max_workers=SIMULTANEOS) as pool:
        falhas = [f for f in pool.map(processar, enumerate(fila, 1)) if f]

    print(f"\n{total - len(falhas)}/{total} processados. "
          "Acompanhe o progresso no Telegram.")
    for url, erro in falhas:
        print(f"  FALHOU: {url} -> {erro.splitlines()[0][:120]}")
    if falhas:
        print("\nRode de novo pra retomar só o que faltou.")


if __name__ == "__main__":
    main()
