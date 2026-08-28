"""Gera a agenda de postagem com os minutos sorteados a cada dia.

    python agenda_postagem.py                 # próximos 14 dias
    python agenda_postagem.py --dias 30
    python agenda_postagem.py --slots 3       # só os 3 primeiros horários
    python agenda_postagem.py --csv agenda.csv

Por que os minutos variam
-------------------------
Pedido do Bryan em 31/07/2026: postar 11:30 cravado todo dia é assinatura de
robô, e comportamento de robô é o que o antifraude do TikTok procura — seis
fontes do corpus `destravar-tiktok` dizem que conta lida como bot tem o
alcance limitado por COMPORTAMENTO, não por qualidade do vídeo. Minuto
sorteado dentro de uma faixa mantém a janela e tira a cadência mecânica.

O sorteio é SEMEADO PELA DATA. Rodar duas vezes no mesmo dia devolve a mesma
agenda — sem isso, cada consulta daria um horário diferente e a agenda não
serviria pra nada. Dias diferentes dão minutos diferentes.

De onde vêm os horários-âncora
------------------------------
Do cruzamento de duas fontes do corpus que dão horário (uma manda "depois das
10h, depois do meio-dia, depois das 16h, depois das 18h"; a outra dá as
janelas 11h-13h, 15h-17h e 18h-22h). Os quatro abaixo são onde as duas
concordam.

⚠️ Força da evidência: [FRACO]. Três fontes dão horário, TRÊS OUTRAS dizem que
horário não faz diferença nenhuma. Isto é chute educado até o painel do
TikTok ter dado próprio — o `FollowerActivity.csv` exportado em 30/07 veio
VAZIO, porque com 5 seguidores não há o que medir. Quando houver, troque
estas âncoras pelo horário real da audiência: é o que o PLAYBOOK manda.

Quatro e não cinco
------------------
Uma fonte é explícita: o TikTok recomenda de 1 a 4 por dia, e acima de 4 pode
tratar como spam. A conta tem poucos dias de vida e já postou 6 num dia só —
não é hora de testar esse teto.
"""
import argparse
import csv
import datetime as dt
import random

# (hora, minuto-base, apelido). O minuto real sai do sorteio em volta daqui.
ANCORAS = [
    (11, 30, "manhã"),
    (13, 0, "almoço"),
    (16, 30, "tarde"),
    (19, 0, "noite"),
]

# Quanto o minuto pode variar para cada lado. 7 dá 15 minutos de faixa, o
# bastante para não repetir e pouco para não sair da janela das fontes.
JITTER_MIN = 7


def agenda(inicio: dt.date, dias: int, slots: int = len(ANCORAS),
           jitter: int = JITTER_MIN) -> list[dict]:
    linhas = []
    for d in range(dias):
        data = inicio + dt.timedelta(days=d)
        # Semente pela data: mesma data, mesma agenda, sempre.
        rnd = random.Random(f"modofuturo-{data.isoformat()}")
        for h, m, apelido in ANCORAS[:slots]:
            minuto = m + rnd.randint(-jitter, jitter)
            hora = h
            if minuto < 0:
                hora, minuto = hora - 1, minuto + 60
            elif minuto > 59:
                hora, minuto = hora + 1, minuto - 60
            linhas.append({
                "data": data.isoformat(),
                "dia_semana": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][data.weekday()],
                "hora": f"{hora:02d}:{minuto:02d}",
                "faixa": apelido,
            })
    return linhas


def semanal(jitter: int = JITTER_MIN, slots: int = len(ANCORAS)) -> list[dict]:
    """Um horário diferente por DIA DA SEMANA, para configurar UMA VEZ.

    Existe por causa de como as ferramentas funcionam. Publer e Buffer têm
    "time slots" por dia da semana: você configura os horários uma vez, joga
    os vídeos na fila, e a ferramenta agenda sozinha no próximo slot livre —
    sem escolher horário vídeo a vídeo.

    Só que o slot é FIXO. Para ter minuto variado sem pagar pelo agendamento
    em massa, a variação passa a ser semanal em vez de diária: 28 horários
    distintos (7 dias × 4), configurados uma vez, repetindo toda semana.

    É menos aleatório que sortear por dia — mas some a assinatura de "11:30
    cravado, todo dia", que é o que interessa, e não exige manutenção.
    """
    nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    linhas = []
    for i, nome in enumerate(nomes):
        rnd = random.Random(f"modofuturo-semana-{nome}")
        for h, m, apelido in ANCORAS[:slots]:
            minuto = m + rnd.randint(-jitter, jitter)
            hora = h
            if minuto < 0:
                hora, minuto = hora - 1, minuto + 60
            elif minuto > 59:
                hora, minuto = hora + 1, minuto - 60
            linhas.append({"dia_semana": nome, "hora": f"{hora:02d}:{minuto:02d}",
                           "faixa": apelido})
    return linhas


def main():
    p = argparse.ArgumentParser(description="Agenda de postagem com minutos sorteados")
    p.add_argument("--semanal", action="store_true",
                   help="tabela por dia da semana, para configurar os time "
                        "slots do Publer/Buffer uma vez só")
    p.add_argument("--publer", action="store_true",
                   help="CSV no formato do Publer (data AAAA/MM/DD, hora HH:MM)")
    p.add_argument("--dias", type=int, default=14)
    p.add_argument("--slots", type=int, default=len(ANCORAS),
                   help=f"quantos posts por dia (máx {len(ANCORAS)})")
    p.add_argument("--jitter", type=int, default=JITTER_MIN,
                   help=f"variação do minuto, para cada lado (padrão {JITTER_MIN})")
    p.add_argument("--inicio", help="AAAA-MM-DD (padrão: hoje)")
    p.add_argument("--csv", help="grava também num CSV")
    a = p.parse_args()

    inicio = dt.date.fromisoformat(a.inicio) if a.inicio else dt.date.today()
    nslots = min(a.slots, len(ANCORAS))

    if a.semanal:
        print("Time slots por dia da semana — configure UMA VEZ no Publer/Buffer\n")
        atual = None
        for l in semanal(a.jitter, nslots):
            if l["dia_semana"] != atual:
                atual = l["dia_semana"]
                print(f"\n  {atual:<9}", end=" ")
            print(f"{l['hora']}", end="  ")
        print("\n\n  Depois é só jogar os vídeos na fila: a ferramenta encaixa")
        print("  cada um no próximo slot livre, sem você escolher horário.")
        return

    linhas = agenda(inicio, a.dias, nslots, a.jitter)

    print(f"Agenda — {a.dias} dia(s), {min(a.slots, len(ANCORAS))} post(s) por dia, "
          f"minuto sorteado ±{a.jitter} (horário de Brasília)\n")
    atual = None
    for l in linhas:
        if l["data"] != atual:
            atual = l["data"]
            d = dt.date.fromisoformat(atual)
            print(f"\n  {d.strftime('%d/%m')} {l['dia_semana']}", end="  ")
        print(f"{l['hora']}", end="  ")
    print("\n")

    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as f:
            if a.publer:
                # Formato que o Publer lê no import em massa: data AAAA/MM/DD e
                # hora HH:MM em 24h, uma linha por post. As colunas de texto e
                # mídia ficam vazias — você preenche com a legenda do .txt de
                # cada clipe e o arquivo do vídeo.
                w = csv.writer(f)
                w.writerow(["Date", "Time", "Text", "Media URL"])
                for l in linhas:
                    w.writerow([l["data"].replace("-", "/"), l["hora"], "", ""])
            else:
                w = csv.DictWriter(f, fieldnames=["data", "dia_semana", "hora", "faixa"])
                w.writeheader()
                w.writerows(linhas)
        print(f"→ {a.csv} ({len(linhas)} horários"
              f"{', formato Publer' if a.publer else ''})")


if __name__ == "__main__":
    main()
