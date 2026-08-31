# -*- coding: utf-8 -*-
"""O registro unico de TODO clipe que sai do pipeline, e do que foi postado.

Pedido do Bryan em 31/08/2026, depois do estrago na fila da cozinha: "temos
que ter um arquivo com todos os nomes dos arquivos que saem direto do
pipeline e ter o controle do que foi postado ou nao, pelo Buffer ou pela
minha mao ou por prints. Nunca repostar video ja' postado."

## A IDENTIDADE E' O HASH DO ARQUIVO, NAO O NOME

⚠️ ESTA E' A LICAO DO PROPRIO ESTRAGO, e o motivo deste modulo existir.

Em 31/08/2026 a fila do @cozinha.internacional tinha 8 posts agendados. SEIS
apontavam pro mesmo arquivo — um `short_9x16.mp4` de 111 MB — com seis
titulos diferentes e seis legendas diferentes. O publicador dava esse nome
fixo a todo clipe, e cada upload apagava o anterior na release.

Qualquer registro por NOME teria dito "seis videos distintos". Qualquer
registro por TITULO teria dito o mesmo. So' o conteudo do arquivo denuncia:
um hash, seis entradas.

Por isso a chave primaria e' o sha256 do mp4. O nome e o titulo entram como
apelidos — uteis pra ler, inuteis pra decidir.

## ALEM DO BUFFER

⚠️ O BUFFER NAO SABE DE TUDO. O Bryan postou as estreias do @atefalhar e do
@truque.importado na mao, direto no TikTok. Pro Buffer esses canais tem ZERO
publicados — e uma lista antirrepeticao que so' olha o Buffer autorizaria
justamente a repeticao que ela existe pra impedir.

Dai os tres caminhos de `origem`: "buffer", "mao" e "print".

## O QUE NAO FOI POSTADO NAO E' APAGADO SOZINHO

O Bryan disse que o que nao foi postado "certamente e' coisa ruim para ser
eliminada, mas deve ser conferido". A funcao `nao_postados` LISTA candidatos;
nada aqui apaga arquivo. Apagar sozinho um clipe que estava so' esperando a
vez seria trocar um estrago por outro.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "registro_clipes.json"
ORIGENS = ("buffer", "mao", "print")


def sha_do_arquivo(caminho: Path, blocos: int = 1 << 20) -> str:
    """sha256 do arquivo inteiro. E' a identidade do clipe."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(blocos), b""):
            h.update(pedaco)
    return h.hexdigest()


def chave_titulo(texto: str) -> str:
    """Titulo normalizado, pra casar o que o Buffer devolve com o registro.

    Tira o prefixo `NN_notaXX_` que o pipeline poe no nome da pasta: foi
    justamente ele que vazou pra dentro das legendas da cozinha.
    """
    t = re.sub(r"^\d+_nota\d+_", "", (texto or "").strip())
    t = t.split("\n")[0]
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def _ler() -> dict:
    if not ARQUIVO.exists():
        return {"_leia": "Registro de clipes. Chave = sha256 do mp4.", "clipes": {}}
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def _gravar(d: dict) -> None:
    ARQUIVO.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


def registrar(sha: str, *, arquivo: str, titulo: str, canal: str,
              url: str = "") -> dict:
    """Anota que este clipe SAIU do pipeline. Ainda nao diz nada sobre postar.

    Chamar isto na hora em que o mp4 vira asset de release e' o que garante
    que nenhum clipe exista fora do registro.
    """
    d = _ler()
    e = d["clipes"].setdefault(sha, {
        "arquivo": arquivo, "titulo": titulo, "canal": canal, "url": url,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "postagens": [],
    })
    # ⚠️ O MESMO SHA VOLTANDO COM OUTRO NOME E' O SINTOMA DO ESTRAGO. Nao
    # sobrescreve o primeiro nome: guarda o apelido e deixa o rastro visivel.
    if e["arquivo"] != arquivo:
        e.setdefault("outros_nomes", [])
        if arquivo not in e["outros_nomes"]:
            e["outros_nomes"].append(arquivo)
    _gravar(d)
    return e


def marcar_postado(sha: str, *, origem: str, quando: str = "",
                   canal: str = "", detalhe: str = "") -> None:
    """Anota uma postagem. `origem` diz por onde saiu: buffer, mao ou print."""
    if origem not in ORIGENS:
        raise ValueError(f"origem tem de ser uma de {ORIGENS}, veio {origem!r}")
    d = _ler()
    e = d["clipes"].get(sha)
    if e is None:
        raise KeyError(f"sha nao registrado: {sha[:12]}")
    quando = quando or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if any(p["quando"] == quando and p["origem"] == origem
           for p in e["postagens"]):
        return
    e["postagens"].append({"origem": origem, "quando": quando,
                           "canal": canal or e["canal"], "detalhe": detalhe})
    _gravar(d)


def ja_postado(sha: str) -> bool:
    """O unico teste que decide se pode reagendar."""
    e = _ler()["clipes"].get(sha)
    return bool(e and e["postagens"])


def sha_por_titulo(titulo: str) -> str | None:
    """Acha o clipe pelo titulo — pra casar o que o Buffer devolve.

    ⚠️ E' o caminho FRACO, de proposito: titulo pode repetir e pode ser
    reescrito. Serve pra reconciliar com o Buffer, que nao sabe do hash.
    Quando o hash estiver na mao, use o hash.
    """
    alvo = chave_titulo(titulo)
    if not alvo:
        return None
    for sha, e in _ler()["clipes"].items():
        if chave_titulo(e.get("titulo") or e.get("arquivo") or "") == alvo:
            return sha
    return None


def nao_postados(dias: int = 0) -> list[dict]:
    """Clipes que sairam do pipeline e nunca foram postados.

    ⚠️ LISTA, NAO APAGA. O Bryan quer conferir antes de eliminar.
    """
    agora = datetime.now(timezone.utc)
    fora = []
    for sha, e in _ler()["clipes"].items():
        if e["postagens"]:
            continue
        idade = (agora - datetime.fromisoformat(e["criado_em"])).days
        if idade >= dias:
            fora.append({"sha": sha, "idade_dias": idade, **e})
    return sorted(fora, key=lambda x: -x["idade_dias"])


PREFIXO_SEM_HASH = "sem-hash:"


def registrar_historico(*, titulo: str, canal: str, arquivo: str = "",
                        url: str = "", postado_em: str = "",
                        origem: str = "buffer") -> str:
    """Cataloga o que existia ANTES do registro por hash, sem baixar arquivo.

    Decisao do Bryan em 31/08/2026: "vamos do de agora pra frente, mas vamos
    escrever tudo em uma lista ainda assim. Vamos ter isso catalogado."

    ⚠️ ESTA ENTRADA NAO TEM HASH, E ISSO PRECISA FICAR VISIVEL. A chave e'
    derivada do TITULO, com o prefixo `sem-hash:`. Titulo e' chave fraca — foi
    exatamente ela que deixou seis posts da cozinha apontarem pro mesmo
    arquivo. Uma entrada historica NAO oferece a protecao que o sha oferece, e
    fingir que oferece seria pior que nao ter a entrada: daria confianca falsa
    justamente onde a protecao e' menor.

    O que ela DA': catalogo. Da' pra listar, contar, e casar por titulo com o
    que o Buffer devolve. O que ela NAO da': garantia de que dois titulos
    diferentes nao sao o mesmo video.

    Clipe novo, que passa pelo `publicar_release`, entra com sha de verdade.
    """
    chave = PREFIXO_SEM_HASH + chave_titulo(titulo)
    d = _ler()
    e = d["clipes"].setdefault(chave, {
        "arquivo": arquivo, "titulo": titulo, "canal": canal, "url": url,
        "criado_em": postado_em or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sem_hash": True,
        "postagens": [],
    })
    e["sem_hash"] = True
    if postado_em and not any(p["quando"] == postado_em for p in e["postagens"]):
        e["postagens"].append({"origem": origem, "quando": postado_em,
                               "canal": canal, "detalhe": titulo[:70]})
    _gravar(d)
    return chave


def tem_hash(chave: str) -> bool:
    """A entrada e' protegida pelo conteudo, ou e' so' catalogo?"""
    return not chave.startswith(PREFIXO_SEM_HASH)


def resumo() -> dict:
    """Quantos clipes, quantos com hash de verdade, quantos ja' postados."""
    c = _ler()["clipes"]
    return {
        "total": len(c),
        "com_hash": sum(1 for k in c if tem_hash(k)),
        "so_catalogo": sum(1 for k in c if not tem_hash(k)),
        "postados": sum(1 for v in c.values() if v["postagens"]),
        "nunca_postados": sum(1 for v in c.values() if not v["postagens"]),
    }
