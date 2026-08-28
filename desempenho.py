"""Loop de feedback: liga o que PUBLICAMOS ao que ACONTECEU.

Por que existe
--------------
Hoje publicamos e não aprendemos nada. Cada `post.json` já carrega a
taxonomia do clipe (`marcador_viral`, `arquetipo`, `emocao_dominante`,
`forca_gancho`...), mas nada disso é confrontado com o resultado real. Sem
isso a taxonomia é enfeite.

Com 30 dias de números, ela vira critério de seleção — e aí a gente sabe o
que funciona **pro nosso público**, não pro público de um guru de YouTube.
Nenhum canal do corpus tem esse loop; é a vantagem que dá pra ter.

Uso
---
    python desempenho.py --pendentes              # o que falta medir
    python desempenho.py --modelo-csv             # gera CSV pra preencher
    python desempenho.py --importar medicoes.csv  # lê de volta
    python desempenho.py --add "2026-07-26_2346/fonte/01_nota95_..." \
        --views 12000 --curtidas 800 --comentarios 45 --compartilhamentos 120
    python desempenho.py --relatorio              # o que aprendemos

Os números saem do TikTok Studio (Analytics de cada post). É entrada
manual porque o app não é auditado e a API não devolve métrica — 3 posts
por dia são 3 linhas por dia.
"""
import argparse
import csv
import io
import json
import statistics
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import config  # noqa: E402

MEDICOES = config.ESTADO / "desempenho.json" if hasattr(config, "ESTADO") \
    else Path(__file__).resolve().parent / "estado" / "desempenho.json"
ENVIADOS = Path(__file__).resolve().parent / "estado" / "enviados_tiktok.json"
SAIDA = config.SAIDA

DIMENSOES = ["tipo_conteudo", "emocao_dominante", "dinamica",
             "marcador_viral", "arquetipo"]
SUBNOTAS = ["forca_gancho", "compartilhabilidade", "independencia",
            "intensidade_emocional", "valor_social"]

# Abaixo disso não se conclui nada — o relatório mostra mas não ordena.
MIN_AMOSTRA = 3

CAMPOS_CSV = ["chave", "titulo", "views", "curtidas", "comentarios",
              "compartilhamentos", "retencao_pct", "seguidores_ganhos"]


# ------------------------------------------------------------------ dados
def chave_de(caminho: str) -> str:
    """Chave canônica `<lote>/<clipe>`.

    Os caminhos reais têm 3 níveis (`<lote>/<fonte>/<clipe>`), mas o
    `enviados_tiktok.json` grava só 2, sem o nível da fonte. Normalizar
    pelos extremos casa os dois lados sem depender do nome do meio.
    """
    partes = [x for x in str(caminho).replace("\\", "/").split("/") if x]
    if len(partes) < 2:
        return "/".join(partes)
    return f"{partes[0]}/{partes[-1]}"


def clipes() -> dict[str, dict]:
    """Todo clipe produzido, indexado pela chave canônica."""
    out = {}
    for p in sorted(SAIDA.glob("*/*/*/post.json")) + sorted(SAIDA.glob("*/*/post.json")):
        rel = str(p.parent.relative_to(SAIDA)).replace("\\", "/")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                              # noqa: BLE001
            continue
        d["_caminho"] = rel
        out[chave_de(rel)] = d
    return out


def carregar(caminho: Path, padrao):
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:                              # noqa: BLE001
            pass
    return padrao


def gravar_medicoes(d: dict):
    MEDICOES.parent.mkdir(parents=True, exist_ok=True)
    MEDICOES.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def publicados() -> set[str]:
    env = carregar(ENVIADOS, [])
    itens = env if isinstance(env, list) else list(env)
    return {chave_de(x) for x in itens}


# ------------------------------------------------------------------ análise
def taxa(m: dict, campo: str) -> float | None:
    v = m.get("views") or 0
    return (m.get(campo) or 0) / v if v else None


def agrupar(dados: list[tuple[dict, dict]], dim: str):
    """dados = [(post, medicao)]. Agrupa pelo valor da dimensão."""
    g: dict[str, list] = {}
    for post, med in dados:
        val = post.get(dim)
        if not val:
            continue
        g.setdefault(str(val), []).append((post, med))
    return g


def resumo_grupo(itens):
    views = [m.get("views") or 0 for _, m in itens]
    comp = [m.get("compartilhamentos") or 0 for _, m in itens]
    taxas = [t for t in (taxa(m, "compartilhamentos") for _, m in itens) if t is not None]
    return {
        "n": len(itens),
        "views_mediana": statistics.median(views) if views else 0,
        "compart_mediana": statistics.median(comp) if comp else 0,
        "taxa_compart": statistics.mean(taxas) if taxas else 0.0,
    }


def relatorio(todos: dict, meds: dict):
    dados = [(todos[k], meds[k]) for k in meds if k in todos and meds[k].get("views")]
    n = len(dados)
    print(f"\n{'='*70}\nRELATÓRIO DE DESEMPENHO — {n} posts medidos\n{'='*70}")
    if not n:
        print("\nNenhuma medição ainda. Use --modelo-csv pra começar.")
        return

    views = [m.get("views") or 0 for _, m in dados]
    print(f"\nviews: mediana {statistics.median(views):,.0f} · "
          f"min {min(views):,} · max {max(views):,}")

    curtos = [p for p, _ in dados if (p.get("duracao_s") or 0) < 60]
    if curtos:
        print(f"[!] {len(curtos)} dos {n} posts têm menos de 60s — esses NÃO "
              f"monetizam (regra oficial). Não servem pra ler RPM.")

    if n < MIN_AMOSTRA * 2:
        print(f"\n*** AMOSTRA PEQUENA ({n} posts). Nada abaixo é conclusão — "
              f"é sinal fraco. Com 3 posts/dia, ~2 semanas dão base. ***")

    for dim in DIMENSOES:
        grupos = agrupar(dados, dim)
        if not grupos:
            continue
        linhas = [(v, resumo_grupo(it)) for v, it in grupos.items()]
        linhas.sort(key=lambda x: -x[1]["views_mediana"])
        print(f"\n--- {dim} ---")
        for val, r in linhas:
            marca = "" if r["n"] >= MIN_AMOSTRA else "  (n baixo)"
            print(f"  {val:<26} n={r['n']:<3} views~{r['views_mediana']:>8,.0f}"
                  f"  compart~{r['compart_mediana']:>6,.0f}"
                  f"  taxa {r['taxa_compart']:.2%}{marca}")

    # duração em faixas — testa a hipótese 65-75 vs 90-110 do playbook §16.1
    faixas = {"<60s (não monetiza)": (0, 60), "60-75s": (60, 75),
              "75-95s": (75, 95), "95s+": (95, 10**6)}
    print("\n--- duração ---")
    for nome, (a, b) in faixas.items():
        it = [(p, m) for p, m in dados if a <= (p.get("duracao_s") or 0) < b]
        if not it:
            continue
        r = resumo_grupo(it)
        marca = "" if r["n"] >= MIN_AMOSTRA else "  (n baixo)"
        print(f"  {nome:<26} n={r['n']:<3} views~{r['views_mediana']:>8,.0f}"
              f"  compart~{r['compart_mediana']:>6,.0f}{marca}")

    # subnotas do Gemini: elas preveem alguma coisa?
    print("\n--- as subnotas do Gemini preveem? (mediana de views por faixa) ---")
    for sn in SUBNOTAS:
        alto = [m.get("views") or 0 for p, m in dados if (p.get(sn) or 0) >= 9]
        baixo = [m.get("views") or 0 for p, m in dados if 0 < (p.get(sn) or 0) < 9]
        if not alto or not baixo:
            print(f"  {sn:<24} dados insuficientes")
            continue
        print(f"  {sn:<24} >=9: {statistics.median(alto):>8,.0f} (n={len(alto)})"
              f"   <9: {statistics.median(baixo):>8,.0f} (n={len(baixo)})")

    print(f"\n{'='*70}\nComo usar: o que aparecer no topo com n>={MIN_AMOSTRA} vira "
          f"prioridade\nna seleção. O que ficar no fundo consistentemente, corte "
          f"do radar.\n{'='*70}")


# ------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser(description="Loop de feedback: desempenho real dos posts")
    p.add_argument("--pendentes", action="store_true")
    p.add_argument("--modelo-csv", nargs="?", const="medicoes.csv")
    p.add_argument("--importar")
    p.add_argument("--add")
    p.add_argument("--views", type=int)
    p.add_argument("--curtidas", type=int)
    p.add_argument("--comentarios", type=int)
    p.add_argument("--compartilhamentos", type=int)
    p.add_argument("--retencao", type=float, help="%% médio assistido")
    p.add_argument("--seguidores", type=int, help="seguidores ganhos")
    p.add_argument("--relatorio", action="store_true")
    p.add_argument("--todos", action="store_true",
                   help="considera todo clipe produzido, não só os publicados")
    a = p.parse_args()

    todos = clipes()
    meds = carregar(MEDICOES, {})
    alvo = todos.keys() if a.todos else (publicados() & todos.keys())

    if a.pendentes:
        falta = [k for k in alvo if k not in meds]
        print(f"{len(falta)} posts publicados sem medição:\n")
        for k in sorted(falta):
            print(f"  {todos[k].get('titulo','')[:60]}\n    {k}")
        if not falta:
            print("  (nenhum — tudo medido)")
        return

    if a.modelo_csv:
        destino = Path(a.modelo_csv)
        falta = [k for k in alvo if k not in meds]
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
            w.writeheader()
            for k in sorted(falta):
                w.writerow({"chave": k, "titulo": todos[k].get("titulo", "")})
        print(f"{len(falta)} linhas em {destino}. Preencha no TikTok Studio "
              f"e rode:\n  python desempenho.py --importar {destino}")
        return

    if a.importar:
        with open(a.importar, newline="", encoding="utf-8-sig") as f:
            n = 0
            for linha in csv.DictReader(f):
                chave = (linha.get("chave") or "").strip()
                if not chave or not (linha.get("views") or "").strip():
                    continue
                meds[chave] = {
                    c: (float(linha[c]) if c in ("retencao_pct",) else int(float(linha[c])))
                    for c in CAMPOS_CSV[2:]
                    if (linha.get(c) or "").strip()
                }
                n += 1
        gravar_medicoes(meds)
        print(f"{n} medições importadas.")
        return

    if a.add:
        if a.views is None:
            sys.exit("--add exige pelo menos --views")
        m = {"views": a.views}
        for nome, v in (("curtidas", a.curtidas), ("comentarios", a.comentarios),
                        ("compartilhamentos", a.compartilhamentos),
                        ("retencao_pct", a.retencao), ("seguidores_ganhos", a.seguidores)):
            if v is not None:
                m[nome] = v
        if a.add not in todos:
            a_add_norm = None
            print(f"[!] chave não encontrada em saida/: {a.add}")
            print("    veja as válidas com --pendentes")
        meds[a.add] = m
        gravar_medicoes(meds)
        print(f"registrado: {todos.get(a.add, {}).get('titulo', a.add)[:60]}")
        return

    relatorio(todos, meds)


if __name__ == "__main__":
    main()
