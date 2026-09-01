# -*- coding: utf-8 -*-
"""Consome a fila de cortes, no maximo 2 por vez.

Pedido do Bryan em 31/08/2026: "vamos de 2 em 2 ate' cortar tudo".

POR QUE ISTO EXISTE COMO MAQUINA, E NAO COMO EU DISPARANDO

Eu nao rodo entre os turnos do Bryan. Um plano do tipo "vou disparando ao
longo da noite" so' funciona se ele ficar me cutucando — e ele pediu
justamente pra nao precisar. Entao quem conta os runs e dispara e' o cron.

⚠️ O TETO DE 2 E' O REPARO DE UM ERRO MEDIDO. Em 31/08/2026 disparei 10 runs
em paralelo. NOVE morreram: as 40 chaves do Gemini secaram no meio do
caminho. As fontes ficaram intactas, mas o runner foi embora. Dois de cada
vez cabe na cota; dez nao cabe.

⚠️ SONDA A COTA ANTES DE DISPARAR. Sem isto, uma noite inteira de cron vira
uma noite inteira de runs mortos com a mesma falha, um a cada 30 minutos. Se
nao ha' cota, este script NAO dispara e diz por que.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
FILA = RAIZ / "fila_cortes.json"
REPO = os.environ.get("GITHUB_REPOSITORY") or "bryanaw2121-sketch/pipeline"
WF = "cortar_do_drive.yml"
PASTA_DRIVE = "1aM22tjWvoWLTv9v1PrICUzk0_763xcUK"   # "a postar" da conta reserva


def _gh(caminho: str, dados: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{caminho}",
        data=json.dumps(dados).encode() if dados is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        corpo = r.read()
        return json.loads(corpo) if corpo else {}


def em_voo() -> int:
    """Runs de corte ainda vivos. E' o numero que o teto limita."""
    n = 0
    for st in ("queued", "in_progress"):
        d = _gh(f"actions/workflows/{WF}/runs?status={st}&per_page=50")
        n += len(d.get("workflow_runs", []))
    return n


def tem_cota() -> tuple[bool, str]:
    """Alguma chave do Gemini responde 200? So' o 200 libera o disparo.

    ⚠️ UMA CHAVE SO' NAO DECIDE NADA. A primeira versao disto sondava a
    `GEMINI_API_KEY` e liberava em qualquer coisa que nao fosse 429. Em
    31/08/2026 essa chave respondeu 503 — sobrecarga, nao cota — a sonda
    liberou, e os DOIS runs morreram na selecao com as 20 chaves esgotadas.
    A leitura estava certa e a conclusao errada: 503 numa chave nao diz nada
    sobre as outras dezenove.

    ⚠️ E 429 CONTINUA SENDO DIFERENTE DE 503. Nao voltei a juntar os dois: a
    mensagem final distingue "sem cota" (espere o reset) de "sobrecarregado"
    (tente de novo daqui a pouco), porque sao esperas de tamanhos diferentes.
    O que mudou e' que agora o SILENCIO tambem barra — sem um 200 na mao,
    nao gasto runner.
    """
    # ⚠️ TODAS AS CHAVES DO RODIZIO, nao uma amostra fixa.
    #
    # Ate' 01/09/2026 esta lista tinha cinco nomes escritos a mao — e os
    # secrets do repo NAO se chamam assim (sao GEMINI4..GEMINI19 mais
    # GEMINI_API_KEY_1/2/3/20). Na nuvem a sonda enxergava DUAS chaves de
    # vinte e decidia o teto de corte com essa amostra.
    #
    # O intervalo e' o mesmo do `keys.Rotador`: prefixo puro e depois
    # _2.._40. Ler o que o motor le' e' a unica forma de a sonda medir a
    # mesma coisa que o corte vai usar.
    nomes = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 41)]
    chaves = [v for v in (os.environ.get(n) for n in nomes) if (v or "").strip()]

    # ⚠️ AMOSTRA, NAO CENSO — E A RAZAO E' QUE A SONDA SE AUTO-SABOTAVA.
    #
    # MEDIDO em 01/09/2026: uma consulta direta as 14 chaves devolveu 10 em
    # 200. A sonda do script, SEGUNDOS DEPOIS, devolveu "1 ok, 8 sem cota" —
    # as mesmas chaves. Bater em todas duas vezes dentro do mesmo minuto
    # estoura o limite POR MINUTO do Gemini, e o 429 resultante era lido como
    # "cota diaria esgotada". A sonda causava o que media, e rebaixava o teto
    # de corte por causa disso.
    #
    # Uma amostra aleatoria de 5 e' representativa o bastante pra decidir
    # entre 3, 2 e 1, e nao chega perto do limite por minuto.
    #
    # ⚠️ ALEATORIA, nao "as cinco primeiras": chave fixa seria sempre a mesma
    # a ser gasta, e a amostra deixaria de representar o rodizio inteiro.
    import random
    if len(chaves) > 5:
        chaves = random.sample(chaves, 5)
    if not chaves:
        return True, "nenhuma chave pra sondar — seguindo sem sonda"

    # ⚠️ EM PARALELO, E COM TIMEOUT CURTO. A primeira versao consultava as
    # chaves uma a uma com 20s de espera cada: com 20 chaves, a sonda sozinha
    # levava minutos e atrasava TODO disparo. Aqui o custo e' o da chave mais
    # lenta, nao a soma.
    #
    # 8s basta: o que se pergunta e' se a chave responde, nao o conteudo. Uma
    # chave que demora mais que isso nao serve pra decidir teto de corte.
    from concurrent.futures import ThreadPoolExecutor

    def _sondar(chave: str) -> str:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.6-flash:generateContent?key={chave.strip()}",
            data=json.dumps({"contents": [{"parts": [{"text": "oi"}]}]}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=8)
            return "ok"
        except urllib.error.HTTPError as e:
            return "sem cota" if e.code == 429 else "sobrecarregado"
        except Exception:
            return "mudo"

    placar = {"ok": 0, "sem cota": 0, "sobrecarregado": 0, "mudo": 0}
    with ThreadPoolExecutor(max_workers=min(10, len(chaves))) as pool:
        for r in pool.map(_sondar, chaves):
            placar[r] += 1

    resumo = ", ".join(f"{v} {k}" for k, v in placar.items() if v)
    if placar["ok"]:
        return True, f"{placar['ok']} de {len(chaves)} chaves com cota ({resumo})"
    return False, f"nenhuma das {len(chaves)} chaves respondeu 200 ({resumo})"


def teto_pela_cota(motivo: str, teto_pedido: int) -> tuple[int, str]:
    """Quantos cortes deixar em voo, dado o que a sonda enxergou.

    ⚠️ PERGUNTA DO BRYAN em 01/09/2026: "se colocarmos mais um pra cortar, de
    3 em 3, sera' que da' problema?". A medicao diz que 3 nao consome MAIS
    cota — consome mais RAPIDO. Os mesmos videos fazem as mesmas chamadas
    (~3 a 6 por run: selecao, traducao por clipe, legenda premium).

    O que muda e' o PREJUIZO quando a cota acaba. Um run que morre ja' pagou
    corte, estabilizacao, transcricao e as vezes render — 40 a 100 minutos de
    runner. Com 2 em voo perdem-se dois; com 3, tres. Foi o que aconteceu com
    os 10 em paralelo de 31/08: nove morreram carregando trabalho ja' pago.

    Ou seja: 3 e' melhor que 2 ENQUANTO ha' cota, e pior que 2 quando ela
    aperta. Numero fixo obriga a escolher um dos dois cenarios — por isso o
    teto segue a medida.

    ⚠️ O TETO PEDIDO E' O MAXIMO, nunca o minimo. Cota folgada nao autoriza
    passar do que o Bryan pediu; ela so' permite CHEGAR la'.
    """
    import re as _re
    m = _re.match(r"(\d+) de (\d+) chaves com cota", motivo)
    if not m:
        return teto_pedido, "sem contagem de chaves — teto como pedido"
    ok, total = int(m.group(1)), int(m.group(2))
    fatia = ok / max(1, total)
    if fatia >= 0.5:
        return teto_pedido, f"cota folgada ({ok}/{total}) — teto {teto_pedido}"
    if ok >= 2:
        return min(2, teto_pedido), f"cota apertada ({ok}/{total}) — teto 2"
    return 1, f"cota no fim ({ok}/{total}) — um de cada vez"


def fonte_sumiu(run_id: int) -> bool:
    """O run morreu porque o BRUTO nao existe mais no Drive?

    ⚠️ ISTO NAO SE RESOLVE TENTANDO DE NOVO. O pipeline apaga o bruto depois
    de um corte bem-sucedido, pra nao estourar a cota do Drive. Se o item da
    fila ainda aponta pra esse id, toda tentativa vai dar 404 — e cada uma
    custa um runner inteiro sendo provisionado.

    MEDIDO em 01/09/2026: o run #235 morreu com
    `HttpError 404 ... /files/1IV7OQ8AdKXWW5_8s0N01XzsZEuM35CRc` — o bruto do
    "MY GO TO GLUTE WORKOUT", apagado depois que o #202 cortou com sucesso. O
    Bryan chegou a subir o mesmo video de novo, mas com id NOVO; o item velho
    ficou na fila apontando pro tumulo.
    """
    t = _log_do_run(run_id)
    if t is None:
        return False
    return "HttpError 404" in t and "drive/v3/files" in t


def _log_do_run(run_id: int) -> str | None:
    """Texto do log, ou None quando nao da' pra ler."""
    try:
        import io as _io
        import zipfile
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/logs",
            headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            z = zipfile.ZipFile(_io.BytesIO(r.read()))
        return "".join(z.read(n).decode("utf-8", "replace")
                       for n in z.namelist() if n.endswith(".txt"))
    except Exception as e:
        print(f"    [!] nao li o log do run {run_id} ({str(e)[:50]})")
        return None


def horizonte_dos_canais() -> dict:
    """Horas de fila que cada canal ainda tem no Buffer.

    ⚠️ E' ISTO QUE DECIDE A ORDEM DOS CORTES, e antes nada decidia: a fila era
    consumida na ordem em que eu escrevi os itens. Em 01/09/2026 isso deixou o
    @truque.importado — com 42 HORAS de folga — ocupando vaga na frente do
    @semanestesia.pod e do @atefalhar, que tinham DUAS.

    Cortar pra quem ja' tem fila enquanto outro canal fica vazio e' gastar
    runner no lugar errado. O Bryan: "temos que focar em cozinha, sem
    anestesia e ate' falhar, estao com muito poucos cortes".

    ⚠️ Canal sem leitura fica com horizonte DESCONHECIDO e vai pro fim, nao
    pro comeco. Um token que falhou nao pode virar prioridade maxima por
    acidente — seria o alarme falso decidindo o gasto.
    """
    horizonte = {}
    agora = datetime.now(timezone.utc)
    for canal, (org, ch, env) in CANAIS_BUFFER.items():
        token = (os.environ.get(env) or "").strip()
        if not token:
            continue
        try:
            req = urllib.request.Request(
                "https://api.buffer.com/",
                data=json.dumps({"query": Q_FILA, "variables": {"i": {
                    "organizationId": org,
                    "filter": {"status": ["scheduled"],
                               "channelIds": [ch]}}}}).encode(),
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=40))
            ds = sorted(e["node"]["dueAt"]
                        for e in d["data"]["posts"]["edges"])
        except Exception:
            continue
        if not ds:
            horizonte[canal] = 0.0
            continue
        fim = datetime.fromisoformat(ds[-1].replace("Z", "+00:00"))
        horizonte[canal] = max(0.0, (fim - agora).total_seconds() / 3600)
    return horizonte


# ⚠️ UM CANAL SO'. A ordenacao por folga existe pro outro motor, que
# reparte cortes entre quatro canais; aqui ela nao tem o que ordenar, e a
# leitura do Buffer serve apenas pro relato.
CANAIS_BUFFER = {
    "cozinha.internacional": ("6a90dddb9bb05f07b058e9bc",
                              "6a90de80ccaf649a672ebe15", "BUFFER_TOKEN"),
}
Q_FILA = "query($i: PostsInput!){ posts(input:$i){ edges{ node{ dueAt } } } }"


def falhou_por_cota(run_id: int) -> bool | None:
    """O run morreu por cota do Gemini? None quando nao deu pra saber.

    ⚠️ ESTA FUNCAO EXISTE PORQUE O CONTADOR PUNIA A FONTE PELO AMBIENTE.
    Em 01/09/2026 o cron DESISTIU de "The Only 13 Minutes You Need To Master
    Discipline" depois de 3 tentativas — e as tres foram cota do Gemini, nao
    defeito nenhum do video. A fonte estava perfeita e saiu da fila.

    Teto de tentativas existe pra fonte quebrada (bruto corrompido, id que
    sumiu do Drive). Cota e' espera, nao defeito: contar as duas coisas no
    mesmo contador joga fora material bom.
    """
    try:
        import io as _io
        import zipfile
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/logs",
            headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            bruto = r.read()
        z = zipfile.ZipFile(_io.BytesIO(bruto))
        texto = "".join(
            z.read(n).decode("utf-8", "replace")
            for n in z.namelist() if n.endswith(".txt"))
    except Exception as e:
        print(f"    [!] nao li o log do run {run_id} ({str(e)[:50]})")
        return None
    # ⚠️ A COTA ESTOURA EM DOIS PASSOS, COM MENSAGENS DIFERENTES, e a
    # primeira versao so' conhecia uma delas:
    #
    #   traducao:  "as N chaves do Gemini estao SEM COTA"
    #   selecao:   "Gemini falhou em escolha de clipes: todas as chaves
    #               esgotadas em ['gemini-3.6-flash']"
    #
    # Resultado MEDIDO em 01/09/2026: o "Stop Being F cking Weak" falhou tres
    # vezes por cota NA SELECAO, nenhuma foi reconhecida, e o cron DESISTIU de
    # uma fonte perfeita. E' o mesmo defeito que ja' tinha me pegado hoje —
    # detector que casa com UMA frase enxerga UMA classe.
    MARCAS = ("SEM COTA", "chaves do Gemini", "todas as chaves esgotadas",
              "sem quota")
    return any(m in texto for m in MARCAS)


def teto_pela_cota(motivo: str, teto_pedido: int) -> tuple[int, str]:
    """Quantos cortes deixar em voo, dado o que a sonda enxergou.

    ⚠️ PERGUNTA DO BRYAN em 01/09/2026: "se colocarmos mais um pra cortar, de
    3 em 3, sera' que da' problema?". A medicao diz que 3 nao consome MAIS
    cota — consome mais RAPIDO. Os mesmos videos fazem as mesmas chamadas
    (~3 a 6 por run: selecao, traducao por clipe, legenda premium).

    O que muda e' o PREJUIZO quando a cota acaba. Um run que morre ja' pagou
    corte, estabilizacao, transcricao e as vezes render — 40 a 100 minutos de
    runner. Com 2 em voo perdem-se dois; com 3, tres. Foi o que aconteceu com
    os 10 em paralelo de 31/08: nove morreram carregando trabalho ja' pago.

    Ou seja: 3 e' melhor que 2 ENQUANTO ha' cota, e pior que 2 quando ela
    aperta. Numero fixo obriga a escolher um dos dois cenarios — por isso o
    teto segue a medida.

    ⚠️ O TETO PEDIDO E' O MAXIMO, nunca o minimo. Cota folgada nao autoriza
    passar do que o Bryan pediu; ela so' permite CHEGAR la'.
    """
    import re as _re
    m = _re.match(r"(\d+) de (\d+) chaves com cota", motivo)
    if not m:
        return teto_pedido, "sem contagem de chaves — teto como pedido"
    ok, total = int(m.group(1)), int(m.group(2))
    fatia = ok / max(1, total)
    if fatia >= 0.5:
        return teto_pedido, f"cota folgada ({ok}/{total}) — teto {teto_pedido}"
    if ok >= 2:
        return min(2, teto_pedido), f"cota apertada ({ok}/{total}) — teto 2"
    return 1, f"cota no fim ({ok}/{total}) — um de cada vez"


def devolver_os_que_falharam(d: dict) -> list[str]:
    """Item cujo run falhou volta pra `pendente`. Sem isto a fila DRENA.

    ⚠️ ERA UM DEFEITO REAL, nao precaucao: o item era marcado `disparado` e
    ficava assim pra sempre. Um run que morre por cota levava a fonte junto,
    e ao fim da noite a fila estaria vazia com zero corte feito — o cron
    tocando alegremente pra ninguem.

    ⚠️ TEM TETO DE TENTATIVAS. Sem ele, uma fonte defeituosa (bruto corrompido,
    id que sumiu do Drive) voltaria pra fila pra sempre, queimando dois runs a
    cada meia hora, e a fila nunca andaria.
    """
    voltaram = []
    for item in d["itens"]:
        if item.get("estado") != "disparado" or not item.get("run_id"):
            continue
        try:
            r = _gh(f"actions/runs/{item['run_id']}")
        except Exception:
            continue
        if r.get("status") != "completed":
            continue
        if r.get("conclusion") == "success":
            item["estado"] = "pronto"
            continue
        # ⚠️ COTA NAO CONTA COMO TENTATIVA. Ver `falhou_por_cota`: o teto
        # existe pra fonte quebrada, nao pra espera de ambiente. Contar as
        # duas coisas junto ja' fez o cron desistir de uma fonte boa.
        # ⚠️ FONTE APAGADA E' TERMINAL. Devolver pra fila faria o item bater
        # em 404 pra sempre, dois runs a cada rodada, sem nunca cortar nada.
        if fonte_sumiu(item["run_id"]):
            item["estado"] = "sem_fonte"
            item.pop("run_id", None)
            voltaram.append(f"  SEM FONTE no Drive: {item['nome'][:40]} "
                            f"(bruto apagado apos corte anterior)")
            continue
        cota = falhou_por_cota(item["run_id"])
        item["estado"] = "pendente"
        item.pop("run_id", None)
        if cota:
            voltaram.append(f"  volta pra fila: {item['nome'][:40]}"
                            f" (COTA — nao conta como tentativa)")
            continue
        # ⚠️ `None` (nao deu pra ler o log) CONTA. Preferir nao contar deixaria
        # uma fonte de fato quebrada girando pra sempre, dois runs a cada meia
        # hora, e a fila nunca andaria.
        item["tentativas"] = int(item.get("tentativas") or 0) + 1
        if item["tentativas"] >= 3:
            item["estado"] = "desistido"
            voltaram.append(f"  DESISTI de {item['nome'][:40]} (3 tentativas"
                            f" que NAO foram cota)")
        else:
            voltaram.append(f"  volta pra fila: {item['nome'][:40]}"
                            f" (tentativa {item['tentativas']})")
    return voltaram


def run_recem_criado() -> int | None:
    """O id do run que acabamos de disparar.

    A API de dispatch nao devolve o id. Como o workflow tem `concurrency` e
    esta e' a unica coisa que dispara corte automaticamente, o run mais novo
    e' o nosso. Se nao aparecer a tempo, devolve None e o item fica sem id —
    o que so' custa nao poder devolve-lo pra fila depois.
    """
    import time
    for _ in range(10):
        time.sleep(3)
        d = _gh(f"actions/workflows/{WF}/runs?per_page=1")
        runs = d.get("workflow_runs") or []
        if runs:
            return runs[0]["id"]
    return None


def main() -> None:
    d = json.loads(FILA.read_text(encoding="utf-8"))
    teto = int(os.environ.get("TETO") or d.get("teto_em_voo") or 2)

    # ⚠️ ANTES DE QUALQUER COISA: recolher os que falharam. Se isto rodasse
    # depois do disparo, um item que falhou continuaria fora da conta e a
    # fila andaria pra frente sem ele.
    devolvidos = devolver_os_que_falharam(d)
    for linha in devolvidos:
        print(linha)
    if devolvidos:
        FILA.write_text(json.dumps(d, ensure_ascii=False, indent=2) + chr(10),
                        encoding="utf-8")

    pendentes = [i for i in d["itens"] if i["estado"] == "pendente"]

    if not pendentes:
        print("fila vazia — nada pendente")
        Path("relato_cortes.txt").write_text(
            "Fila de cortes VAZIA — tudo que estava pendente ja' foi disparado.",
            encoding="utf-8")
        return

    voando = em_voo()
    vagas = max(0, teto - voando)
    print(f"em voo: {voando} | teto: {teto} | vagas: {vagas} | pendentes: {len(pendentes)}")
    if not vagas:
        print("sem vaga — o cron tenta de novo na proxima passada")
        return

    ok, motivo = tem_cota()
    print(f"sonda de cota: {motivo}")
    if ok:
        teto, porque = teto_pela_cota(motivo, teto)
        vagas = max(0, teto - voando)
        print(f"teto pela cota: {porque} -> {vagas} vaga(s)")
    if not ok:
        Path("relato_cortes.txt").write_text(
            f"Nao disparei: {motivo}. Restam {len(pendentes)} na fila.",
            encoding="utf-8")
        return

    linhas = []
    # ⚠️ ORDENA POR NECESSIDADE, nao pela ordem em que os itens foram
    # escritos. Canal sem leitura vai pro FIM (999), nunca pro comeco.
    h = horizonte_dos_canais()
    if h:
        pendentes.sort(key=lambda i: h.get(i["canal"], 999.0))
        print("  ordem por folga: " + ", ".join(
            f"{c}={h[c]:.0f}h" for c in sorted(h, key=h.get)))

    for item in pendentes[:vagas]:
        # ⚠️ ESTE WORKFLOW TEM OUTRA ASSINATURA. Ele recebe `arquivo_id`,
        # nao `drive_file_id`, e nao tem os campos de voz/canal — o motor da
        # cozinha atende um canal so'. Copiar as entradas do outro daria 422.
        entradas = {
            "arquivo_id": item["drive_file_id"],
            "qtd": item["qtd"],
            "idioma": "en",
        }
        _gh(f"actions/workflows/{WF}/dispatches",
            {"ref": "main", "inputs": entradas})
        item["estado"] = "disparado"
        item["quando"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rid = run_recem_criado()
        if rid:
            item["run_id"] = rid
        linhas.append(f"  {item['canal']:<18} {item['nome'][:46]}")
        print(f"disparado: {item['canal']} — {item['nome'][:50]}")

    FILA.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    restam = sum(1 for i in d["itens"] if i["estado"] == "pendente")
    Path("relato_cortes.txt").write_text(
        f"Disparei {len(linhas)} corte(s):\n" + "\n".join(linhas)
        + f"\n\nRestam {restam} na fila.", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
