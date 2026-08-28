"""Ponte: pega o que você aprovou no descobridor-de-virais e corta aqui.

    python importar_aprovados.py --listar          # o que está aprovado
    python importar_aprovados.py                   # corta todos os aprovados
    python importar_aprovados.py --qtd 8           # candidatos por vídeo
    python importar_aprovados.py --so-primeiro     # corta só o de maior nota

Fluxo completo:
    descobridor-de-virais gera CSV  ->  você marca "s" em APROVAR (s/n)
      ->  este script chama main.py pra cada aprovado
      ->  clipes em saida/  ->  publicar_tiktok.py --proximos

Por que não usa o `baixar_aprovados.py` do descobridor: o `main.py` daqui já
baixa com yt-dlp. Baixar duas vezes só gastaria banda e disco.

Marca o CSV com STATUS=cortado, então rodar de novo não reprocessa nada.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

import config

# descobridor-de-virais é irmão do clip_engine dentro de "flux youtube"
DESCOBRIDOR = (config.RAIZ.parent / "descobridor-de-virais"
               / "descobridor-de-virais")

CSVS = ["fila_de_aprovacao.csv", "viral_geral.csv", "oportunidades_podcast.csv"]

COL_APROVAR = "APROVAR (s/n)"
COL_STATUS = "STATUS"


def _linhas(caminho: Path) -> tuple[list[dict], list[str]]:
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        leitor = csv.DictReader(f)
        return list(leitor), (leitor.fieldnames or [])


def _gravar(caminho: Path, linhas: list[dict], campos: list[str]):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def aprovados() -> list[dict]:
    """Linhas com APROVAR=s que ainda não foram cortadas, melhor nota primeiro."""
    if not DESCOBRIDOR.exists():
        sys.exit(f"não encontrei o descobridor em:\n  {DESCOBRIDOR}")

    achados = []
    for nome in CSVS:
        caminho = DESCOBRIDOR / nome
        if not caminho.exists():
            continue
        linhas, _ = _linhas(caminho)
        for i, linha in enumerate(linhas):
            marca = (linha.get(COL_APROVAR) or "").strip().lower()
            estado = (linha.get(COL_STATUS) or "").strip().lower()
            if marca not in ("s", "sim", "y", "yes"):
                continue
            if estado == "cortado":
                continue
            if not (linha.get("url") or "").strip():
                continue
            try:
                nota = float(linha.get("nota") or 0)
            except ValueError:
                nota = 0.0
            achados.append({"csv": nome, "indice": i, "nota": nota,
                            "titulo": linha.get("titulo", ""),
                            "url": linha["url"].strip(),
                            "canal": linha.get("canal", ""),
                            "tier": linha.get("tier", "")})
    achados.sort(key=lambda x: -x["nota"])
    return achados


def _marcar_cortado(nome_csv: str, indice: int, resultado: str):
    caminho = DESCOBRIDOR / nome_csv
    linhas, campos = _linhas(caminho)
    if indice < len(linhas):
        linhas[indice][COL_STATUS] = resultado
        _gravar(caminho, linhas, campos)


def main():
    p = argparse.ArgumentParser(description="Corta os vídeos aprovados no descobridor")
    p.add_argument("--listar", action="store_true", help="só mostra, não corta")
    p.add_argument("--qtd", type=int, default=8,
                   help="candidatos que o Gemini propõe por vídeo (padrão 8: o "
                        "filtro de câmera travada descarta bastante)")
    p.add_argument("--so-primeiro", action="store_true",
                   help="corta só o de maior nota (bom pra testar)")
    p.add_argument("--idioma", default="en", help="idioma da fala (padrão en)")
    a = p.parse_args()

    fila = aprovados()
    if not fila:
        print("Nenhum vídeo aprovado pendente.\n")
        print(f"Marque 's' na coluna '{COL_APROVAR}' num destes CSVs:")
        for nome in CSVS:
            existe = "ok" if (DESCOBRIDOR / nome).exists() else "ainda não gerado"
            print(f"  {DESCOBRIDOR / nome}   [{existe}]")
        return

    print(f"{len(fila)} aprovado(s) pendente(s):\n")
    for i, v in enumerate(fila, 1):
        print(f"  {i:02d}. nota {v['nota']:<6} {v['tier'][:14]:<14} "
              f"{v['titulo'][:45]}")
        print(f"      {v['url']}")
    print()

    if a.listar:
        return

    if a.so_primeiro:
        fila = fila[:1]

    for i, v in enumerate(fila, 1):
        print(f"\n{'='*64}\n[{i}/{len(fila)}] {v['titulo'][:55]}\n{'='*64}")
        r = subprocess.run(
            [sys.executable, "main.py", "--url", v["url"],
             "--idioma", a.idioma, "--qtd", str(a.qtd)],
            cwd=config.RAIZ,
        )
        # 'sem_clipe' quando o vídeo é ruim de imagem (câmera travada) e nada
        # sobra — não é erro de código, e não deve ser tentado de novo à toa
        _marcar_cortado(v["csv"], v["indice"],
                        "cortado" if r.returncode == 0 else "sem_clipe")

    print("\nPronto. Veja os clipes com:")
    print("  python publicar_tiktok.py --fila")


if __name__ == "__main__":
    main()
