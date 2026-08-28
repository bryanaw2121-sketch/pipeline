"""Descobre vídeos candidatos a corte via YouTube Data API v3.

    python descobrir.py                 # top config.FILA_QTD
    python descobrir.py --qtd 10
    python descobrir.py --rodar         # já dispara main.py pra cada um da fila

Critério é hype puro: views, velocidade de views/hora, engajamento.
Fontes: config.CANAIS_MONITORADOS (fixos) + config.TERMOS_HYPE (busca aberta).
Preencha essas duas listas em config.py antes de rodar.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime

import config
from engine import descoberta, status


def _mostrar(titulo: str, itens: list[dict]):
    print(f"\n=== {titulo} ===")
    if not itens:
        print("(nenhum candidato)")
        return
    print(f"{'#':<3} {'nota':<6} {'views':<10} {'views/h':<9} {'eng%':<6} título")
    for i, v in enumerate(itens, 1):
        print(f"{i:<3} {v['nota']:<6} {v['views']:<10} {v['views_por_hora']:<9} "
              f"{v['engajamento_pct']:<6} {v['titulo'][:60]}")


def _atualizar_painel(geral: list[dict], podcasts: list[dict]):
    itens = [
        {"id": v["id"], "url": v["url"], "titulo": v["titulo"], "canal": v.get("canal", ""),
         "nota": v["nota"], "origem": "geral", "status": "pendente"}
        for v in geral
    ] + [
        {"id": v["id"], "url": v["url"], "titulo": v["titulo"], "canal": v.get("canal", ""),
         "nota": v["nota"], "origem": "podcast", "status": "pendente"}
        for v in podcasts
    ]
    status.gravar_fila(itens)


def _rodar(itens: list[dict]):
    for v in itens:
        print(f"\n=== cortando: {v['titulo']} ===")
        status.marcar_item(v["url"], "processando")
        r = subprocess.run([sys.executable, "main.py", "--url", v["url"]])
        if r.returncode == 0:
            descoberta.marcar_canal_cortado(v.get("canal_id", ""))
            status.marcar_item(v["url"], "concluido")
        else:
            status.marcar_item(v["url"], "erro")


def main():
    p = argparse.ArgumentParser(description="Fila de vídeos candidatos a corte")
    p.add_argument("--qtd", type=int, default=config.FILA_QTD)
    p.add_argument("--so-podcasts", action="store_true",
                   help="pula a fila geral, mostra só a seção de podcasts")
    p.add_argument("--rodar", action="store_true",
                   help="depois de montar a fila, chama main.py pra cada vídeo")
    a = p.parse_args()

    geral: list[dict] = []
    if not a.so_podcasts:
        if not config.CANAIS_MONITORADOS and not config.TERMOS_HYPE:
            print("[!] CANAIS_MONITORADOS e TERMOS_HYPE vazios em config.py — pulando fila geral.")
        else:
            print(f"buscando candidatos gerais (janela de {config.JANELA_DIAS} dias)...")
            geral = descoberta.descobrir(a.qtd)

    print(f"buscando podcasts (<= {config.JANELA_HORAS_PODCAST}h, "
          f"{config.VIEWS_MIN_PODCAST:,}-{config.VIEWS_MAX_PODCAST:,} views, "
          f"canal ainda sem corte)...")
    podcasts = descoberta.descobrir_podcasts(a.qtd)

    if not geral and not podcasts:
        print("nenhum candidato encontrado.")
        return

    config.SAIDA.mkdir(parents=True, exist_ok=True)
    caminho = config.SAIDA / f"fila_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    caminho.write_text(
        json.dumps({"geral": geral, "podcasts": podcasts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if geral:
        _mostrar("FILA GERAL", geral)
    _mostrar("PODCASTS (canal ainda sem corte)", podcasts)
    print(f"\nfila salva em {caminho}")

    _atualizar_painel(geral, podcasts)

    if a.rodar:
        _rodar(geral)
        _rodar(podcasts)


if __name__ == "__main__":
    main()
