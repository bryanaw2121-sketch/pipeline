"""Lê os CSVs do descobridor-de-virais e formata pro Telegram.

O descobridor é um projeto irmão (`flux youtube/descobridor-de-virais`) com
3 radares que geram CSV. Aqui só lemos o resultado — quem gera é lá.
"""
import csv
import subprocess
import sys
from pathlib import Path

import config

DESCOBRIDOR = (config.RAIZ.parent / "descobridor-de-virais"
               / "descobridor-de-virais")

RADARES = [
    ("radar_viral_geral.py", "viral_geral.csv", "VIRAIS GERAIS"),
    ("descobrir_virais.py", "fila_de_aprovacao.csv", "NICHO (IA/tech)"),
    ("radar_podcasts.py", "oportunidades_podcast.csv", "PODCASTS sem corte"),
]


def _linhas(nome_csv: str) -> list[dict]:
    caminho = DESCOBRIDOR / nome_csv
    if not caminho.exists():
        return []
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _nota(linha: dict) -> float:
    try:
        return float(linha.get("nota") or 0)
    except ValueError:
        return 0.0


def melhores(nome_csv: str, n: int = 8) -> list[dict]:
    """Top `n` por nota, ignorando o que já foi aprovado/cortado."""
    linhas = [l for l in _linhas(nome_csv)
              if (l.get("STATUS") or "").strip().lower() != "cortado"]
    linhas.sort(key=_nota, reverse=True)
    return linhas[:n]


def resumo_telegram(n: int = 6) -> str:
    """Lista numerada dos melhores candidatos.

    O número de cada linha é o que o /cortar aceita — mesma ordenação do
    `_todos_ordenados()`, senão /cortar 3 cortaria outro vídeo.
    """
    todos = _todos_ordenados()
    if not todos:
        return ("Sem candidatos. Rode /radar pra buscar "
                "(ou os radares ainda não rodaram).")

    linhas = [f"TOP {min(n, len(todos))} de {len(todos)} candidatos.",
              "Use /cortar N pra cortar um deles.", ""]
    for i, l in enumerate(todos[:n], 1):
        tier = (l.get("tier") or l.get("cortes_oficiais") or "").strip()
        marca = " [QUENTE]" if tier.startswith("A") or "NÃO" in tier else ""
        idi = l.get("idioma")
        linhas.append(f"{i}. [{_nota(l):.0f}]{marca} {(l.get('titulo') or '')[:56]}")
        detalhe = "   " + (l.get("canal") or "")[:26]
        if idi and idi != "?":
            detalhe += f" · {idi}"
        linhas.append(detalhe)
        linhas.append(f"   {l.get('url','')}")
        linhas.append("")
    return "\n".join(linhas)


def _todos_ordenados() -> list[dict]:
    """Todos os candidatos dos 3 radares, melhor nota primeiro.

    A numeração do /lista sai daqui, então /cortar 3 aponta pro mesmo item
    que o /lista mostrou como 3.
    """
    juntos = []
    for _, csv_nome, _ in RADARES:
        juntos += [l for l in _linhas(csv_nome)
                   if (l.get("STATUS") or "").strip().lower() != "cortado"]
    juntos.sort(key=_nota, reverse=True)
    return juntos


def url_por_numero(n: int) -> str:
    """URL do n-ésimo item da lista (1-based). Estoura IndexError se não existe."""
    todos = _todos_ordenados()
    if n < 1 or n > len(todos):
        raise IndexError(n)
    url = (todos[n - 1].get("url") or "").strip()
    if not url:
        raise IndexError(n)
    return url


def cortar_url(url: str, qtd: int = 8, idioma: str = "en") -> str:
    """Roda o main.py nessa URL. Devolve a pasta de saída (ou o motivo da falha)."""
    antes = {p.name for p in config.SAIDA.iterdir()} if config.SAIDA.exists() else set()
    r = subprocess.run(
        [sys.executable, "main.py", "--url", url, "--idioma", idioma,
         "--qtd", str(qtd)],
        cwd=config.RAIZ, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=3600)
    if r.returncode != 0:
        saida = (r.stdout or "") + (r.stderr or "")
        if "câmera travada" in saida or "camera travada" in saida:
            raise RuntimeError("todos os trechos tinham câmera travada — "
                               "nada aproveitável nesse vídeo")
        ultimas = [l for l in saida.strip().splitlines() if l.strip()][-3:]
        raise RuntimeError(" | ".join(ultimas)[:300] or "erro desconhecido")

    novas = ({p.name for p in config.SAIDA.iterdir()} - antes) if config.SAIDA.exists() else set()
    return next(iter(novas), "saida/ (veja a pasta mais recente)")


def rodar_radares() -> str:
    """Roda os 3 radares. Devolve um resumo do que cada um achou."""
    if not DESCOBRIDOR.exists():
        return f"não encontrei o descobridor em {DESCOBRIDOR}"

    saida = []
    for script, csv_nome, rotulo in RADARES:
        alvo = DESCOBRIDOR / script
        if not alvo.exists():
            saida.append(f"{rotulo}: script não existe")
            continue
        r = subprocess.run([sys.executable, script], cwd=DESCOBRIDOR,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
        total = len(_linhas(csv_nome))
        if r.returncode == 0:
            saida.append(f"{rotulo}: {total} encontrados")
        else:
            erro = (r.stderr or "").strip().splitlines()
            saida.append(f"{rotulo}: FALHOU ({erro[-1][:80] if erro else '?'})")
    return "\n".join(saida)
