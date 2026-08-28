"""Põe a numeração (001_, 002_, ...) nos clipes que JÁ estão em 'A POSTAR'.

Os clipes novos já saem numerados do `subir_drive.py`. Este script é para o
acervo anterior — em 30/07/2026 eram 138 clipes na pasta 29-07, cujo nome
começava pela nota, e nota repete.

Faz duas coisas, e só elas: RENOMEIA (põe o número na frente, mantendo o
nome antigo inteiro — `nota95_01_nota95_Titulo` → `003_nota95_01_nota95_Titulo`)
e MOVE cada clipe para a subpasta `parte NN` que lhe cabe. Não apaga arquivo,
não baixa e não sobe nada: o conteúdo não é tocado, e mover no Drive é trocar
de pai, não copiar — o id do arquivo continua o mesmo.

A única coisa que ele descarta é subpasta `parte NN` que ficou VAZIA (o que
acontece ao diminuir a quantidade de clipes por pasta), e mesmo essa vai para
a lixeira, nunca em definitivo.

Por padrão só MOSTRA o que faria. Nada muda sem `--aplicar`.

    python renumerar_a_postar.py                      # todas as pastas, simulação
    python renumerar_a_postar.py --dia 29-07           # uma pasta só
    python renumerar_a_postar.py --dia 29-07 --aplicar # renomeia de verdade
    python renumerar_a_postar.py --conta reserva --aplicar
    python renumerar_a_postar.py --digitos 4 --aplicar # se um dia passar de 999

O par .mp4/.txt do mesmo clipe recebe SEMPRE o mesmo número — eles são
casados pelo nome sem extensão, não pela ordem em que o Drive devolve.

Rodar duas vezes é seguro: a numeração antiga é reconhecida e substituída,
nunca empilhada (`numeracao.sem_prefixo`).
"""
import argparse
import sys
from collections import defaultdict

import contas_drive
import numeracao


def _itens(servico, pasta_id: str) -> list[dict]:
    """Todos os arquivos do dia, incluindo os que já estão dentro de uma
    `parte NN`, com o id da pasta onde cada um está hoje (`_pai`).

    Paginado: sem isso a pasta 29-07 (276 itens) voltaria cortada, e
    renumerar meia pasta é pior que não renumerar.
    """
    achados, token = [], None
    while True:
        r = servico.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000, pageToken=token).execute()
        for f in r.get("files", []):
            if "folder" in f["mimeType"]:
                # Só desce em `parte NN`. Qualquer outra subpasta é coisa que
                # o Bryan criou na mão, e mexer nela não foi pedido.
                if numeracao.e_parte(f["name"]):
                    achados.extend(_itens(servico, f["id"]))
                continue
            achados.append({**f, "_pai": pasta_id})
        token = r.get("nextPageToken")
        if not token:
            return achados


def _achar_ou_criar_subpasta(servico, pai_id: str, nome: str) -> str:
    """Acha a subpasta pelo nome; cria se não existir.

    Cópia deliberada da mesma função do `subir_drive.py`: importar de lá
    arrastaria config, telegram e publicar_tiktok para um script que só
    renomeia arquivo, e é o tipo de dependência que quebra a portabilidade
    sem dar nada em troca.
    """
    q = (f"'{pai_id}' in parents and name = '{nome}' "
         "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    achados = servico.files().list(q=q, fields="files(id, name)").execute().get("files", [])
    if achados:
        return achados[0]["id"]
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder",
            "parents": [pai_id]}
    return servico.files().create(body=meta, fields="id").execute()["id"]


def _pastas_do_dia(servico, a_postar_id: str, dia: str | None) -> list[dict]:
    q = (f"'{a_postar_id}' in parents and trashed = false "
         "and mimeType = 'application/vnd.google-apps.folder'")
    if dia:
        q += f" and name = '{dia}'"
    r = servico.files().list(q=q, fields="files(id, name)", orderBy="name").execute()
    return r.get("files", [])


def _grupos(itens: list[dict]) -> list[tuple[str, list[dict]]]:
    """Um clipe = um grupo. Junta o .mp4 e o .txt pelo nome sem extensão para
    os dois receberem o mesmo número, e devolve na ordem da numeração
    (melhor nota primeiro)."""
    por_base = defaultdict(list)
    for it in itens:
        if "folder" in it["mimeType"]:
            continue                       # subpasta inesperada: não numera
        base = it["name"].rsplit(".", 1)[0]
        por_base[base].append(it)
    return sorted(por_base.items(), key=lambda kv: numeracao.chave_de_ordem(kv[0]))


def renumerar(conta_nome: str, dia: str | None, aplicar: bool, digitos: int,
              por_pasta: int = numeracao.POR_PASTA) -> int:
    conta = contas_drive.conta_por_nome(conta_nome)
    servico = contas_drive.servico(conta)

    pastas = _pastas_do_dia(servico, conta["a_postar"], dia)
    if not pastas:
        print(f"[{conta_nome}] nenhuma pasta do dia"
              f"{f' chamada {dia}' if dia else ''} em A POSTAR.")
        return 0

    total = 0
    for pasta in pastas:
        grupos = _grupos(_itens(servico, pasta["id"]))
        n_partes = -(-len(grupos) // por_pasta) if grupos else 0
        print(f"\n[{conta_nome}] pasta {pasta['name']} — "
              f"{len(grupos)} clipe(s) em {n_partes} parte(s) de {por_pasta}")

        # As partes que JÁ existem, lidas sem criar nada — a simulação não
        # pode deixar pasta vazia pra trás no Drive. O que faltar é criado
        # adiante, e só com --aplicar.
        partes: dict[str, str] = {
            f["name"]: f["id"]
            for f in servico.files().list(
                q=(f"'{pasta['id']}' in parents and trashed = false and "
                   "mimeType = 'application/vnd.google-apps.folder'"),
                fields="files(id, name)", pageSize=1000).execute().get("files", [])
            if numeracao.e_parte(f["name"])}

        def _id_da_parte(nome: str) -> str:
            if nome not in partes:
                partes[nome] = _achar_ou_criar_subpasta(servico, pasta["id"], nome)
            return partes[nome]

        mudanças = 0
        for numero, (base, arquivos) in enumerate(grupos, 1):
            novo_base = numeracao.com_numero(base, numero, digitos)
            parte = numeracao.nome_da_parte(numero, por_pasta)
            # Já está com o número certo E na parte certa? Não toca. Parte que
            # ainda não existe conta como "precisa mover" — é o caso de todo
            # clipe hoje solto na raiz do dia.
            destino_atual = partes.get(parte)
            preciso_mover = (destino_atual is None
                             or any(arq["_pai"] != destino_atual for arq in arquivos))
            if novo_base == base and not preciso_mover:
                continue
            mudanças += 1
            print(f"  {parte}  {numeracao.formatar(numero, digitos)}  {base[:62]}")
            if not aplicar:
                continue
            destino = _id_da_parte(parte)
            for arq in arquivos:
                ext = arq["name"][len(base):]        # '.mp4', '.txt'
                corpo = {"name": novo_base + ext}
                pedido = {"fileId": arq["id"], "body": corpo}
                if arq["_pai"] != destino:
                    # Mover no Drive é trocar de pai, não copiar: o arquivo é
                    # o mesmo, o id não muda e nada é reenviado.
                    pedido["addParents"] = destino
                    pedido["removeParents"] = arq["_pai"]
                servico.files().update(**pedido).execute()
        print(f"  → {mudanças} clipe(s) "
              f"{'ajustado(s)' if aplicar else 'a ajustar'}, "
              f"{len(grupos) - mudanças} já certo(s)")

        # Partes que sobraram vazias. Acontece ao mudar quantos clipes cabem
        # por pasta: de 15 para 30, as partes 06-10 esvaziam. Vão pra LIXEIRA,
        # nunca em definitivo — a regra do projeto vale para pasta também.
        # (Lembrete: lixeira do Drive NÃO devolve cota; quem esvazia é o Bryan.)
        for nome_parte, id_parte in sorted(partes.items()):
            if servico.files().list(
                    q=f"'{id_parte}' in parents and trashed = false",
                    fields="files(id)", pageSize=1).execute().get("files"):
                continue
            print(f"  [vazia] {nome_parte} → lixeira")
            if aplicar:
                servico.files().update(fileId=id_parte,
                                       body={"trashed": True}).execute()

        total += mudanças
    return total


def main():
    p = argparse.ArgumentParser(
        description="Numera (001_, 002_...) os clipes já em A POSTAR, por nota")
    p.add_argument("--conta", default="principal",
                   help="conta do Drive (principal, reserva) — ver contas_drive.py")
    p.add_argument("--todas-contas", action="store_true",
                   help="percorre as duas contas")
    p.add_argument("--dia", help="só esta pasta (ex: 29-07); padrão: todas")
    p.add_argument("--digitos", type=int, default=numeracao.NUMERO_DIGITOS,
                   help=f"dígitos no número (padrão {numeracao.NUMERO_DIGITOS})")
    p.add_argument("--por-pasta", type=int, default=numeracao.POR_PASTA,
                   help=f"clipes por subpasta 'parte NN' "
                        f"(padrão {numeracao.POR_PASTA})")
    p.add_argument("--aplicar", action="store_true",
                   help="renomeia de verdade; sem isto, só mostra")
    a = p.parse_args()

    contas = [c["nome"] for c in contas_drive.CONTAS] if a.todas_contas else [a.conta]
    total = 0
    for nome in contas:
        try:
            total += renumerar(nome, a.dia, a.aplicar, a.digitos, a.por_pasta)
        except Exception as e:
            print(f"[{nome}] falhou: {e}", file=sys.stderr)

    if not a.aplicar and total:
        print(f"\nSIMULAÇÃO — nada foi alterado. {total} clipe(s) seriam "
              "renomeados. Rode de novo com --aplicar.")


if __name__ == "__main__":
    main()
