"""Puxa as métricas dos vídeos publicados pela Display API do TikTok.

    python metricas_tiktok.py              # lista os vídeos e os números
    python metricas_tiktok.py --gravar     # grava em estado/desempenho.json
    python metricas_tiktok.py --json       # saída crua, para depurar

Por que existe
--------------
Até 31/07/2026 a medição do canal era 100% manual: exportar CSV no TikTok
Studio e importar com `desempenho.py --importar`. Isso funciona, mas depende
do Bryan lembrar de fazer, e por isso o `desempenho.py` **nunca recebeu um
número** entre 26/07 e 30/07.

Esta é a via automática: `/v2/video/list/` devolve, por vídeo publicado,
`view_count`, `like_count`, `comment_count` e `share_count` — exatamente os
quatro campos que o `desempenho.py` espera.

O escopo `video.list`
---------------------
Exige o produto **Display API** habilitado no app e o escopo `video.list`
concedido. O token de 31/07 tem só `user.info.basic, video.publish,
video.upload` — este comando devolve erro de escopo até o app ser aprovado e
o OAuth refeito (**escopo não se acrescenta a token existente**).

E é justamente por isso que este arquivo existe ANTES da aprovação: o revisor
do TikTok exige ver **todos** os escopos pedidos funcionando no vídeo de
demonstração. Pedir `video.list` sem ter o que demonstrar é recusa na certa —
está na tabela de motivos do `AUDITORIA_TIKTOK.md`.

⚠️ Em Sandbox o TikTok devolve dados completos para o usuário de teste do
próprio app. Isso já enganou duas sessões: **só confie no resultado com
credencial de produção**.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

import config
from publicar_tiktok import _token_valido

LIST_URL = "https://open.tiktokapis.com/v2/video/list/"

# Os quatro que o desempenho.py usa, mais o que ajuda a identificar o vídeo.
CAMPOS = ["id", "title", "video_description", "create_time", "duration",
          "view_count", "like_count", "comment_count", "share_count"]

MEDICOES = config.ESTADO / "desempenho.json" if hasattr(config, "ESTADO") \
    else config.RAIZ / "estado" / "desempenho.json"


def _pagina(token: str, cursor=None, maximo: int = 20) -> dict:
    corpo = {"max_count": maximo}
    if cursor:
        corpo["cursor"] = cursor
    req = urllib.request.Request(
        f"{LIST_URL}?fields={','.join(CAMPOS)}",
        data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def listar(maximo: int = 100) -> list[dict]:
    """Todos os vídeos publicados, paginando. Devolve [] em erro de escopo,
    com a mensagem explicada — não levanta exceção, para o comando servir de
    diagnóstico do próprio escopo."""
    token = _token_valido()
    videos, cursor = [], None
    while len(videos) < maximo:
        try:
            d = _pagina(token, cursor)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")[:400]
            print(f"[X] HTTP {e.code}: {corpo}")
            if "scope" in corpo.lower() or e.code in (401, 403):
                print("\n    Falta o escopo 'video.list'. Isso significa que:")
                print("    - o produto Display API não está no app, OU")
                print("    - o token atual foi emitido antes do escopo existir.")
                print("    Escopo NÃO se acrescenta a token existente: depois de")
                print("    aprovado, rode 'python publicar_tiktok.py --autorizar'.")
            return []
        dados = d.get("data", {})
        videos += dados.get("videos", [])
        cursor = dados.get("cursor")
        if not dados.get("has_more"):
            break
    return videos[:maximo]


def _linha(v: dict) -> str:
    titulo = (v.get("title") or v.get("video_description") or "")[:44]
    return (f"{v.get('view_count', 0):>7} {v.get('like_count', 0):>6} "
            f"{v.get('comment_count', 0):>5} {v.get('share_count', 0):>6}  {titulo}")


def main() -> int:
    p = argparse.ArgumentParser(description="Métricas via Display API do TikTok")
    p.add_argument("--gravar", action="store_true",
                   help="grava em estado/desempenho.json (formato do desempenho.py)")
    p.add_argument("--json", action="store_true", help="saída crua")
    p.add_argument("--max", type=int, default=100)
    a = p.parse_args()

    videos = listar(a.max)
    if not videos:
        return 1

    if a.json:
        print(json.dumps(videos, ensure_ascii=False, indent=2))
        return 0

    print(f"{len(videos)} vídeo(s) publicado(s)\n")
    print(f"{'views':>7} {'likes':>6} {'com':>5} {'share':>6}  título")
    print("-" * 72)
    for v in sorted(videos, key=lambda x: -(x.get("view_count") or 0)):
        print(_linha(v))

    tv = sum(v.get("view_count") or 0 for v in videos)
    tl = sum(v.get("like_count") or 0 for v in videos)
    ts = sum(v.get("share_count") or 0 for v in videos)
    print("-" * 72)
    print(f"{tv:>7} {tl:>6} {'':>5} {ts:>6}  TOTAL")

    if a.gravar:
        # Mesma forma que o desempenho.py grava no --importar: chave -> campos.
        atual = {}
        if MEDICOES.exists():
            try:
                atual = json.loads(MEDICOES.read_text(encoding="utf-8"))
            except Exception:                                    # noqa: BLE001
                atual = {}
        for v in videos:
            atual[v["id"]] = {
                "titulo": v.get("title") or v.get("video_description") or "",
                "views": v.get("view_count") or 0,
                "curtidas": v.get("like_count") or 0,
                "comentarios": v.get("comment_count") or 0,
                "compartilhamentos": v.get("share_count") or 0,
                "origem": "display_api",
            }
        MEDICOES.parent.mkdir(parents=True, exist_ok=True)
        MEDICOES.write_text(json.dumps(atual, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\n→ {MEDICOES} ({len(videos)} vídeo(s))")
        print("  agora: python desempenho.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
