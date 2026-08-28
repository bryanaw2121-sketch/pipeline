"""Publicação no YouTube — com trava contra vídeo trancado.

O YouTube TRANCA como privado todo vídeo enviado por projeto de API não
auditado, e nesse caso NÃO EXISTE RECURSO: só reenviando na mão. Por isso
este script se recusa a subir em lote antes de provar que o projeto está
liberado.

    python publicar.py --verificar                 # teste com 1 vídeo (faça ISTO primeiro)
    python publicar.py --pasta "saida/2026-07-26_1430/meu-video"
    python publicar.py --pasta "..." --por-dia 3 --hora 18:00

Padrão: sobe PRIVADO e agendado. Público exige --publico explícito.
"""
import argparse, json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from engine import status

ESCOPOS = ["https://www.googleapis.com/auth/youtube.force-ssl",
           "https://www.googleapis.com/auth/youtube.upload"]
SEGREDOS = config.RAIZ / "client_secrets.json"
TOKEN = config.RAIZ / "token.json"
ESTADO = config.RAIZ / ".estado_publicacao.json"


# ------------------------------------------------------------------ auth
def _servico():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("Faltam bibliotecas. Rode:\n"
                 "  pip install google-api-python-client google-auth-oauthlib")

    if not SEGREDOS.exists():
        sys.exit(f"Falta {SEGREDOS.name}. Veja o passo a passo no README "
                 f"(seção Google Cloud).")

    cred = None
    if TOKEN.exists():
        cred = Credentials.from_authorized_user_file(str(TOKEN), ESCOPOS)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            print("Abrindo o navegador para você autorizar o canal...")
            cred = InstalledAppFlow.from_client_secrets_file(
                str(SEGREDOS), ESCOPOS).run_local_server(port=0)
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=cred)


# ------------------------------------------------------------------ estado
def _ler_estado() -> dict:
    if ESTADO.exists():
        try:
            # utf-8-sig: tolera BOM se o arquivo for editado no Windows
            return json.loads(ESTADO.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("   [!] .estado_publicacao.json ilegível — tratando como não verificado")
    return {}


def _gravar_estado(**kw):
    d = _ler_estado()
    d.update(kw)
    ESTADO.write_text(json.dumps(d, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ upload
def _subir(yt, video: Path, corpo: dict) -> str:
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    midia = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=corpo, media_body=midia)

    resp, tentativas = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"\r      enviando... {int(status.progress()*100)}%", end="")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tentativas < 5:
                tentativas += 1
                time.sleep(2 ** tentativas)
                continue
            raise
    print("\r      enviado.            ")
    return resp["id"]


def _capa(yt, video_id: str, jpg: Path):
    from googleapiclient.errors import HttpError
    try:
        yt.thumbnails().set(videoId=video_id, media_body=str(jpg)).execute()
    except HttpError as e:
        # canal sem verificação por telefone não pode definir capa
        print(f"      [!] capa não aplicada: {e.resp.status}")


# ------------------------------------------------------------------ trava
def _verificar() -> bool:
    """Sobe 1 vídeo descartável e tenta torná-lo público.

    Se o projeto não for auditado, o YouTube ignora a mudança e ele continua
    privado — assim descobrimos com 1 vídeo em vez de 50.
    """
    from engine import midia

    print("\n=== TESTE DE LIBERAÇÃO DO PROJETO ===")
    print("Vai subir 1 vídeo descartável (5s, tela preta) e tentar publicá-lo.\n")

    config.TRABALHO.mkdir(parents=True, exist_ok=True)
    teste = config.TRABALHO / "teste_api.mp4"
    midia.roda(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=5",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(teste)])

    yt = _servico()
    vid = _subir(yt, teste, {
        "snippet": {"title": "teste de API - ignorar",
                    "description": "Verificação de auditoria. Será apagado."},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    })
    print(f"      id: {vid}")

    print("      tentando tornar público...")
    yt.videos().update(part="status", body={
        "id": vid,
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }).execute()
    time.sleep(4)

    r = yt.videos().list(part="status", id=vid).execute()
    itens = r.get("items", [])
    atual = itens[0]["status"]["privacyStatus"] if itens else "desconhecido"
    liberado = atual == "public"

    print(f"\n      privacidade após a tentativa: {atual}")
    if liberado:
        print("\n  ✓ PROJETO LIBERADO — pode publicar em lote.\n")
    else:
        print("\n  ✗ PROJETO TRANCADO — não é auditado ainda.")
        print("    NÃO suba em lote: os vídeos nasceriam privados e SEM recurso.")
        print("    Peça a auditoria: https://support.google.com/youtube/contact/yt_api_form")
        print("    Até lá, suba pelo YouTube Studio na mão.\n")

    try:
        yt.videos().delete(id=vid).execute()
        print("      vídeo de teste apagado.")
    except Exception:
        print(f"      [!] apague o vídeo de teste na mão: {vid}")

    teste.unlink(missing_ok=True)
    _gravar_estado(auditado=liberado, verificado_em=datetime.now().isoformat(timespec="seconds"))
    return liberado


# ------------------------------------------------------------------ lote
def publicar_pasta(pasta: Path, por_dia: int, hora: str, publico: bool,
                   so_vertical: bool, forcar: bool):
    """Por padrão sobe os DOIS formatos de cada clipe (vertical Short +
    fullscreen 16:9), quando o fullscreen existir — preferência do usuário,
    não é opcional a menos que --so-vertical seja passado."""
    est = _ler_estado()
    if not est.get("auditado") and not forcar:
        sys.exit(
            "\n  BLOQUEADO: o projeto ainda não passou no teste de liberação.\n"
            "  Rode primeiro:  python publicar.py --verificar\n\n"
            "  Motivo: projeto não auditado faz o YouTube TRANCAR os vídeos\n"
            "  como privados, sem possibilidade de recurso.\n"
            "  (--forcar ignora esta trava, por sua conta e risco)\n"
        )

    clipes = sorted(p for p in pasta.iterdir() if p.is_dir() and (p / "post.json").exists())
    if not clipes:
        sys.exit(f"Nenhum clipe com post.json em {pasta}")

    try:
        h, m = (int(x) for x in hora.split(":"))
    except ValueError:
        sys.exit("--hora deve estar no formato HH:MM (ex: 18:00)")

    # primeira postagem: hoje no horário, ou amanhã se já passou
    base = datetime.now().astimezone().replace(hour=h, minute=m, second=0, microsecond=0)
    if base <= datetime.now().astimezone():
        base += timedelta(days=1)

    yt = _servico()
    print(f"\n{len(clipes)} clipes | {por_dia}/dia a partir de "
          f"{base.strftime('%d/%m %H:%M')} | {'PÚBLICO' if publico else 'privado'}\n")

    enviados = []
    for i, c in enumerate(clipes):
        meta = json.loads((c / "post.json").read_text(encoding="utf-8"))
        quando = base + timedelta(days=i // por_dia,
                                  hours=(i % por_dia) * (6 // max(1, por_dia)))

        formatos = [("short_9x16.mp4", "")]
        if not so_vertical and (c / "fullscreen_16x9.mp4").exists():
            formatos.append(("fullscreen_16x9.mp4", " (tela cheia)"))

        for nome_arq, sufixo_titulo in formatos:
            video = c / nome_arq
            if not video.exists():
                print(f"  [pulado] {c.name}: sem {nome_arq}")
                continue
            _enviar_clipe(yt, c, video, meta, quando, publico, sufixo_titulo, enviados)

    if enviados:
        (pasta / "_publicados.json").write_text(
            json.dumps(enviados, ensure_ascii=False, indent=2), encoding="utf-8")

        origem = pasta / "_origem.json"
        if origem.exists():
            url = json.loads(origem.read_text(encoding="utf-8")).get("url", "")
            status.marcar_item(url, "publicado", publicado_em=time.time(),
                               qtd_publicados=len(enviados))

    print(f"\n{len(enviados)} enviados. Registro em _publicados.json")


def _enviar_clipe(yt, c: Path, video: Path, meta: dict, quando: datetime,
                  publico: bool, sufixo_titulo: str, enviados: list):
    corpo = {
        "snippet": {
            "title": ((meta.get("titulo") or c.name)[:100 - len(sufixo_titulo)] + sufixo_titulo),
            "description": meta.get("descricao") or "",
            "tags": (meta.get("tags") or [])[:15],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "private",   # sempre privado no envio
            "selfDeclaredMadeForKids": False,
        },
    }
    # publishAt só vale com privacyStatus private — é assim que se agenda
    if publico:
        corpo["status"]["publishAt"] = quando.astimezone(timezone.utc)\
            .isoformat().replace("+00:00", "Z")

    print(f"  [{c.name}]{sufixo_titulo} {corpo['snippet']['title'][:55]}")
    print(f"      {'agendado p/ ' + quando.strftime('%d/%m %H:%M') if publico else 'privado (sem agendamento)'}")
    try:
        vid = _subir(yt, video, corpo)
        if (c / "capa.jpg").exists() and not sufixo_titulo:
            _capa(yt, vid, c / "capa.jpg")
        print(f"      https://youtu.be/{vid}")
        enviados.append({"id": vid, "clipe": c.name + sufixo_titulo,
                         "quando": quando.isoformat() if publico else None})
    except Exception as e:
        print(f"      [ERRO] {e}")


def main():
    p = argparse.ArgumentParser(description="Publica os cortes no YouTube")
    p.add_argument("--verificar", action="store_true",
                   help="testa com 1 vídeo se o projeto está liberado (FAÇA ISTO PRIMEIRO)")
    p.add_argument("--pasta", help="pasta de saída gerada pelo main.py")
    p.add_argument("--por-dia", type=int, default=2)
    p.add_argument("--hora", default="18:00", help="horário da 1ª postagem (HH:MM)")
    p.add_argument("--publico", action="store_true",
                   help="agenda publicação. Sem isto, sobe privado e você revisa")
    p.add_argument("--so-vertical", action="store_true",
                   help="publica só o 9:16 (por padrão sobe os dois formatos, "
                        "vertical + tela cheia, quando o tela cheia existir)")
    p.add_argument("--forcar", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.verificar:
        _verificar()
        return
    if not a.pasta:
        p.error("informe --pasta ou use --verificar")

    pasta = Path(a.pasta)
    if not pasta.exists():
        sys.exit(f"não encontrei: {pasta}")
    publicar_pasta(pasta, max(1, a.por_dia), a.hora, a.publico,
                   a.so_vertical, a.forcar)


if __name__ == "__main__":
    main()
