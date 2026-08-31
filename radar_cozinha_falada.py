# -*- coding: utf-8 -*-
"""Radar de fontes FALADAS para o @cozinha.internacional.

POR QUE ELE EXISTE, e por que nao e' o `descobrir.py`

O `descobrir.py` ordena por hype puro: views, views/hora, engajamento. Isso
nao diz nada sobre a unica coisa que decide se a fonte SERVE — se alguem fala
nela.

O motor narra o que foi DITO. Fonte muda nao tem o que dublar, e o clipe sai
mudo: a guarda o recusa no FIM do run, com o runner inteiro ja' gasto. Em
cozinha isso e' o caso dominante, nao a excecao — "satisfying", "no talking"
e compilacao com trilha sao o formato padrao do nicho.

Foi o que aconteceu com os 6 brutos da pasta DOCES: pelo menos dois sao
compilacao muda ("Amazing CAKE Decorating Compilation", "AMAZING Dessert
Compilation So Satisfying").

⚠️ MAS NAO OS SEIS. Em 31/08/2026 eu disse que os 6 eram compilacoes mudas e
isso estava ERRADO: "Make Butter in 10 Minutes — Chef Jean-Pierre" e os dois
do Babish sao de criadores que falam o tempo todo. Julguei a pasta pelo pior
item. Aqui a regra e' por VIDEO, nunca por pasta.

## O criterio que manda: SEGUNDOS POR RECEITA

Herdado do `09_RADAR_FONTES.md`. O corte tem de ser uma unidade completa e
cabe entre DUR_MIN (65s) e DUR_MAX (210s):

    entre 65 e 210s  -> cada receita vira UM corte inteiro. Ideal.
    acima de 210s    -> a receita nao cabe e o corte parte no meio de um passo
    abaixo de 65s    -> nao monetiza sozinho

Nao da' pra contar receitas pela API, entao o radar usa a DURACAO como proxy e
marca a faixa. A contagem real e' olho humano, no titulo ("5 ways", "6
recipes") — por isso ela e' extraida quando aparece.

RODOU EM 31/08/2026. O que a rodada mostrou:

  42 candidatos. Cortados: 0 por fonte muda, 0 por venda, 11 fora do tema,
  9 por alfabeto nao-latino.

  ⚠️ O VETO DE FONTE MUDA NAO MORDEU NENHUMA VEZ. Isso NAO quer dizer que ele
  e' inutil — quer dizer que as buscas ja' puxam pro formato falado, entao o
  material mudo nem chega. Ele fica como rede de seguranca para quando alguem
  acrescentar um termo mais aberto.

  ⚠️ E O CRITERIO PRINCIPAL SO' VALE PRA 4 DE 42. "Segundos por receita" e' o
  que o 09_RADAR_FONTES.md diz que organiza tudo — mas ele depende de o titulo
  DIZER quantas receitas tem, e a maioria nao diz. Nos outros 38 a nota cai
  para hype puro com um desconto fixo. E' limitacao real, nao ajuste
  pendente: a API nao expoe contagem de receita.

Roda com:  python radar_cozinha_falada.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _chaves() -> list[str]:
    """Le as chaves do AMBIENTE — nunca do codigo.

    A primeira versao do radar do @atefalhar tinha as cinco chaves escritas
    dentro do arquivo. Os repositorios sao PUBLICOS: commitar assim queima as
    cinco, e apagar depois nao resolve porque o valor fica no historico.
    """
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    ks = []
    if v := os.getenv("YOUTUBE_API_KEY"):
        ks.append(v.strip())
    for i in range(2, 21):
        if v := os.getenv(f"YOUTUBE_API_KEY_{i}"):
            ks.append(v.strip())
    if not ks:
        sys.exit("Nenhuma YOUTUBE_API_KEY no ambiente. Elas estao em "
                 "Desktop/Tiktok/CREDENCIAIS.md, fora de qualquer repo.")
    return ks


CHAVES = _chaves()

# Buscas puxando para o formato FALADO. Cada termo carrega uma palavra que so'
# aparece quando alguem explica: "explains", "how to", "recipe tutorial",
# "step by step". Nao adianta gastar cota trazendo o que o veto vai matar.
BUSCAS = [
    "chef explains recipe step by step",
    "cooking tutorial talking through recipe",
    "how to make dessert recipe explained",
    "professional chef technique explained kitchen",
    "baking recipe tutorial voice over",
    "easy dinner recipe explained step by step",
    "chef jean pierre recipe",
    "binging with babish recipe",
]

# ⚠️ VETO DURO — fonte muda. E' o formato DOMINANTE do nicho de cozinha, nao
# um caso raro. Sem fala nao ha' dublagem, e o clipe sai mudo.
VETO_MUDO = [
    "no talking", "asmr", "silent", "music only", "relaxing",
    "satisfying", "compilation", "compilado", "aesthetic",
    "cooking sounds", "no voice", "sem falar",
]

# Vendas e sorteio: o corte vira anuncio de terceiro.
VETO_VENDA = ["giveaway", "haul", "link in bio", "sponsored", "codigo de desconto"]

# Filtro de TEMA positivo. O titulo ou o canal tem de conter uma destas.
# A lista e' LARGA de proposito: no radar do @truque.importado uma lista curta
# demais derrubou tres videos bons EM SILENCIO, e recusa silenciosa e' pior
# que ruido porque ninguem a percebe.
TEMA = [
    "recipe", "recipes", "cook", "cooking", "bake", "baking", "kitchen",
    "chef", "dessert", "dish", "meal", "dinner", "breakfast", "lunch",
    "bread", "cake", "pasta", "sauce", "roast", "grill", "fry", "soup",
    "receita", "cozinha", "culinaria",
]

# Fonte em portugues tira a razao do canal: sem traducao nao ha' conversao de
# medida, que e' o produto ("350°F e' 180°C. De nada."). MARCA, nao veta — a
# decisao e' editorial.
PT_TIRA_A_CONVERSAO = ("fonte PT: sem traducao nao ha' conversao de medida, "
                       "que e' o produto do canal")

DUR_MIN, DUR_MAX = 65, 210        # iguais ao config.py da cozinha


def http(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def com_rodizio(monta_url):
    """Tenta cada chave: a cota de busca estoura rapido (429 medido em 30/08)."""
    ultimo = None
    for k in CHAVES:
        try:
            return http(monta_url(k))
        except Exception as e:
            ultimo = e
            continue
    raise RuntimeError(f"todas as {len(CHAVES)} chaves falharam: {ultimo}")


def buscar(termo, n=8):
    def url(k):
        q = urllib.parse.urlencode({
            "part": "snippet", "q": termo, "type": "video",
            "maxResults": n, "order": "viewCount",
            "videoDuration": "medium",   # 4 a 20 min
            "publishedAfter": "2024-06-01T00:00:00Z",
            "key": k})
        return "https://www.googleapis.com/youtube/v3/search?" + q
    return com_rodizio(url).get("items", [])


def detalhes(ids):
    def url(k):
        q = urllib.parse.urlencode({
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(ids), "key": k})
        return "https://www.googleapis.com/youtube/v3/videos?" + q
    return com_rodizio(url).get("items", [])


def segundos(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def quantas_receitas(titulo: str) -> int | None:
    """Conta receitas quando o TITULO diz ("5 ways", "6 recipes", "3 dishes").

    Nao inventa quando nao diz — devolve None. Um numero chutado aqui vira
    "segundos por receita" chutado, que e' o criterio que manda em tudo.
    """
    # ⚠️ MEDIDO em 31/08/2026: a primeira versao deste padrao achou contagem
    # em 0 de 42 titulos reais. Ele exigia o numero COLADO no substantivo e so'
    # conhecia cinco substantivos — entao "The 5 Sauces", "4 Easy Desserts",
    # "5 Easy Dinners" e "29 Vegetable Hacks" passavam batido.
    #
    # Detector que nunca acha nao devolve "nao ha'": devolve "nao sei", e o
    # criterio que manda no radar inteiro (segundos por receita) fica sem
    # entrada. Ele passou despercebido porque a saida era "?" — que e' um
    # valor legitimo — em vez de um erro.
    #
    # Agora aceita ate' dois adjetivos entre o numero e o substantivo, e a
    # lista e' larga. Acha em 4 de 42, que e' o numero HONESTO: a maioria dos
    # titulos realmente nao diz quantas receitas tem.
    m = re.search(
        r"\b(\d{1,2})\s+(?:\w+\s+){0,2}"
        r"(ways?|recipes?|dishes|meals?|desserts?|sauces?|dinners?|lunches|"
        r"breakfasts?|cookies?|cakes?|snacks?|hacks?|ideas?|tips?)\b",
        titulo, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _escrita_estranha(texto: str) -> bool:
    """Titulo em alfabeto nao-latino.

    O `defaultAudioLanguage` da API MENTE — no radar do @atefalhar um video
    inteiro em hindi vinha declarado como `en`. O alfabeto do titulo nao mente.
    Piso de 15% pra um titulo ingles com emoji nao ser recusado.
    """
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return False
    fora = sum(1 for c in letras if ord(c) > 0x2E80 or 0x0370 <= ord(c) <= 0x1CFF)
    return fora / len(letras) > 0.15


def avaliar(v):
    st = v.get("statistics", {})
    views = int(st.get("viewCount", 0) or 0)
    likes = int(st.get("likeCount", 0) or 0)
    dur = segundos(v["contentDetails"]["duration"])
    titulo = v["snippet"]["title"]
    pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
    horas = max(1.0, (datetime.now(timezone.utc) - pub).total_seconds() / 3600)
    idioma = (v["snippet"].get("defaultAudioLanguage")
              or v["snippet"].get("defaultLanguage") or "")
    pt = idioma.lower().startswith("pt")

    vph = views / horas
    eng = (likes / views * 100) if views else 0

    n_rec = quantas_receitas(titulo)
    s_por_receita = (dur / n_rec) if n_rec else None

    # O criterio que manda: a receita cabe num corte inteiro?
    if s_por_receita is None:
        custo = 0.8               # sem contagem no titulo, e' aposta
        faixa = "?"
    elif DUR_MIN <= s_por_receita <= DUR_MAX:
        custo = 1.0               # ideal: cada receita vira um corte
        faixa = "OK"
    elif s_por_receita > DUR_MAX:
        custo = 0.4               # nao cabe: o corte parte no meio do passo
        faixa = "LONGA"
    else:
        custo = 0.3               # curta demais: nao monetiza sozinha
        faixa = "CURTA"

    nota = (min(views / 1000, 100) * 0.5 + min(vph, 100) * 0.3
            + min(eng * 10, 100) * 0.2) * custo
    return {
        "id": v["id"], "titulo": titulo,
        "canal": v["snippet"]["channelTitle"],
        "url": f"https://www.youtube.com/watch?v={v['id']}",
        "views": views, "views_h": round(vph, 1), "eng": round(eng, 2),
        "dur_min": round(dur / 60, 1), "idioma": idioma or "?",
        "receitas": n_rec,
        "s_por_receita": round(s_por_receita) if s_por_receita else None,
        "faixa": faixa, "pt": pt,
        "aviso": PT_TIRA_A_CONVERSAO if pt else "",
        "nota": round(nota, 1),
    }


def main():
    vistos, brutos = set(), []
    for termo in BUSCAS:
        try:
            itens = buscar(termo)
        except Exception as e:
            print(f"  [!] busca falhou ({termo[:35]}): {str(e)[:70]}")
            continue
        novos = [i["id"]["videoId"] for i in itens
                 if i["id"]["videoId"] not in vistos]
        vistos.update(novos)
        print(f"  {termo[:42]:<44} {len(novos)} novo(s)")
        for j in range(0, len(novos), 50):
            brutos += detalhes(novos[j:j + 50])

    aval = []
    corte = {"mudo": 0, "venda": 0, "tema": 0, "escrita": 0}
    for v in brutos:
        titulo = v["snippet"]["title"]
        t = (titulo + " " + v["snippet"]["channelTitle"]).lower()
        if any(x in t for x in VETO_MUDO):
            corte["mudo"] += 1
            continue
        if any(x in t for x in VETO_VENDA):
            corte["venda"] += 1
            continue
        if _escrita_estranha(titulo):
            corte["escrita"] += 1
            continue
        if not any(x in t for x in TEMA):
            corte["tema"] += 1
            continue
        aval.append(avaliar(v))
    aval.sort(key=lambda x: -x["nota"])

    # Salva ANTES de imprimir: em 30/08 um emoji no titulo derrubou a saida no
    # console do Windows (cp1252) e levou junto uma rodada ja' paga em cota.
    with open("radar_cozinha_falada.json", "w", encoding="utf-8") as f:
        json.dump(aval, f, ensure_ascii=False, indent=1)

    def seguro(t):
        return t.encode("ascii", "replace").decode("ascii")

    print(f"\n{len(aval)} candidato(s)   |   cortados: {corte['mudo']} mudo/"
          f"compilacao, {corte['venda']} venda, {corte['tema']} fora do tema, "
          f"{corte['escrita']} alfabeto nao-latino\n")
    print(f"{'#':<3} {'nota':>5} {'min':>6} {'rec':>4} {'s/rec':>6} "
          f"{'faixa':>6} {'views':>9}  titulo")
    print("-" * 110)
    for i, v in enumerate(aval[:20], 1):
        pt = " <PT?>" if v["pt"] else ""
        print(f"{i:<3} {v['nota']:>5} {v['dur_min']:>6} "
              f"{str(v['receitas'] or '-'):>4} {str(v['s_por_receita'] or '-'):>6} "
              f"{v['faixa']:>6} {v['views']:>9}{pt}  {seguro(v['titulo'])[:44]}")
    print(f"\n{len(aval)} salvos em radar_cozinha_falada.json")
    print(f"faixa OK = cada receita cabe num corte ({DUR_MIN}-{DUR_MAX}s)")
    print("faixa ?  = o titulo nao diz quantas receitas; conferir no olho")
    print("\n⚠️ O veto le' o TITULO, nao o audio. Um video mudo que nao diz")
    print("   isso no titulo passa — e o clipe so' sai mudo no FIM do run.")


if __name__ == "__main__":
    main()
