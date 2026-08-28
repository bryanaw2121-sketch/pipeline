"""A numeração sequencial no começo do nome dos clipes em 'A POSTAR/<dd-mm>'.

Pedido pelo Bryan em 30/07/2026: numa pasta com mais de cem clipes, dizer "o
terceiro da lista" era impossível — o nome começava pela nota, e nota repete
(treze clipes com nota95 em 29-07). O número na frente dá a cada clipe um
apelido curto e único dentro do dia.

O nome antigo é preservado inteiro depois do número: `nota95_01_nota95_Titulo`
vira `03_nota95_01_nota95_Titulo`. Nada do que já funcionava mudou de forma.

Duas decisões dele, registradas para quem vier depois:

**01 é a melhor nota.** A ordem da numeração é nota decrescente, então
ordenar a pasta por nome mostra a melhor colheita primeiro — que é o que o
`subir_drive.py` sempre disse querer, e não era o que acontecia (ordenado por
nome, `nota80` vinha antes de `nota98`).

**Três dígitos** (`001`). Dois não serviriam: a pasta 29-07 tem 138 clipes, e
em ordem alfabética `100` cairia entre `10` e `11`. Com três, a ordem se
mantém até 999. É parâmetro (`--digitos` no renumerar, `NUMERO_DIGITOS` aqui)
para não precisar mexer em código se um dia passar disso.

O número **não é** ordem de postagem nem promessa de qualidade absoluta: o
lote que chega depois no mesmo dia continua a contagem (139, 140...), mesmo
que traga nota alta. Renumerar a pasta inteira a cada lote foi descartado —
o número de um clipe mudaria depois de ele já ter visto a lista.
"""
import re

# Quantos dígitos no número. Ver a discussão acima antes de baixar isto.
NUMERO_DIGITOS = 3

# Quantos clipes por subpasta. Pedido do Bryan em 30/07/2026: a pasta do dia
# com 138 clipes obrigava rolagem longa no celular pra achar qualquer coisa.
# Agora o dia vira `30-07/parte 01`, `30-07/parte 02`, ... Começou em 15 e ele
# subiu para 30 no mesmo dia, depois de ver o resultado.
#
# A numeração NÃO reinicia a cada parte: ela é do DIA. `parte 01` tem 001-015,
# `parte 02` tem 016-030. Assim o número continua sendo apelido único dentro
# do dia — dizer "o 037" identifica um clipe só, e já diz em que parte ele
# está. Reiniciar por parte criaria treze clipes chamados 001.
POR_PASTA = 30

# Marca da versão do MOTOR no nome da pasta do dia: `31-07 v2`.
#
# Pedida pelo Bryan em 31/07/2026 para separar, de olho, o que saiu do motor
# novo do que saiu do antigo — os dois vão conviver no Drive enquanto os
# clipes velhos não forem refeitos.
#
# É código de versão, e não "NOVO", porque "novo" envelhece: daqui a duas
# mudanças ninguém sabe mais qual novo era qual. O que cada versão significa
# fica registrado aqui:
#
#   (sem marca) até 30/07 — sem título na tela, corte podendo cair no meio
#                da frase, fonte da legenda resolvida por sorte no runner
#   v2          31/07 — título em texto nos 3,5s iniciais, início ancorado no
#                começo da frase, Inter Black vindo do repositório
#
# Vazio desliga a marca e a pasta volta a ser só `31-07`.
MARCA_MOTOR = "v2"


def nome_do_dia(dia: str) -> str:
    """'31-07' -> '31-07 v2'. É o nome da pasta do dia dentro de A POSTAR."""
    return f"{dia} {MARCA_MOTOR}".strip() if MARCA_MOTOR else dia

# 'parte' com dois dígitos pelo mesmo motivo do número: com 138 clipes são 10
# partes, e em ordem alfabética 'parte 10' cairia entre 'parte 1' e 'parte 2'.
_PARTE = re.compile(r"^parte (\d+)$")

# O prefixo que este módulo escreve: dígitos + '_'. Aceita de 2 dígitos pra
# cima para reconhecer o que foi numerado com outro ajuste — assim renumerar
# duas vezes não empilha prefixo.
_PREFIXO = re.compile(r"^(\d{2,})_")

# A nota, como o subir_drive.py a escreve no nome (nota91_...).
_NOTA = re.compile(r"^nota(\d+)_")


def formatar(numero: int, digitos: int = NUMERO_DIGITOS) -> str:
    """3 → '003'. Número maior do que os dígitos cabem cresce em vez de
    truncar: com 3 dígitos, 1000 vira '1000', não '000'."""
    return str(numero).zfill(digitos)


def sem_prefixo(nome: str) -> str:
    """Nome sem a numeração, se houver. É o que torna a operação idempotente:
    renumerar de novo recalcula em cima do nome original."""
    return _PREFIXO.sub("", nome, count=1)


def numero_do_nome(nome: str) -> int | None:
    m = _PREFIXO.match(nome)
    return int(m.group(1)) if m else None


def nota_do_nome(nome: str) -> float:
    """A nota lida do nome, já ignorando a numeração. Devolve 0 se o nome não
    seguir o padrão — assim um arquivo estranho vai pro fim da fila em vez de
    derrubar a ordenação inteira."""
    m = _NOTA.match(sem_prefixo(nome))
    return float(m.group(1)) if m else 0.0


def com_numero(nome: str, numero: int, digitos: int = NUMERO_DIGITOS) -> str:
    """O nome final. Troca a numeração se já existir, em vez de somar outra."""
    return f"{formatar(numero, digitos)}_{sem_prefixo(nome)}"


def chave_de_ordem(nome: str) -> tuple:
    """Nota decrescente; empate desfeito pelo nome, para a ordem ser estável
    entre execuções (dois runs sobre a mesma pasta dão o mesmo resultado)."""
    limpo = sem_prefixo(nome)
    return (-nota_do_nome(limpo), limpo.casefold())


def parte_do_numero(numero: int, por_pasta: int = POR_PASTA) -> int:
    """Em que parte cai o clipe de número N. 1..15 → 1; 16..30 → 2."""
    return (numero - 1) // por_pasta + 1


def nome_da_parte(numero: int, por_pasta: int = POR_PASTA) -> str:
    """'parte 03', a subpasta onde o clipe de número N deve morar."""
    return f"parte {parte_do_numero(numero, por_pasta):02d}"


def e_parte(nome: str) -> bool:
    return bool(_PARTE.match(nome))


def _filhos(servico, pasta_id: str, campos: str) -> list[dict]:
    """Filhos diretos da pasta, paginado."""
    achados, token = [], None
    while True:
        r = servico.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            fields=f"nextPageToken, files({campos})",
            pageSize=1000, pageToken=token).execute()
        achados.extend(r.get("files", []))
        token = r.get("nextPageToken")
        if not token:
            return achados


def maior_numero_na_pasta(servico, pasta_id: str) -> int:
    """O maior número já usado no DIA, ou 0 se não há nenhum. É daqui que o
    lote seguinte continua a contagem.

    Desce nas subpastas `parte NN`: desde 30/07/2026 os clipes não ficam
    soltos na pasta do dia, e olhar só o primeiro nível devolveria 0 num dia
    que já tem 138 clipes — o lote novo recomeçaria em 001 e criaria número
    repetido.

    Olha TODOS os arquivos, não só os .mp4: se um upload morreu no meio e só o
    .txt subiu, o número dele ainda está gasto e não pode ser reutilizado.
    """
    maior = 0
    for f in _filhos(servico, pasta_id, "id, name, mimeType"):
        if "folder" in f["mimeType"]:
            if e_parte(f["name"]):
                maior = max(maior, maior_numero_na_pasta(servico, f["id"]))
            continue
        n = numero_do_nome(f["name"])
        if n and n > maior:
            maior = n
    return maior
