"""Registro ÚNICO de todo vídeo-fonte que o projeto já trabalhou.

    python registro_videos.py --listar
    python registro_videos.py --sincronizar     # varre GitHub e Drive
    python registro_videos.py --tem <id_youtube>

Por que existe (pedido do Bryan em 29/07/2026): "mantenha uma lista de todos
os vídeos que já trabalhamos para nunca corrermos o risco de trabalhar com
vídeos repetidos".

Até agora esse conhecimento estava espalhado em três lugares que não se
conversam, cada um com um recorte diferente e nenhum completo:

  - `estado/raw_vistos.json` — o que o vigia despachou, por ID do **Drive**
  - `descobridor-de-virais/radar_*.csv` — o que os radares acharam
  - `lista_videos.txt` — o que está na fila agora, e é sobrescrito a cada leva

Nenhum deles responde "este vídeo do YouTube já virou clipe?". Este arquivo
responde, e é indexado pelo **ID do YouTube** — que é o único identificador
estável: o ID do Drive muda a cada novo upload do mesmo vídeo, e o nome do
arquivo muda com renomeação.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# console do Windows costuma abrir em cp1252, que não tem caractere "→"
# usado no print de resumo — força UTF-8 pra não derrubar o processo depois
# de já ter salvo o registro (visto em 04/08/2026, --sincronizar).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent
REGISTRO = RAIZ / "estado" / "videos_trabalhados.json"
REPO = "bryanaw2121-sketch/media-assets"


def carregar() -> dict:
    if not REGISTRO.exists():
        return {}
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"[!] {REGISTRO.name} ilegível — começando do zero.")
        return {}


def salvar(reg: dict):
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRO.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(REGISTRO)


def anotar(yt_id: str, **campos):
    """Acrescenta ou atualiza um vídeo. Nunca apaga o que já existe —
    reprocessamento só soma informação."""
    reg = carregar()
    item = reg.setdefault(yt_id, {})
    for k, v in campos.items():
        if v not in (None, "", 0):
            item[k] = v
    item["clipes"] = max(int(item.get("clipes", 0)), int(campos.get("clipes", 0) or 0))
    salvar(reg)
    return item


def _id_youtube(texto: str) -> str:
    """Acha o ID do YouTube dentro de um nome de arquivo ou URL.

    O yt-dlp grava como `Titulo [ID].mp4`, então o ID viaja junto do arquivo
    até o Drive — é o que permite religar o vídeo à origem depois.
    """
    m = re.search(r"\[([A-Za-z0-9_-]{11})\]", texto or "")
    if m:
        return m.group(1)
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", texto or "")
    return m.group(1) if m else ""


def sincronizar():
    """Reconstrói o registro a partir do histórico real: runs do GitHub
    (o que foi cortado, com que resultado) e a lista atual do Drive."""
    import requests
    from dotenv import load_dotenv
    load_dotenv(override=True)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        sys.exit("Falta GITHUB_TOKEN no .env.")
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    reg = carregar()
    novos = 0
    runs = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100",
        headers=h, timeout=60).json().get("workflow_runs", [])
    print(f"varrendo {len(runs)} runs do GitHub...")

    for x in runs:
        if x.get("status") != "completed":
            continue
        try:
            j = requests.get(
                f"https://api.github.com/repos/{REPO}/actions/runs/{x['id']}/jobs",
                headers=h, timeout=60).json()
            log = requests.get(
                f"https://api.github.com/repos/{REPO}/actions/jobs/{j['jobs'][0]['id']}/logs",
                headers=h, timeout=60).text
        except Exception:
            continue

        m = re.search(r"\[1/5\] fonte: (.+?)\s+\(", log)
        nome = m.group(1).strip() if m else ""
        yt = _id_youtube(nome)
        if not yt:
            continue

        clipes = len(re.findall(r"\[4/5\] clipe \d+/", log))
        item = reg.setdefault(yt, {})
        if not item:
            novos += 1
        item["titulo"] = item.get("titulo") or nome
        item.setdefault("runs", [])
        if x["run_number"] not in item["runs"]:
            item["runs"].append(x["run_number"])
        item["clipes"] = max(int(item.get("clipes", 0)), clipes)
        if x["conclusion"] == "success":
            item["cortado"] = True
            item["quando"] = item.get("quando") or x["run_started_at"][:10]
        else:
            item.setdefault("cortado", False)
            item["ultima_falha"] = x["conclusion"]

    salvar(reg)
    feitos = sum(1 for v in reg.values() if v.get("cortado"))
    print(f"registro: {len(reg)} vídeos ({novos} novos nesta varredura), "
          f"{feitos} já cortados com sucesso")
    print(f"→ {REGISTRO}")


def main():
    p = argparse.ArgumentParser(description="Registro de vídeos já trabalhados")
    p.add_argument("--listar", action="store_true")
    p.add_argument("--sincronizar", action="store_true")
    p.add_argument("--tem", metavar="ID_YOUTUBE")
    a = p.parse_args()

    if a.sincronizar:
        return sincronizar()

    reg = carregar()
    if a.tem:
        item = reg.get(a.tem)
        print(f"{a.tem}: " + ("JÁ TRABALHADO — " + json.dumps(item, ensure_ascii=False)
                              if item else "novo, nunca processado"))
        return

    if not reg:
        print("Registro vazio. Rode --sincronizar para reconstruir do histórico.")
        return
    print(f"{len(reg)} vídeo(s) no registro:\n")
    for yt, v in sorted(reg.items(), key=lambda kv: kv[1].get("quando") or ""):
        marca = "✅" if v.get("cortado") else "❌"
        print(f"  {marca} {yt}  {v.get('clipes',0):>2} clipe(s)  "
              f"{v.get('quando','?')}  {(v.get('titulo') or '')[:48]}")


if __name__ == "__main__":
    main()
