"""Pré-triagem por TRANSCRIÇÃO: decide o que vale baixar, antes de baixar.

Por que existe
--------------
O radar pontua o vídeo-fonte por viralidade (views/hora, engajamento). Mas
não é isso que nos paga. O que paga é o CLIPE qualificar: mais de 60s,
~50% de retenção e o bônus de originalidade (PLAYBOOK_TIKTOK.md §1).
Vídeo-fonte viral e vídeo-fonte cortável são coisas diferentes — um viral
de 8 min pode não ter um único arco autocontido de 65s, e um documentário
de 31 min com views modestas pode ter seis (foi o caso da Bermuda, que deu
nosso melhor lote: 6 clipes, notas 83-95).

Como funciona
-------------
Baixa só a LEGENDA (yt-dlp, segundos, e **não gasta cota da YouTube Data
API**), manda a transcrição pro Nemotron e recebe uma nota de
cortabilidade. Só o que passa merece os 300-400 MB de download e a
requisição do Gemini.

    python triar_cortabilidade.py --listar
    python triar_cortabilidade.py --top 20
    python triar_cortabilidade.py --url "https://youtu.be/..."

Grava `CORTABILIDADE (0-100)` e `ARCOS_65s` de volta nos CSVs do radar, e
mantém cache em `estado/cortabilidade.json` pra não retriar o mesmo vídeo.
"""
import argparse
import csv
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import config                       # noqa: E402
from engine import nemotron         # noqa: E402

def _achar_descobridor() -> Path:
    """Procura a pasta do descobridor subindo a árvore, em vez de contar
    níveis fixos.

    O caminho antigo repetia o nome da pasta
    (`..\\descobridor-de-virais\\descobridor-de-virais`), herdado do layout
    aninhado da máquina anterior. No layout atual ele não existe, e o efeito
    era silencioso do pior jeito: `candidatos()` não achava CSV nenhum e a
    triagem dizia "nada a triar" — parecendo trabalho concluído. É o mesmo
    defeito que o `config.py` do descobridor já documenta na direção oposta.
    """
    aqui = Path(__file__).resolve().parent
    for base in [aqui, *aqui.parents][:5]:
        for cand in (base / "descobridor-de-virais", base.parent / "descobridor-de-virais"):
            if cand.is_dir() and any(cand.glob("*.csv")):
                return cand
    return aqui.parent / "descobridor-de-virais"


DESCOBRIDOR = _achar_descobridor()

# Os CSVs fixos dos radares antigos, MAIS todo `radar_*.csv` — o
# `radar_assunto.py` cria um arquivo por assunto (`radar_limiar_humano.csv`,
# `radar_robos_ia.csv`...), e uma lista fixa nunca os incluiria. Sem isto a
# triagem ignorava exatamente as listas dirigidas, que são as que o Bryan
# manda rodar.
CSVS = sorted({"fila_de_aprovacao.csv", "viral_geral.csv",
               "oportunidades_podcast.csv",
               *(p.name for p in DESCOBRIDOR.glob("radar_*.csv"))})
CACHE = config.ESTADO / "cortabilidade.json" if hasattr(config, "ESTADO") \
    else Path(__file__).resolve().parent / "estado" / "cortabilidade.json"

COL_NOTA = "CORTABILIDADE (0-100)"
COL_ARCOS = "ARCOS_65s"
COL_VEREDITO = "VEREDITO_TRIAGEM"
COL_STATUS = "STATUS"

TAG = re.compile(r"<[^>]+>")
TEMPO = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->")


# ------------------------------------------------------------------ legenda
def baixar_legenda(url: str, tentativas: int = 3) -> tuple[str, str] | tuple[None, str]:
    """Baixa só a legenda (auto ou manual), pt ou en. Devolve (texto, idioma).

    Um idioma POR VEZ de propósito: `--sub-langs "pt.*,en.*"` resolvia pra
    4 faixas (pt, pt-PT, en-orig, en) e fazia 4 requisições por vídeo — o
    caminho mais rápido pro 429 do YouTube, que é o gargalo real aqui.
    """
    for idioma in ("pt", "en"):
        for t in range(tentativas):
            with tempfile.TemporaryDirectory() as tmp:
                cmd = ["yt-dlp", "--skip-download", "--write-auto-subs",
                       "--write-subs", "--sub-langs", idioma,
                       "--sub-format", "vtt", "--no-warnings",
                       "--retries", "3", "--extractor-retries", "2",
                       "-o", str(Path(tmp) / "%(id)s"), url]
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True,
                                       encoding="utf-8", errors="replace",
                                       timeout=300, check=False)
                except subprocess.TimeoutExpired:
                    return None, "timeout"
                vtts = sorted(Path(tmp).glob("*.vtt"))
                if vtts:
                    txt = vtts[0].read_text(encoding="utf-8", errors="replace")
                    return limpar_vtt(txt), idioma
                erro = (p.stderr or "") + (p.stdout or "")
                if "429" in erro or "Too Many Requests" in erro:
                    # rate limit de IP do YouTube: espera crescente
                    time.sleep(20 * (t + 1))
                    continue
                if "not a bot" in erro or "Sign in to confirm" in erro:
                    # Bloqueio de IP de datacenter — o MESMO que impede o
                    # download de vídeo na VPS. Medido em 30/07/2026: numa
                    # tanda de 154, 101 caíram aqui e eram rotulados
                    # "sem_legenda", como se o vídeo não tivesse legenda.
                    # São coisas opostas: sem_legenda é veredito final, isto
                    # é falha NOSSA e o vídeo continua candidato — basta
                    # triar da máquina do Bryan, que tem IP residencial.
                    return None, "bloqueado_ip"
                break        # não tem esse idioma, tenta o próximo
    return None, "sem_legenda"


def limpar_vtt(bruto: str) -> str:
    """VTT de auto-caption é rolante: cada bloco repete a linha anterior."""
    linhas, vistas = [], set()
    for cru in bruto.splitlines():
        s = cru.strip()
        if not s or s.startswith(("WEBVTT", "Kind:", "Language:")) or TEMPO.match(s):
            continue
        s = TAG.sub("", s).strip()
        if not s or s in vistas:
            continue
        vistas.add(s)
        linhas.append(s)
    return re.sub(r"\s+", " ", " ".join(linhas)).strip()


# ------------------------------------------------------------------ nota
PROMPT = """\
Você avalia se um vídeo LONGO serve de matéria-prima para cortes de TikTok.

O QUE PAGA (não confunda com "o vídeo é bom"):
- O TikTok só paga por vídeo com MAIS DE 60 SEGUNDOS, e que segure ~50% de
  retenção. Então o que vale é: quantos trechos AUTOCONTIDOS de 65 a 110
  segundos este vídeo contém?
- Autocontido = faz sentido sozinho, sem precisar do resto do vídeo, sem
  precisar de contexto que o espectador não tem.
- Cada trecho precisa de um GANCHO nos 3 primeiros segundos: revelação,
  número chocante, tabu, contradição, pergunta enigmática.
- A fala tem que se sustentar SEM ver a tela (nosso corte é 9:16 com
  legenda queimada; o espectador não vê gráfico nem slide).

NÃO PONTUE por: fama do canal, produção cara, quantas views o original tem.
Um documentário desconhecido com 6 boas histórias vale mais que uma
entrevista famosa com nenhuma.

Penalize: vídeo que é só bate-papo sem revelação; conteúdo que depende de
imagem na tela; fala picotada por música/aplauso; assunto que exige
contexto longo; conteúdo que já é um corte de outra pessoa.

TÍTULO: {titulo}
IDIOMA DA TRANSCRIÇÃO: {idioma}

TRANSCRIÇÃO:
{texto}

Responda APENAS este JSON:
{{
  "cortabilidade": <0-100>,
  "arcos": <quantos trechos autocontidos de 65-110s você conseguiria tirar>,
  "densidade_fala": "alta|media|baixa",
  "independencia_visual": "alta|media|baixa",
  "veredito": "cortar|talvez|descartar",
  "motivo": "<1-2 frases, direto>",
  "melhores": [
    {{"tema": "<do que trata>", "gancho": "<a frase/ideia de abertura>"}}
  ]
}}
"melhores": até 3, os arcos mais fortes. Lista vazia se não houver nenhum.
"""

LIMITE_PALAVRAS = 40000     # ~1h30 de fala; acima disso corta o meio


def avaliar(titulo: str, texto: str, idioma: str) -> dict:
    palavras = texto.split()
    if len(palavras) > LIMITE_PALAVRAS:
        metade = LIMITE_PALAVRAS // 2
        texto = " ".join(palavras[:metade] + ["[...]"] + palavras[-metade:])
    return nemotron.json_de(
        PROMPT.format(titulo=titulo, idioma=idioma, texto=texto),
        temperatura=0.2, max_tokens=8000)


# ------------------------------------------------------------------ CSVs
def ler_csv(caminho: Path):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        leitor = csv.DictReader(f)
        return list(leitor), list(leitor.fieldnames or [])


def gravar_csv(caminho: Path, linhas, campos):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def candidatos(so_csv: str | None = None):
    """Linhas com URL, ainda não cortadas e ainda sem nota de cortabilidade.

    `so_csv` restringe a um arquivo (ex: 'radar_limiar_humano.csv'). Sem ele a
    fila junta todos os radares — mais de mil linhas — e triar "os 20
    primeiros" pegaria os do radar mais antigo, não os da lista recém-rodada.
    """
    out = []
    for nome in CSVS:
        if so_csv and nome != so_csv:
            continue
        caminho = DESCOBRIDOR / nome
        if not caminho.exists():
            continue
        linhas, _ = ler_csv(caminho)
        for i, l in enumerate(linhas):
            url = (l.get("url") or "").strip()
            if not url:
                continue
            if (l.get(COL_STATUS) or "").strip().lower() in ("cortado", "sem_clipe"):
                continue
            if (l.get(COL_NOTA) or "").strip():
                continue
            try:
                nota_radar = float(l.get("nota") or 0)
            except ValueError:
                nota_radar = 0.0
            out.append({"csv": nome, "i": i, "url": url,
                        "titulo": (l.get("titulo") or "").strip(),
                        "nota_radar": nota_radar})
    out.sort(key=lambda x: -x["nota_radar"])
    return out


def anotar(csv_nome: str, indice: int, r: dict):
    caminho = DESCOBRIDOR / csv_nome
    linhas, campos = ler_csv(caminho)
    for c in (COL_NOTA, COL_ARCOS, COL_VEREDITO):
        if c not in campos:
            campos.append(c)
    if indice < len(linhas):
        linhas[indice][COL_NOTA] = r.get("cortabilidade", "")
        linhas[indice][COL_ARCOS] = r.get("arcos", "")
        linhas[indice][COL_VEREDITO] = r.get("veredito", "")
        gravar_csv(caminho, linhas, campos)


def cache_ler() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def cache_gravar(d: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ main
def triar_um(c: dict, cache: dict) -> dict | None:
    texto, idioma = baixar_legenda(c["url"])
    if not texto:
        print(f"   [-] {c['titulo'][:55]}  ({idioma})")
        return {"url": c["url"], "titulo": c["titulo"], "cortabilidade": None,
                "veredito": idioma, "arcos": 0}
    if len(texto.split()) < 300:
        print(f"   [-] {c['titulo'][:55]}  (transcrição curta demais)")
        return {"url": c["url"], "titulo": c["titulo"], "cortabilidade": None,
                "veredito": "transcricao_curta", "arcos": 0}
    try:
        r = avaliar(c["titulo"], texto, idioma)
    except Exception as e:                                  # noqa: BLE001
        print(f"   [x] {c['titulo'][:45]}: {str(e)[:70]}")
        return None
    r["url"], r["titulo"] = c["url"], c["titulo"]
    r["palavras"] = len(texto.split())
    print(f"   [{r.get('cortabilidade','?'):>3}] {r.get('arcos','?')} arcos · "
          f"{r.get('veredito','?'):<9} {c['titulo'][:50]}")
    return r


def main():
    p = argparse.ArgumentParser(description="Tria vídeos por cortabilidade, pela transcrição")
    p.add_argument("--listar", action="store_true", help="só mostra a fila")
    p.add_argument("--top", type=int, default=10, help="quantos triar (padrão 10)")
    p.add_argument("--url", help="tria uma URL avulsa, sem mexer nos CSVs")
    p.add_argument("--titulo", default="(avulso)", help="título, com --url")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--csv", help="tria só este CSV do descobridor "
                                 "(ex: radar_limiar_humano.csv)")
    a = p.parse_args()

    cache = cache_ler()

    if a.url:
        r = triar_um({"url": a.url, "titulo": a.titulo}, cache)
        if r:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            cache[a.url] = r
            cache_gravar(cache)
        return

    fila = candidatos(a.csv)
    if not fila:
        print("Nada pra triar. Rode os radares do descobridor primeiro.")
        return

    if a.listar:
        print(f"{len(fila)} candidatos sem triagem (melhor nota de radar primeiro):\n")
        for c in fila[:40]:
            print(f"  [radar {c['nota_radar']:>5.1f}]  {c['titulo'][:66]}")
        return

    alvos = fila[:a.top]
    print(f"triando {len(alvos)} de {len(fila)} candidatos (só legenda, sem download)\n")

    # O resultado fica CASADO com o candidato desde já. Antes o `None` de uma
    # falha era filtrado da lista e o `zip` seguinte deslocava tudo: a nota de
    # um vídeo era gravada na linha de outro. Com um alvo só nunca aparecia;
    # com 154 e a rede falhando no meio, aparece.
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        pares = list(zip(alvos, ex.map(lambda c: triar_um(c, cache), alvos)))

    resultados = [r for _, r in pares if r]
    for c, r in pares:
        if not r:
            continue
        cache[c["url"]] = r
        anotar(c["csv"], c["i"], r)
    cache_gravar(cache)

    bons = sorted([r for r in resultados if r.get("cortabilidade") is not None],
                  key=lambda r: -r["cortabilidade"])
    print(f"\n{'='*68}\nRANKING POR CORTABILIDADE\n{'='*68}")
    for r in bons:
        print(f"\n[{r['cortabilidade']}] {r.get('arcos',0)} arcos · {r.get('veredito','')}"
              f"\n  {r['titulo'][:70]}\n  {r.get('motivo','')}")
        for m in (r.get("melhores") or [])[:3]:
            print(f"    · {m.get('tema','')} — \"{str(m.get('gancho',''))[:60]}\"")
        print(f"  {r['url']}")

    cortar = [r for r in bons if r.get("veredito") == "cortar"]
    print(f"\n{len(cortar)} vale(m) cortar. Marque 's' em 'APROVAR (s/n)' no CSV "
          f"e rode:\n  python importar_aprovados.py --qtd 8")


if __name__ == "__main__":
    main()
