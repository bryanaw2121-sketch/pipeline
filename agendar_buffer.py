# -*- coding: utf-8 -*-
"""Enfileira clipes no Buffer, na ordem certa, respeitando o teto do plano.

POR QUE EXISTE
O plano gratuito do Buffer guarda no máximo 10 posts agendados por canal. Não
é limite de total, é de FILA: a cada post enviado, um slot volta. Então a fila
não precisa ser profunda — precisa ser reabastecida. Este script faz isso.

AS TRÊS REGRAS, todas pedidas pelo Bryan e todas com motivo:

1. ORDEM CRONOLÓGICA DENTRO DO MESMO VÍDEO-FONTE. Ordenar por nota embaralha a
   narrativa: no run #159 a nota 95 estava aos 141s do fonte, a 93 aos 1210s e
   a 92 aos 54s — o trecho dos 20 minutos ia ao ar antes do trecho do primeiro
   minuto. Ordena por `inicio_s`, que o `publicar_release.py` carrega até o
   manifesto.

2. UMA VAGA SEMPRE LIVRE. Enche até 9 dos 10, pro Bryan conseguir encaixar algo
   na mão sem precisar apagar nada.

3. RÓTULO DE IA SEMPRE MARCADO (`isAiGenerated`). A interface do Buffer não
   expõe esse campo — a API expõe. É a única forma de marcar esses vídeos.

DEDUPLICAÇÃO SEM REGISTRO LOCAL: compara o texto dos posts que já estão no
Buffer com a legenda do clipe. Arquivo de registro não serviria, porque este
script roda tanto na VPS quanto no runner do GitHub, e no runner ele nasce
vazio a cada execução.

Uso:
    python agendar_buffer.py --simular    # mostra o que faria, não manda nada
    python agendar_buffer.py              # enfileira de verdade
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

from engine import buffer_cota as cota, dedup, registro_clipes, refeicao
from engine import adiados, rejeitados

API_BUFFER = "https://api.buffer.com/"
API_GITHUB = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPO", "bryanaw2121-sketch/media-assets")

# Teto do plano gratuito, medido em 25/08/2026 (o app avisa "1 post left" com
# 9 na fila).
#
# RESERVA passou de 1 pra 0 em 25/08, a pedido do Bryan: ele prefere a fila
# sempre cheia. Se ele quiser encaixar algo na mão, apaga um post ou usa
# --reserva 1 numa rodada. A regra 2 lá em cima descreve o comportamento
# antigo e fica aqui como histórico da decisão.
LIMITE_FILA = 10
RESERVA_MANUAL = 0
# Teto de páginas por consulta de posts. Cada página é uma requisição, e o
# histórico só cresce — sem teto, a consulta fica mais cara a cada semana.
MAX_PAGINAS = 4

# Horários de postagem (São Paulo). O `addToQueue` usaria a agenda do canal no
# Buffer, que não reflete isto — então o agendamento é explícito.
# Cortado de 6 pra 5 slots em 26/08/2026, decisao do Bryan. Motivo medido: os
# dois melhores dias do canal tiveram 5 e 2 posts (medianas 726 e 434) e o dia
# de 15 posts foi o pior de julho (115). O slot das 13:07 foi o escolhido pra
# sair porque era o par mais apertado da grade (1h34 depois das 11:33), e em
# 26/08 os dois posts do meio-dia foram os piores medidos do dia (22 e 11).
# CADENCIA AINDA NAO DECIDIDA pro canal de comida. Estes horarios sao herdados
# do outro canal e servem so' como ponto de partida — canal novo tem alcance
# diferente, e copiar cadencia sem medir foi explicitamente desaconselhado.
# 29/08/2026: 4 posts/dia nos DOIS canais, decisao do Bryan. Saiu o slot das
# 20:50, o par mais apertado da grade (1h47 depois das 19:03).
SLOTS_SP = [(8, 15), (11, 33), (16, 27), (19, 30)]
# Teto DURO de posts por dia (SP), contando o que ja' foi enviado. A grade
# sozinha nunca segurou o volume: 25/08 saiu com 8 posts e 26/08 com 11, ambos
# acima dos 6 slots que existiam. Isso acontece porque um slot que ja' disparou
# some de `scheduled`, e uma rodada seguinte do agendador enxerga o dia vazio.
MAX_POR_DIA = 4
# Intervalo MINIMO entre dois posts do mesmo dia, em horas. Ordem do Bryan em
# 29/08/2026. E' regra DURA, verificada depois do sorteio da variacao — nao um
# alvo que a grade tenta cumprir.
#
# A diferenca importa: com a grade sozinha, o par 16:27-19:30 da' 3h03, mas a
# variacao de ±8 em cada ponta pode virar 2h47. Foi o que aconteceu no
# primeiro agendamento de 29/08 (16:32 -> 19:22 = 2h50). Confiar na folga da
# grade e' confiar num sorteio.
INTERVALO_MIN_H = 3.0
VARIACAO_MIN = 8      # minuto varia ±8 pra não parecer robô
FUSO_SP_H = 3         # America/Sao_Paulo = UTC-3

RAIZ = Path(__file__).resolve().parent


def _token_buffer() -> str:
    v = (os.environ.get("BUFFER_TOKEN") or "").strip()
    if v:
        return v
    arq = RAIZ / "buffer_token.txt"
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    sys.exit("Falta BUFFER_TOKEN (variável de ambiente ou buffer_token.txt).")


def _token_github() -> str:
    for nome in ("GITHUB_TOKEN", "GH_TOKEN"):
        v = (os.environ.get(nome) or "").strip()
        if v:
            return v
    arq = RAIZ / "github_token.txt"
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    sys.exit("Falta GITHUB_TOKEN — sem ele não dá pra ler o manifesto.")


def consultar(token: str, query: str, variaveis: dict | None = None) -> dict:
    # Orçamento ANTES da rede: em 25/08/2026 a conta bateu no rate limit de 24h
    # e a fila ficou intocável por um dia. Ver engine/buffer_cota.py.
    cota.checar(1)
    cota.registrar(1)
    r = requests.post(API_BUFFER,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"},
                      json={"query": query, "variables": variaveis or {}},
                      timeout=180)
    d = r.json()
    if "errors" in d:
        raise RuntimeError(json.dumps(d["errors"], ensure_ascii=False)[:400])
    return d["data"]


def contexto_buffer(token: str) -> tuple[str, str, list[dict]]:
    """Devolve (organizationId, channelId do TikTok, posts já agendados)."""
    org = consultar(token, "{ account { organizations { id } } }")
    org_id = org["account"]["organizations"][0]["id"]

    canais = consultar(token, """
      query($i: ChannelsInput!) { channels(input: $i) { id service name } }""",
      {"i": {"organizationId": org_id}})["channels"]
    tiktok = [c for c in canais if c["service"] == "tiktok"]
    if not tiktok:
        sys.exit("Nenhum canal TikTok conectado nesta conta do Buffer.")

    # Cache primeiro: a fila muda no máximo 4x/dia (é a cadência de postagem),
    # então reler a cada poucos minutos era desperdício puro.
    guardado = cota.cache_valido()
    if guardado is not None:
        return org_id, guardado["canal"], guardado["posts"]

    agendados, cursor, paginas = [], None, 0
    while True:
        paginas += 1
        if paginas > MAX_PAGINAS:
            print(f"  [!] parei em {MAX_PAGINAS} páginas pra não gastar orçamento; "
                  "a dedup usa o que veio (os mais recentes).")
            break
        d = consultar(token, """
          query($i: PostsInput!, $a: String) { posts(input: $i, after: $a) {
            pageInfo { hasNextPage endCursor }
            edges { node { id status text dueAt } } } }""",
          {"i": {"organizationId": org_id,
                 # "sent" JUNTO com "scheduled": a deduplicacao compara o texto
                 # dos posts que o Buffer ja' conhece, e clipe PUBLICADO tambem
                 # conta. Sem isso, um clipe que saiu de manha voltava pra fila
                 # a' tarde — republicacao acidental, o oposto do que o Bryan
                 # pediu. Aconteceu de verdade em 25/08/2026 com "A industria
                 # que controla todas as outras industrias".
                 "filter": {"status": ["scheduled", "sent"],
                            "channelIds": [tiktok[0]["id"]]}}, "a": cursor})["posts"]
        agendados += [e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]
    cota.guardar_cache({"canal": tiktok[0]["id"], "posts": agendados})
    return org_id, tiktok[0]["id"], agendados


def manifesto(token_gh: str, tag: str | None = None) -> dict:
    """Lê o manifesto.json das releases de clipes.

    Junta TODAS as releases `clipes-*`, não só a do mês: um clipe de fim de mês
    pode ser agendado no mês seguinte, e ele mora na release antiga.
    """
    h = {"Authorization": f"Bearer {token_gh}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"{API_GITHUB}/repos/{REPO}/releases?per_page=100", headers=h, timeout=60)
    r.raise_for_status()
    tudo = {}
    for rel in r.json():
        if tag and rel["tag_name"] != tag:
            continue
        if not tag and not rel["tag_name"].startswith("clipes-"):
            continue
        for a in rel.get("assets", []):
            if a["name"] == "manifesto.json":
                try:
                    # `?t=` derruba o cache do CDN do GitHub. MEDIDO em 25/08/2026: o asset
                    # tinha 16 clipes no servidor e a URL sem parametro devolvia 11 — versao
                    # antiga. Sem isto o agendador ignora silenciosamente todo lote novo.
                    tudo.update(requests.get(
                        a["browser_download_url"] + f"?t={int(time.time())}",
                        timeout=60).json())
                except Exception as e:
                    print(f"  [!] manifesto de {rel['tag_name']} ilegível: {str(e)[:70]}")
    return tudo


def _chave_texto(t: str) -> str:
    """Normaliza pra comparar legenda de clipe com texto de post do Buffer.

    Sem acento, sem hashtag, sem pontuação, minúsculo. O Buffer às vezes
    devolve o texto com espaçamento diferente do que foi enviado, então
    comparação literal não serve.
    """
    t = (t or "").split("#")[0]
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:70]


def ordenar(clipes: dict) -> list[tuple[str, dict]]:
    """Ordem de postagem: por vídeo-fonte, e dentro dele por posição no original.

    Os vídeos-fonte entram na ordem em que foram publicados na release; dentro
    de cada um, o corte mais no início do vídeo vai primeiro. É a regra 1.
    """
    itens = list(clipes.items())
    primeira_aparicao = {}
    for _, v in itens:
        f = v.get("fonte") or ""
        d = v.get("publicado_em") or ""
        if f not in primeira_aparicao or d < primeira_aparicao[f]:
            primeira_aparicao[f] = d

    def chave(par):
        _, v = par
        # Republicacao vai pro FIM da fila, sempre. Sao clipes que ja' foram ao
        # ar uma vez (ou que foram tirados da fila por terem sido postados sem
        # rotulo de IA) e voltam pelo pipeline. Sem isto eles entrariam na
        # FRENTE, porque a ordenacao usa a data de publicacao na release e o
        # lote deles e' mais antigo — o oposto do que o Bryan pediu em 25/08.
        rep = 1 if v.get("republicacao") else 0
        # Adiado vai atras de TODO mundo, republicacao inclusive. A chave sai
        # da LEGENDA (titulo como reserva), igual ao `cabe()` — calcular pelo
        # titulo nao bate, e foi assim que tres clipes que o Bryan tinha
        # vetado entraram na fila em 27/08/2026. Ver engine/adiados.py.
        adi = 1 if adiados.adiado(
            _chave_texto(v.get("legenda") or v.get("titulo") or "")) else 0
        fonte = v.get("fonte") or ""
        # inicio_s ausente (clipe antigo, de antes do manifesto) cai pro fim do
        # seu grupo em vez de quebrar a ordenação
        inicio = v.get("inicio_s")
        return (adi, rep, primeira_aparicao.get(fonte, ""), fonte,
                float("inf") if inicio is None else float(inicio))

    return sorted(itens, key=chave)


def proximos_horarios(agendados: list[dict], quantos: int,
                      conhecidos: list[dict] | None = None
                      ) -> list[datetime.datetime]:
    """Próximos slots livres da grade, em horário de São Paulo.

    Pula slot já ocupado (compara pela HORA, não pelo minuto exato, porque o
    minuto varia de propósito), slot que já passou, e dia que já bateu
    `MAX_POR_DIA`.

    `conhecidos` deve trazer agendados E enviados: a contagem por dia precisa
    do que já foi ao ar, senão um post que disparou de manhã deixa de contar e
    o dia estoura o teto. Sem isso, 26/08/2026 fechou com 11 posts.
    """
    def _dia_hora(p):
        if not p.get("dueAt"):
            return None
        d = (datetime.datetime.fromisoformat(p["dueAt"].replace("Z", "+00:00"))
             - datetime.timedelta(hours=FUSO_SP_H))
        return d.date(), d.hour

    ocupados = set()
    for p in agendados:
        dh = _dia_hora(p)
        if dh:
            ocupados.add(dh)

    # Os INSTANTES exatos do que ja' esta' agendado. O conjunto `ocupados` so'
    # guarda (dia, hora) e nao serve pra medir intervalo — 16:32 e 19:22 sao
    # horas diferentes e mesmo assim distam 2h50.
    instantes: list[datetime.datetime] = []
    for p in agendados:
        dh = _dia_hora(p)
        if dh:
            ocupados.add(dh)
        if p.get("dueAt"):
            instantes.append(
                (datetime.datetime.fromisoformat(p["dueAt"].replace("Z", "+00:00"))
                 - datetime.timedelta(hours=FUSO_SP_H)).replace(tzinfo=None))

    por_dia: dict[datetime.date, int] = {}
    for p in (conhecidos if conhecidos is not None else agendados):
        dh = _dia_hora(p)
        if dh:
            por_dia[dh[0]] = por_dia.get(dh[0], 0) + 1
    agora = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(hours=FUSO_SP_H)).replace(tzinfo=None)
    saida, dia = [], agora.date()
    while len(saida) < quantos:
        for h, m in SLOTS_SP:
            if len(saida) >= quantos:
                break
            minuto = min(57, max(3, m + random.randint(-VARIACAO_MIN, VARIACAO_MIN)))
            cand = datetime.datetime.combine(dia, datetime.time(h, minuto))
            if cand <= agora + datetime.timedelta(minutes=20):
                continue
            if (dia, h) in ocupados:
                continue
            if por_dia.get(dia, 0) >= MAX_POR_DIA:
                break
            # INTERVALO MINIMO, verificado DEPOIS da variacao. Compara com o
            # que ja' esta' no Buffer e com o que esta' sendo montado agora —
            # os dois grupos existem no mesmo dia e nenhum sozinho basta.
            vizinhos = [x for x in instantes + saida if x.date() == dia]
            perto = [x for x in vizinhos
                     if abs((cand - x).total_seconds()) < INTERVALO_MIN_H * 3600]
            if perto:
                # Empurra pra frente do vizinho mais tardio, em vez de
                # descartar o slot: descartar deixaria buraco no dia sem
                # necessidade.
                cand = max(perto) + datetime.timedelta(hours=INTERVALO_MIN_H)
                if cand.date() != dia or cand.hour >= 23:
                    continue          # nao cabe mais hoje, tenta amanha
                if any(abs((cand - x).total_seconds()) < INTERVALO_MIN_H * 3600
                       for x in vizinhos):
                    continue
            ocupados.add((dia, h))
            por_dia[dia] = por_dia.get(dia, 0) + 1
            saida.append(cand)
        dia += datetime.timedelta(days=1)
    return saida


def enfileirar(token: str, canal: str, clipe: dict, simular: bool,
               quando_sp: datetime.datetime | None = None) -> str:
    legenda = (clipe.get("legenda") or clipe.get("titulo") or "").strip()
    titulo = (clipe.get("titulo") or legenda.split("#")[0]).strip()[:90]
    if simular:
        return "SIMULADO"
    m = """mutation($input: CreatePostInput!) {
      createPost(input: $input) { __typename
        ... on PostActionSuccess { post { id status dueAt } }
        ... on RestProxyError { code message }
        ... on LimitReachedError { message }
        ... on InvalidInputError { message }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message } } }"""
    d = consultar(token, m, {"input": {
        "channelId": canal,
        "text": legenda,
        "mode": "customScheduled" if quando_sp else "addToQueue",
        "schedulingType": "automatic",
        **({"dueAt": (quando_sp + datetime.timedelta(hours=FUSO_SP_H))
             .strftime("%Y-%m-%dT%H:%M:%S.000Z")} if quando_sp else {}),
        "assets": [{"video": {"url": clipe["url"]}}],
        "metadata": {"tiktok": {"isAiGenerated": True, "title": titulo}},
    }})["createPost"]
    if d["__typename"] != "PostActionSuccess":
        raise RuntimeError(f"{d['__typename']}: {d.get('message', '')[:160]}")
    return d["post"].get("dueAt") or "sem horário"


def main() -> None:
    p = argparse.ArgumentParser(description="Enfileira clipes no Buffer")
    p.add_argument("--simular", action="store_true",
                   help="mostra o que faria, sem mandar nada")
    p.add_argument("--tag", help="usa só uma release (padrão: todas as clipes-*)")
    p.add_argument("--reserva", type=int, default=RESERVA_MANUAL,
                   help="vagas deixadas livres pro Bryan (padrão 1)")
    a = p.parse_args()

    tb, tg = _token_buffer(), _token_github()
    _, canal, conhecidos = contexto_buffer(tb)
    # `conhecidos` traz agendados E enviados (pra dedup). A CONTAGEM de vagas
    # usa so' os agendados — enviado ja' liberou o slot.
    agendados = [p for p in conhecidos if p.get("status") == "scheduled"]
    alvo = LIMITE_FILA - a.reserva
    vagas = alvo - len(agendados)
    print(f"fila: {len(agendados)}/{LIMITE_FILA} agendados, "
          f"{a.reserva} reservada(s) -> {max(0, vagas)} vaga(s) pra encher")
    if vagas <= 0:
        print("nada a fazer: fila cheia.")
        return

    todos = manifesto(tg, a.tag)
    if not todos:
        print("manifesto vazio — nenhum clipe publicado em release ainda.")
        return

    # Dois conjuntos diferentes de propósito:
    #  - `ja_na_fila`: o que está agendado agora. NADA pode repetir isso.
    #  - `ja_publicado`: o que o Buffer já enviou. Bloqueia clipe normal, mas
    #    NÃO bloqueia republicação: quando o Bryan apaga um vídeo do TikTok
    #    pra postar de novo pelo pipeline, o Buffer continua com o post antigo
    #    como "sent" — e tratar isso como duplicata apagaria justamente o que
    #    ele quer refazer. Aconteceu em 25/08 com "Exército Cria Baratas" e
    #    "A VERDADEIRA CORRIDA DA IA": eu removi os dois da fila por engano.
    ja_na_fila = {_chave_texto(x["text"]) for x in conhecidos
                  if x.get("status") == "scheduled"}
    ja_publicado = {_chave_texto(x["text"]) for x in conhecidos
                    if x.get("status") == "sent"}
    # A consulta acima para em MAX_PAGINAS pra nao gastar orcamento, entao ela
    # e' CEGA pro que e' antigo — foi essa cegueira que republicou um clipe em
    # 25/08/2026. `estado/publicados.json` guarda o historico completo em disco
    # e nao custa requisicao. Import tardio de proposito: historico.py importa
    # este modulo, e no topo isso seria circular.
    try:
        import historico
        offline = set(historico._ler_publicados())
        so_no_disco = offline - ja_publicado
        ja_publicado |= offline
        if so_no_disco:
            print(f"dedup: +{len(so_no_disco)} texto(s) so' no registro offline "
                  f"(alem dos {len(conhecidos)} que o Buffer devolveu)")
    except Exception as e:
        print(f"  [!] registro offline indisponivel ({str(e)[:80]}); "
              "dedup usando so' o que o Buffer devolveu.")

    rejeitados_ = rejeitados.chaves()

    def cabe(v):
        # ⚠️ RECUSA POR CONTEUDO, ANTES DE QUALQUER COMPARACAO DE TEXTO.
        #
        # Todas as guardas abaixo comparam TEXTO, e foi texto que falhou em
        # 31/08/2026 NESTE canal: 6 posts na fila, 6 titulos e 6 legendas
        # diferentes, um unico arquivo. Os textos eram de fato todos
        # diferentes — nenhuma dedup de texto podia enxergar.
        #
        # Clipe antigo nao tem sha no manifesto: ai' esta guarda nao opina e
        # as de texto seguem valendo.
        sha = v.get("sha")
        if sha and registro_clipes.ja_postado(sha):
            return False
        k = _chave_texto(v.get("legenda") or v.get("titulo") or "")
        # Comparacao por PREFIXO, nao por igualdade: 88 dos 101 posts reais
        # tem titulo e descricao na mesma linha, e a chave deles vira
        # titulo+descricao — nunca casaria com a chave de um clipe novo, que
        # e' so' o titulo. Ver engine/dedup.py.
        if dedup.ja_visto(k, ja_na_fila):
            return False
        # Apagado da fila pelo Bryan = decisão editorial, nunca reagendar.
        # Apagar post agendado não deixa rastro no Buffer, então sem esta lista
        # o clipe volta a parecer disponível — empurrei o mesmo três vezes em
        # 26/08/2026. Ver engine/rejeitados.py.
        if k in rejeitados_:
            return False
        return v.get("republicacao") or not dedup.ja_visto(k, ja_publicado)

    fila = [(k, v) for k, v in ordenar(todos) if cabe(v)]
    print(f"{len(todos)} clipe(s) no manifesto, {len(fila)} ainda não agendado(s)\n")

    horarios = proximos_horarios(agendados, max(0, vagas), conhecidos)
    # Casa a RECEITA com a HORA de comer: cafe da manha as 8h, almoco as 11h,
    # jantar as 19h. Antes era zip puro, e o primeiro clipe pegava o primeiro
    # slot sem olhar o que era — em 30/08 "3 Tacas de Cottage para o Cafe da
    # Manha" estava agendado pras 16:27, com a refeicao escrita no titulo.
    #
    # Conservador de proposito: so' reordena o que a refeicao exigir, e clipe
    # que nao casa com nada cai no comportamento antigo. Ver engine/refeicao.py.
    fila = refeicao.casar(fila, horarios)
    enviados = 0
    for (chave, clipe), quando in zip(fila, horarios):
        if enviados >= vagas:
            break
        titulo = (clipe.get("titulo") or "")[:56]
        try:
            quando_txt = enfileirar(tb, canal, clipe, a.simular, quando_sp=quando)
        except Exception as e:
            print(f"  [!] {titulo}: {str(e)[:140]}")
            continue
        ini = clipe.get("inicio_s")
        pos = f"{float(ini):.0f}s do fonte" if ini is not None else "posição ?"
        print(f"  nota {clipe.get('nota', 0):.0f}  {pos:>14}  {titulo}")
        print(f"       -> {quando_txt}")
        enviados += 1

    print(f"\n{enviados} clipe(s) {'simulado(s)' if a.simular else 'enfileirado(s)'}; "
          f"{len(fila) - enviados} esperando a próxima vaga.")


if __name__ == "__main__":
    main()
