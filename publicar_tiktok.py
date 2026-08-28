"""Publicação no TikTok via Content Posting API.

    python publicar_tiktok.py --autorizar         # 1x, gera token.json do TikTok
    python publicar_tiktok.py --pasta "saida/2026-07-26_1430/meu-video" --publico

Igual ao publicar.py: app novo/não auditado só publica em modo privado
(SELF_ONLY) — a TikTok exige revisão ("Content Posting API - Direct Post")
pra liberar postagem pública de verdade. Sem essa auditoria, --publico
ainda assim sai como rascunho/privado, sem aviso — por isso o --verificar.
"""
import argparse, json, os, sys, time
from pathlib import Path

import requests
from dotenv import load_dotenv

import config
from engine import telegram

load_dotenv()

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8721/callback")
PORTA = 8721

TOKEN = config.RAIZ / "token_tiktok.json"
ESTADO = config.RAIZ / ".estado_publicacao_tiktok.json"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
# `video.list` (Display API) entrou em 31/07/2026: é ele que devolve
# view_count, like_count, comment_count e share_count por vídeo — os quatro
# números que o desempenho.py espera e que até agora vinham de CSV exportado
# à mão. Ver metricas_tiktok.py.
#
# ⚠️ Escopo NÃO se acrescenta a token existente. Depois que o app for
# aprovado com o Display API, é obrigatório refazer o OAuth do zero:
#     ren token_tiktok.json token_tiktok.json.bak
#     python publicar_tiktok.py --autorizar
# Sem isso o token velho continua sem `video.list` e o metricas_tiktok.py
# devolve `scope_not_authorized` (401).
ESCOPOS = "user.info.basic,video.publish,video.upload,video.list"


def _hashtag(tag: str) -> str:
    """Hashtag válida: sem espaço (quebraria em duas) e sem acento (quem
    busca digita sem). Mesma regra do `_hashtag` em main.py."""
    import unicodedata
    sem_acento = (unicodedata.normalize("NFKD", tag)
                  .encode("ascii", "ignore").decode("ascii"))
    return "#" + "".join(ch for ch in sem_acento if ch.isalnum())


def _exigir_credenciais():
    if not CLIENT_KEY or not CLIENT_SECRET:
        sys.exit("Falta TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET no .env")


# ------------------------------------------------------------------ auth
def _autorizar():
    """Fluxo OAuth2 com servidor local — mesma ideia do InstalledAppFlow do
    Google. Precisa que REDIRECT_URI esteja cadastrada no app do TikTok for
    Developers (Login Kit > Redirect URI)."""
    import hashlib
    import http.server
    import secrets
    import urllib.parse

    _exigir_credenciais()
    codigo = {}

    # PKCE — exigido pelo TikTok desde a atualização do Login Kit.
    # ATENÇÃO: o TikTok foge do padrão OAuth aqui — o code_challenge é o
    # SHA256 em HEX, não em base64url. Com base64url a autorização passa no
    # navegador e só falha na troca do código ("Code verifier or code
    # challenge is invalid"), o que engana: parece que deu certo.
    verificador = secrets.token_hex(48)          # 96 chars, dentro do 43-128
    desafio = hashlib.sha256(verificador.encode()).hexdigest()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            codigo["valor"] = qs.get("code", [None])[0]
            codigo["erro"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Autorizado! Pode fechar esta aba." if codigo["valor"] else "Falhou — veja o terminal."
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *a):
            pass

    url = (f"{AUTH_URL}?client_key={CLIENT_KEY}&scope={ESCOPOS}"
           f"&response_type=code&redirect_uri={REDIRECT_URI}&state=flux"
           f"&code_challenge={desafio}&code_challenge_method=S256")
    print(f"\nAbra esse link e autorize a conta do TikTok:\n\n{url}\n")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    servidor = http.server.HTTPServer(("localhost", PORTA), _Handler)
    print(f"Aguardando autorização em http://localhost:{PORTA}/callback ...")
    servidor.handle_request()

    if not codigo.get("valor"):
        sys.exit(f"Autorização falhou: {codigo.get('erro') or 'sem código recebido'}")

    r = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": codigo["valor"],
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verificador,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    dados = r.json()
    if "access_token" not in dados:
        sys.exit(f"TikTok não devolveu access_token: {dados}")

    TOKEN.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nToken salvo em {TOKEN.name}. Conta @{dados.get('open_id', '?')} autorizada.")


def _token_valido() -> str:
    """Devolve access_token válido, renovando via refresh_token se preciso."""
    _exigir_credenciais()
    if not TOKEN.exists():
        sys.exit("Sem token_tiktok.json — rode primeiro:\n  python publicar_tiktok.py --autorizar")
    dados = json.loads(TOKEN.read_text(encoding="utf-8"))

    r = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": dados["refresh_token"],
    })
    if r.status_code == 200:
        novo = r.json()
        if "access_token" in novo:
            TOKEN.write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
            return novo["access_token"]
    # refresh falhou — token de acesso original pode ainda estar válido (curto, ~24h)
    return dados["access_token"]


# ------------------------------------------------------------------ upload
CHUNK_MIN = 5 * 1024 * 1024        # 5 MB — mínimo exigido pelo TikTok
CHUNK_MAX = 64 * 1024 * 1024       # 64 MB — máximo por chunk


def _plano_chunks(tam: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) aceitos pelo TikTok.

    Regra deles: chunk entre 5MB e 64MB, e o ÚLTIMO chunk leva o resto (pode
    passar de 64MB? não — por isso o número de chunks é arredondado pra cima).
    Arquivo menor que 5MB vai inteiro num chunk só.

    Sem isso, vídeo acima de 64MB falha com `invalid_params: The chunk size is
    invalid`, que não diz o que está errado de verdade.
    """
    if tam <= CHUNK_MAX:
        return tam, 1
    total = (tam + CHUNK_MAX - 1) // CHUNK_MAX      # arredonda pra cima
    chunk = tam // total                            # divide igual entre eles
    if chunk < CHUNK_MIN:
        chunk, total = CHUNK_MIN, max(1, tam // CHUNK_MIN)
    return chunk, total


def _enviar_arquivo(access_token: str, video: Path, url_init: str,
                    corpo: dict) -> str:
    tam = video.stat().st_size
    chunk, total = _plano_chunks(tam)
    corpo = dict(corpo)
    corpo["source_info"] = dict(corpo.get("source_info", {}),
                                source="FILE_UPLOAD", video_size=tam,
                                chunk_size=chunk, total_chunk_count=total)

    r = requests.post(url_init, json=corpo, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    })
    r.raise_for_status()
    resp = r.json().get("data", {})
    upload_url = resp.get("upload_url")
    publish_id = resp.get("publish_id")
    if not upload_url:
        raise RuntimeError(f"TikTok não devolveu upload_url: {r.json()}")

    if total > 1:
        print(f"      {tam/1048576:.0f} MB em {total} partes de "
              f"~{chunk/1048576:.0f} MB")
    with open(video, "rb") as fh:
        for i in range(total):
            ini = i * chunk
            # o último chunk leva todo o resto, senão sobrariam bytes
            fim = (tam - 1) if i == total - 1 else (ini + chunk - 1)
            fh.seek(ini)
            pedaco = fh.read(fim - ini + 1)
            r2 = requests.put(upload_url, data=pedaco, headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {ini}-{fim}/{tam}",
            })
            r2.raise_for_status()
    return publish_id


def _publicar_video(access_token: str, video: Path, titulo: str, publico: bool) -> str:
    """Direct Post — exige app auditado ('Content Posting API - Direct Post')
    pra sair público de verdade; sem auditoria, o TikTok força SELF_ONLY."""
    tam = video.stat().st_size
    chunk = min(tam, 64 * 1024 * 1024)
    corpo = {
        "post_info": {
            "title": titulo[:150],
            "privacy_level": "PUBLIC_TO_EVERYONE" if publico else "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": tam,
            "chunk_size": chunk,
            "total_chunk_count": 1,
        },
    }
    return _enviar_arquivo(access_token, video, INIT_URL, corpo)


def _enviar_rascunho(access_token: str, video: Path) -> str:
    """Modo Sandbox / sem revisão: manda o vídeo pra caixa de entrada do
    TikTok como rascunho. Não precisa de app auditado nem de escopo
    'video.publish' aprovado — só 'video.upload'. O usuário dá 1 toque em
    'Postar' no app do TikTok pra publicar de verdade.

    ATENÇÃO (medido em 26/07/2026): o TikTok limita a ~5 rascunhos PENDENTES
    e o contador só zera quando o vídeo é POSTADO. Excluir o rascunho no app
    NÃO devolve a vaga — o status continua `SEND_TO_USER_INBOX` na API e a
    vaga fica presa. Nunca instrua o usuário a excluir rascunho pra "abrir
    espaço"; ele tem que postar.
    """
    tam = video.stat().st_size
    chunk = min(tam, 64 * 1024 * 1024)
    corpo = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": tam,
            "chunk_size": chunk,
            "total_chunk_count": 1,
        },
    }
    return _enviar_arquivo(access_token, video, INBOX_INIT_URL, corpo)


def _status(access_token: str, publish_id: str) -> dict:
    r = requests.post(STATUS_URL, json={"publish_id": publish_id}, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    })
    r.raise_for_status()
    return r.json().get("data", {})


# ------------------------------------------------------------------ fila
def _enviados() -> set[str]:
    p = config.REGISTRO_ENVIADOS_TIKTOK
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")))


def _marcar_enviado(clipe: Path):
    p = config.REGISTRO_ENVIADOS_TIKTOK
    p.parent.mkdir(parents=True, exist_ok=True)
    atual = _enviados()
    atual.add(_chave(clipe))
    p.write_text(json.dumps(sorted(atual), ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _chave(clipe: Path) -> str:
    """Identidade estável do clipe: <lote>/<nome do clipe>."""
    return f"{clipe.parent.parent.name}/{clipe.name}"


def fila_pendente() -> list[Path]:
    """Clipes prontos que ainda não foram pro rascunho do TikTok.

    Pula os lotes de `config.LOTES_IGNORADOS` (legenda estourada) e ordena
    por nota decrescente, pro melhor material sair primeiro.
    """
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
    return [c for _, c in achados]


# ------------------------------------------------------------------ lote
def publicar_pasta(pasta: Path, direto: bool, publico: bool, so_vertical: bool):
    """Por padrão manda como RASCUNHO (caixa de entrada do TikTok) — funciona
    em Sandbox, sem revisão. Passe --direto só depois que o app for auditado
    pra 'Direct Post', senão o TikTok força SELF_ONLY silenciosamente."""
    if direto and publico:
        print("[!] --publico pedido, mas só funciona de verdade depois que o app "
              "passar pela revisão 'Direct Post' do TikTok. App não auditado "
              "publica como privado (SELF_ONLY) mesmo assim, sem erro.\n")
    if not direto:
        print("Modo rascunho (Sandbox): os vídeos vão pra caixa de entrada do "
              "TikTok — abra o app e toque em 'Postar' em cada um.\n")

    access_token = _token_valido()
    if (pasta / "post.json").exists():
        # apontou direto pra pasta de UM clipe (é o que dá pra copiar da tela
        # mais fácil) em vez da pasta do lote — publica só ele
        clipes = [pasta]
    else:
        clipes = sorted(p for p in pasta.iterdir()
                        if p.is_dir() and (p / "post.json").exists())
    if not clipes:
        sys.exit(f"Nenhum clipe com post.json em {pasta}")

    enviados = []
    for c in clipes:
        enviados += _enviar_um(access_token, c, direto, publico, so_vertical)

    if enviados:
        (pasta / "_publicados_tiktok.json").write_text(
            json.dumps(enviados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(enviados)} enviados. Registro em _publicados_tiktok.json")


def legenda_do_clipe(clipe: Path) -> str:
    """Legenda pronta pra colar no app: título + hashtags válidas.

    Hashtag não pode ter espaço nem acento — "#Elon Musk" viraria "#Elon"
    mais o texto solto "Musk".
    """
    meta = json.loads((clipe / "post.json").read_text(encoding="utf-8"))
    tags = " ".join(_hashtag(t) for t in (meta.get("tags") or [])[:5] if t)
    return f"{meta.get('titulo') or clipe.name} {tags}".strip()


def _enviar_um(access_token: str, c: Path, direto: bool, publico: bool,
               so_vertical: bool) -> list[dict]:
    titulo = legenda_do_clipe(c)
    formatos = [("short_9x16.mp4", "")]
    if not so_vertical and (c / "fullscreen_16x9.mp4").exists():
        formatos.append(("fullscreen_16x9.mp4", " (tela cheia)"))

    feitos = []
    for nome_arq, sufixo in formatos:
        video = c / nome_arq
        if not video.exists():
            print(f"  [pulado] {c.name}: sem {nome_arq}")
            continue
        print(f"  [{c.name}]{sufixo} {titulo[:55]}")
        try:
            if direto:
                publish_id = _publicar_video(access_token, video, titulo + sufixo, publico)
            else:
                publish_id = _enviar_rascunho(access_token, video)
                print(f"      legenda (cole no app ao postar): {titulo}")
            print(f"      publish_id={publish_id}")
            # acompanha até terminar: uma consulta só costuma pegar ainda em
            # PROCESSING_UPLOAD, o que não diz se deu certo
            st = {}
            for _ in range(24):                     # ~2 min de paciência
                time.sleep(5)
                st = _status(access_token, publish_id)
                estado = st.get("status", "?")
                print(f"      status: {estado}")
                if estado in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"):
                    break
            if st.get("status") == "FAILED":
                raise RuntimeError(f"TikTok recusou: {st}")
            feitos.append({"clipe": c.name + sufixo, "publish_id": publish_id,
                           "legenda_sugerida": titulo})
        except Exception as e:
            print(f"      [ERRO] {e}")
    if feitos:
        _marcar_enviado(c)
    return feitos


def mandar_legendas(n: int = config.TIKTOK_LOTE) -> int:
    """Manda só as LEGENDAS da fila pro Telegram, sem tocar no TikTok.

    Existe porque a API do TikTok bloqueia envio com frequência
    (`spam_risk_too_many_pending_share`) e a legenda não tem nada a ver com
    isso — dá pra postar o vídeo na mão e ainda ter a legenda no celular.
    """
    fila = fila_pendente()
    if not fila:
        telegram.enviar("Fila vazia — nada pendente.")
        return 0

    telegram.enviar(f"Legendas dos próximos {min(n, len(fila))} "
                    f"(de {len(fila)} na fila). Uma mensagem por vídeo:")
    for i, c in enumerate(fila[:n], 1):
        arquivo = c / "short_9x16.mp4"
        telegram.enviar(f"[{i}] {c.parent.parent.name} / {c.name}\n"
                        f"arquivo: {arquivo}\n\n{legenda_do_clipe(c)}")
    print(f"{min(n, len(fila))} legendas mandadas pro Telegram.")
    return min(n, len(fila))


def enviar_proximos(n: int = config.TIKTOK_LOTE, avisar: bool = True) -> list[dict]:
    """Manda os próximos `n` clipes da fila que ainda não foram pro rascunho,
    e manda a legenda de cada um pro Telegram (pro usuário copiar no celular).

    É o que o comando /mais do Telegram chama: o usuário posta os pendentes no
    app, manda /mais, e os próximos entram na fila.
    """
    fila = fila_pendente()
    if not fila:
        msg = "Fila vazia — todos os clipes prontos já foram pro rascunho."
        print(msg)
        if avisar:
            telegram.enviar(msg)
        return []

    print(f"{len(fila)} clipes na fila. Mandando os {min(n, len(fila))} melhores.\n")
    token = _token_valido()
    enviados, falhas = [], []
    for c in fila[:n]:
        feitos = _enviar_um(token, c, direto=False, publico=False, so_vertical=True)
        if feitos:
            enviados += feitos
            # legenda separada, uma mensagem por clipe: no celular é muito
            # mais fácil tocar e copiar do que achar o trecho num bloco só
            if avisar:
                telegram.enviar(legenda_do_clipe(c))
        else:
            falhas.append(c)

    restam = len(fila) - len(enviados)
    print(f"\n{len(enviados)} enviados. Restam {restam} na fila.")

    if avisar:
        if enviados:
            telegram.enviar(
                f"{len(enviados)} vídeo(s) no rascunho do TikTok. "
                f"As legendas vieram acima, uma por vídeo.\n"
                f"Restam {restam} na fila — mande /mais depois de postar.")
        elif falhas:
            telegram.enviar(
                "Não consegui mandar: o TikTok recusou com "
                "'spam_risk_too_many_pending_share'. Isso acontece quando há "
                "envios recentes demais — poste os pendentes e espere um pouco "
                "antes de mandar /mais de novo.")
    return enviados


def main():
    p = argparse.ArgumentParser(description="Publica os cortes no TikTok")
    p.add_argument("--autorizar", action="store_true",
                   help="1ª vez: autoriza a conta do TikTok (abre navegador)")
    p.add_argument("--pasta", help="pasta de saída gerada pelo main.py "
                                   "(ou de um clipe específico)")
    p.add_argument("--proximos", nargs="?", type=int, const=config.TIKTOK_LOTE,
                   metavar="N",
                   help=f"manda os próximos N da fila que ainda não foram "
                        f"(padrão {config.TIKTOK_LOTE}), pulando os já enviados")
    p.add_argument("--fila", action="store_true",
                   help="só lista o que está na fila, sem enviar")
    p.add_argument("--direto", action="store_true",
                   help="Direct Post em vez de rascunho — só funciona com app auditado")
    p.add_argument("--publico", action="store_true",
                   help="com --direto: tenta publicar público (exige app auditado)")
    p.add_argument("--com-horizontal", action="store_true",
                   help="também sobe o 16:9, se existir. Padrão é só o 9:16 — "
                        "TikTok é vertical-first, horizontal rende mal lá")
    a = p.parse_args()

    if a.autorizar:
        _autorizar()
        return

    if a.fila:
        fila = fila_pendente()
        print(f"{len(fila)} clipes na fila (melhor nota primeiro):\n")
        for i, c in enumerate(fila, 1):
            nota = json.loads((c / "post.json").read_text(encoding="utf-8")).get("nota")
            print(f"  {i:02d}. nota {nota}  {c.parent.parent.name}  {c.name[:55]}")
        return

    if a.proximos:
        enviar_proximos(a.proximos)
        return

    if not a.pasta:
        p.error("informe --pasta, --proximos, --fila ou --autorizar")

    pasta = Path(a.pasta)
    if not pasta.exists():
        sys.exit(f"não encontrei: {pasta}")
    publicar_pasta(pasta, a.direto, a.publico, not a.com_horizontal)


if __name__ == "__main__":
    main()
