"""Marca a palavra de maior impacto em cada grupo de legenda, via Gemini.

Padrão visto numa referência (Erica Bruno, TikTok, 02/08/2026): a legenda
fica branca por padrão e só UMA palavra por grupo ganha cor sólida — não é
a palavra sendo falada acendendo tipo karaokê, é uma escolha editorial de
qual palavra "pesa mais" na frase (verbo de ação, pronome direto, urgência).
Pedimos pro Gemini marcar essa palavra, numa chamada só por clipe (não uma
por grupo — o clipe inteiro tem ~20-30 grupos, uma chamada só é suficiente
e mais barato).
"""
import json
import re
import time

import requests

import config
from . import keys

PROMPT = """Você edita legendas de vídeos virais de TikTok em português do Brasil.

Primeiro, a fala COMPLETA do clipe, pra você entender o contexto e o que
realmente importa em cada parte (o que é revelação, o que é só conectivo):
"{contexto}"

Agora, a mesma fala quebrada em trechos curtos de legenda (cada um até 3
palavras), numerados na ordem em que aparecem no vídeo. Para CADA trecho,
escolha a palavra de MAIOR IMPACTO editorial pra destacar com cor — o tipo
de palavra que uma editora profissional destacaria pra prender atenção
(verbo de ação forte, pronome direto tipo "você", superlativo, palavra de
urgência ou revelação), julgando pelo peso da palavra DENTRO DA FRASE
COMPLETA acima, não isolada. Nem todo trecho precisa ter destaque: se
nenhuma palavra se destacar claramente, responda -1 pra esse trecho.

Escolha TAMBÉM a cor do destaque, pelo SENTIDO da palavra na frase:

- "vermelho" — palavra forte, pesada, definitiva: risco, perda, ameaça,
  número que impressiona, termo técnico que é a revelação do trecho.
- "azul" — alerta e tensão no MEIO da explicação: o que preocupa, o que
  ainda não se resolveu, a ressalva, o "mas".
- "verde" — afirmação, conclusão, o que tranquiliza ou fecha o raciocínio:
  a solução, o resultado, o que deu certo, informação neutra e factual.

Na dúvida entre duas, escolha "verde" — é a cor neutra.

Responda SOMENTE um array JSON, um item por trecho, na mesma ordem. Cada item
é [indice, "cor"] com o ÍNDICE (começando em 0) da palavra dentro do trecho,
ou -1 se nenhuma palavra merecer destaque. Exemplo: [[1,"vermelho"], -1, [0,"verde"]]
Sem markdown, sem comentário, sem texto antes ou depois do array.

Trechos:
{trechos}"""


def _extrair_json(saida: str) -> str:
    saida = saida.strip()
    saida = re.sub(r"^```(json)?", "", saida).strip()
    saida = re.sub(r"```$", "", saida).strip()
    return saida


# Palavras que nunca são o destaque: artigo, preposição, conectivo, auxiliar.
# Sem esta lista o escolhedor local marcaria "de" e "que", que é pior que não
# marcar nada.
_FRACAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "pra", "para", "com", "sem",
    "e", "ou", "mas", "que", "se", "ao", "aos", "à", "às", "é", "foi", "era",
    "ser", "ter", "tem", "tinha", "vai", "vou", "já", "mais", "muito", "isso",
    "isto", "esse", "essa", "este", "esta", "ele", "ela", "eles", "elas",
    "seu", "sua", "meu", "minha", "the", "of", "to", "and", "in", "on",
}


def escolher_local(grupo: list[dict]) -> int | None:
    """Escolhe uma palavra pra destacar SEM chamar o Gemini.

    Rede de segurança: antes disto, qualquer falha da API deixava o clipe
    inteiro em branco — e o Bryan reportou exatamente isso em 26/08/2026
    ("frases que ficam com a legenda em branco").

    Critério simples e previsível: a palavra mais longa que não seja conectivo.
    Não é escolha editorial como a do Gemini, mas é MUITO melhor que nenhuma —
    a legenda karaokê sem cor perde a camada que sustenta o ritmo.
    """
    melhor, melhor_tam = None, 0
    for i, p in enumerate(grupo):
        w = re.sub(r"[^\wÀ-ÿ]", "", (p.get("palavra") or "")).lower()
        if len(w) < 4 or w in _FRACAS:
            continue
        if len(w) > melhor_tam:
            melhor, melhor_tam = i, len(w)
    return melhor


CORES_VALIDAS = ("vermelho", "azul", "verde")
COR_PADRAO = "verde"      # neutra: é o que a escolha local usa


def _ler_item(bruto) -> tuple[int | None, str | None]:
    """Lê um item da resposta do modelo.

    Aceita `[indice, "cor"]` (formato atual), `indice` puro (formato antigo,
    caso o modelo esqueça a cor) e `-1`. Ser tolerante aqui é de propósito: a
    alternativa é jogar fora o destaque do trecho por causa de formatação.
    """
    if isinstance(bruto, (list, tuple)) and bruto:
        idx, cor = bruto[0], (bruto[1] if len(bruto) > 1 else COR_PADRAO)
        cor = str(cor).strip().lower()
        if cor not in CORES_VALIDAS:
            cor = COR_PADRAO
    else:
        idx, cor = bruto, COR_PADRAO
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return None, None
    return (idx, cor) if idx >= 0 else (None, None)


def marcar(grupos: list[list[dict]]) -> list[tuple[int | None, str | None]]:
    """Devolve, por grupo, (índice da palavra destacada, cor) ou (None, None).

    A cor vem do SENTIDO da palavra (pedido do Bryan em 26/08/2026): vermelho
    pra palavra forte/definitiva, azul pra alerta no meio da explicação, verde
    pra afirmação e conclusão. Antes disso a paleta só rotacionava, sem
    critério nenhum."""
    if not grupos:
        return []

    trechos = "\n".join(
        f"{i}: " + " ".join(p["palavra"] for p in g)
        for i, g in enumerate(grupos)
    )
    contexto = " ".join(p["palavra"] for g in grupos for p in g)

    rot = keys.gemini()
    for _ in range(len(rot) * 2):
        chave = rot.proxima()
        try:
            r = requests.post(
                f"{config.GEMINI_URL}/models/{config.GEMINI_MODELO}:generateContent?key={chave}",
                json={
                    "contents": [{"parts": [{"text": PROMPT.format(contexto=contexto, trechos=trechos)}]}],
                    "generationConfig": {"temperature": 0.4},
                },
                timeout=60,
            )
            if r.status_code in (429, 403):
                rot.queimar(chave)
                continue
            r.raise_for_status()
            saida = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            arr = json.loads(_extrair_json(saida))
            if not isinstance(arr, list):
                raise ValueError(f"esperava lista, veio {arr!r}")
            # Tamanho diferente NÃO é mais erro fatal. Um clipe de 60s tem 40 a
            # 60 trechos, e pedir um array com contagem exata disso é frágil —
            # um item a mais ou a menos jogava fora o destaque do clipe INTEIRO
            # e a legenda saía toda branca. Agora aproveita o que veio na ordem
            # e completa o resto com a escolha local.
            if len(arr) != len(grupos):
                print(f"   [!] destaque veio com {len(arr)} de {len(grupos)} "
                      "trechos; completando o resto localmente")
            saida_final = []
            for i, g in enumerate(grupos):
                bruto = arr[i] if i < len(arr) else None
                idx, cor = _ler_item(bruto)
                if idx is not None and 0 <= idx < len(g):
                    saida_final.append((idx, cor))
                elif i < len(arr):
                    saida_final.append((None, None))   # o modelo disse -1 de propósito
                else:
                    saida_final.append((escolher_local(g), COR_PADRAO))
            return saida_final
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (429, 403):
                rot.queimar(chave)
                continue
            print(f"   [!] destaque: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"   [!] destaque: {e}")
            time.sleep(1)

    print("   [!] destaque falhou em todas as chaves — usando escolha local "
          "(legenda continua colorida, só sem curadoria do modelo)")
    return [(escolher_local(g), COR_PADRAO) for g in grupos]


PROMPT_TITULO = """Você edita títulos de abertura de vídeos virais de TikTok, no
estilo de uma caixa de texto que aparece nos primeiros segundos — ex:
"VIRALIZOU / Faça isso / IMEDIATAMENTE", onde 1-2 trechos curtos (uma ou
poucas palavras) ficam em CAIXA ALTA pra dar impacto, e o resto do título
mantém a formatação normal. É esse ritmo alternado que dá o efeito.

Reescreva o título abaixo mudando SÓ A CAIXA (maiúscula/minúscula) de
palavras pra criar esse efeito. NÃO mude nenhuma palavra, não adicione nem
remova nada, não mude pontuação nem acento. Normalmente 1-2 trechos curtos
ficam em caixa alta — não exagere, a maior parte do título deve continuar
como está.

Responda SOMENTE o título reescrito, sem aspas, sem comentário, sem markdown.

Título original:
{texto}"""


def _mesmas_palavras(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"\s+", " ", s.strip().lower())
    return norm(a) == norm(b)


def marcar_titulo(texto: str) -> str:
    """Devolve o título com trechos em CAIXA ALTA pra dar ritmo editorial.

    Se o Gemini falhar ou mudar alguma palavra (alucinação), devolve o
    título original sem tocar — melhor sem o efeito do que com o título
    errado."""
    texto = (texto or "").strip()
    if not texto:
        return texto

    rot = keys.gemini()
    for _ in range(len(rot) * 2):
        chave = rot.proxima()
        try:
            r = requests.post(
                f"{config.GEMINI_URL}/models/{config.GEMINI_MODELO}:generateContent?key={chave}",
                json={
                    "contents": [{"parts": [{"text": PROMPT_TITULO.format(texto=texto)}]}],
                    "generationConfig": {"temperature": 0.4},
                },
                timeout=60,
            )
            if r.status_code in (429, 403):
                rot.queimar(chave)
                continue
            r.raise_for_status()
            saida = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if _mesmas_palavras(saida, texto):
                return saida
            print("   [!] destaque de título: Gemini mudou palavra, ignorando")
            return texto
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (429, 403):
                rot.queimar(chave)
                continue
            print(f"   [!] destaque de título: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"   [!] destaque de título: {e}")
            time.sleep(1)

    print("   [!] destaque de título falhou em todas as chaves — título sem caixa alta")
    return texto
