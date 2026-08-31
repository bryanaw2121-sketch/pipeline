"""Tradução de legenda pra pt-BR — sem dublagem, só o texto que fica queimado.

Groq devolve timestamp por palavra NO IDIOMA ORIGINAL. Traduzir palavra por
palavra quebraria a ordem (inglês e português não têm a mesma estrutura de
frase), então a abordagem é: traduzir o trecho inteiro de uma vez com o
Gemini, e redistribuir as palavras traduzidas dentro da MESMA janela de tempo
do trecho original, proporcional ao tamanho de cada palavra. Não é
sincronismo labial nem por palavra exata — é karaokê aproximado, suficiente
pra legenda (não estamos dublando áudio).
"""
import re
import time

import requests

import config
from . import keys

PROMPT = """Traduza a fala abaixo para português do Brasil, natural e coloquial
(é legenda de vídeo curto, não documento formal). Mantenha o mesmo número
aproximado de frases. Responda SOMENTE com o texto traduzido, sem aspas,
sem comentário, sem markdown.

Fala original:
{texto}"""

# Usado só quando --dublar: a fala original costuma ter mais de uma pessoa
# (entrevistador perguntando, entrevistado respondendo) e cacoetes de fala
# ("ok ok", repetição, gagueira). Traduzir isso literalmente faz a voz
# clonada (uma pessoa só) "interpretar" os dois lados do diálogo, o que
# soa estranho. Aqui a IA reescreve como um NARRADOR CONTANDO A HISTÓRIA
# do que está acontecendo com base no que os personagens disseram — não
# é dublagem das falas deles, é o narrador relatando os fatos.
PROMPT_NARRACAO = """A fala abaixo é a transcrição de um vídeo e pode ter mais de
uma pessoa falando (por exemplo: entrevistador perguntando, entrevistado
respondendo), além de cacoetes de fala como "ok ok", repetições e gagueira.

Reescreva isso em português do Brasil como se VOCÊ fosse um narrador contando
a história do que está acontecendo, com base no que os personagens disseram
— não é dublar/interpretar as falas deles, é você relatando os fatos e o que
foi dito (ex: em vez de reproduzir a pergunta e a resposta como diálogo,
narre o que aconteceu: "ela explicou que..." / "ele mostrou como..."). Um só
narrador falando o tempo todo, nunca trocando de personagem.

{dica_genero}ATENÇÃO AO GÊNERO: o inglês (e outros idiomas) muitas vezes não deixa claro
se quem está falando/sendo descrito é homem ou mulher (ex: "you", nome
próprio sem pista, frase sem pronome). NUNCA generalize pro masculino por
padrão. Preste atenção em qualquer pista de gênero no texto original (nome,
"she"/"her", "woman", forma de tratamento, etc.) pra decidir uma vez só, e
depois use "ele"/"ela" (pronome curto, não repita "a convidada"/"o
entrevistado" toda hora — isso deixa o texto mais longo que o necessário)
CONSISTENTE do início ao fim. Só use o papel da pessoa ("a convidada") na
PRIMEIRA menção pra estabelecer o gênero, se não houver nenhuma outra pista;
depois disso, pronome curto sempre.

VÁRIOS PARTICIPANTES (podcast, mesa-redonda, mais de 2 pessoas falando):
se houver MAIS DE UMA pessoa do mesmo gênero (ex: dois homens, duas
mulheres) ou mais de 2 pessoas no total, "ele"/"ela" sozinho fica ambíguo
— não dá pra saber de quem se fala. Nesses casos: se o nome da pessoa
aparece no texto original, apresente com papel + nome UMA VEZ na primeira
menção (ex: "o convidado Elon Musk") e depois use só um jeito curto de
chamar essa pessoa (ex: "Musk") nas próximas vezes — NUNCA fique repetindo
"o convidado"/"o anfitrião" toda hora, isso soa repetitivo e cansativo. Se
o nome não aparecer no original, aí sim use o papel ("o anfitrião", "o
segundo convidado") como identificador, mas ainda assim com moderação —
só quando o contexto imediato não deixar claro de quem se trata.

TAMANHO: {orcamento}o texto reescrito vai ser falado no MESMO TEMPO que a fala
original durava. Texto mais longo força a dublagem a acelerar a fala pra
caber no tempo, o que soa corrido e ruim.

⚠️ COMO ENCURTAR SEM PERDER NADA: o que sai é REDUNDÂNCIA, nunca FATO.
Corte primeiro: repetição da mesma ideia, conectivo longo, adjetivo
decorativo, e a repetição do papel da pessoa quando o pronome já basta.
NUNCA corte: número, MEDIDA, temperatura, tempo de forno, ingrediente, nome,
marca, o passo de uma receita, nem a conclusão. Se depois de tirar toda a
redundância o texto ainda passar do limite, ENTREGUE ASSIM MESMO — um texto
um pouco longo é melhor que um texto que perdeu informação.

LINGUAGEM MENOS CRUA: quando o assunto envolver violência, morte ou dano a
pessoas, narre o FATO sem a palavra mais gráfica — prefira "o fim de milhares
de pessoas" a "a morte de milhares", "eliminar" a "assassinar", "tirar vidas"
a "matar". NÃO é censura nem eufemismo que esconde o que aconteceu: o fato
tem que continuar claro e verdadeiro, com a mesma força. É escolha de
vocabulário, do jeito que um documentário de TV narra tragédia sem ser
gráfico. Se a palavra crua for indispensável pro sentido (uma citação
direta, um termo técnico), use — não distorça o fato pra evitá-la.

Mantenha o MESMO ASSUNTO e as MESMAS informações e fatos (não invente nada, não resuma
demais), só remova a troca de interlocutor e os cacoetes de fala, deixando o
texto linear e natural de se ouvir em voz alta. Responda SOMENTE com o texto
reescrito, sem aspas, sem comentário, sem markdown.

Fala original:
{texto}"""


PROMPT_LITERAL = """Traduza a fala abaixo para português do Brasil. É a fala de
uma pessoa ensinando uma receita, em vídeo curto.

REGRAS:
1. Traduza FIELMENTE o que a pessoa diz — a instrução exata importa ("bata até
   dobrar de volume" não pode virar "misture bem"). Não é narração em terceira
   pessoa: é a própria pessoa falando.
2. Escreva em FRASES COMPLETAS, com pontuação correta. O texto vai ser lido por
   uma voz sintética, e cada ponto final vira uma PAUSA. Ponto no meio de uma
   frase faz a voz parar no lugar errado.
3. Remova cacoetes, gagueira e repetição da transcrição ("agora, agora", "e aí,
   e aí"). Uma vez só.
4. NÃO CONVERTA MEDIDA NENHUMA. Os números já vêm convertidos e corretos:
   copie exatamente como estão (gramas, mililitros, °C, colheres, centímetros).
   Se aparecer uma medida que você acha estranha, MANTENHA assim mesmo.
   Converter por conta própria já produziu erro: "9x13 polegadas" virou
   "20 por 30" quando o certo é 23x33.
5. Nome de prato estrangeiro: escolha UMA grafia e repita igual até o fim
   (cobbler foi lido de três jeitos diferentes no mesmo vídeo).

Responda SOMENTE com o texto traduzido, sem aspas, sem comentário, sem markdown.

Fala original:
{texto}
TAMANHO: {orcamento}o texto vai ser falado no MESMO TEMPO que a fala original
durava. Texto mais longo força a dublagem a acelerar, o que soa corrido.

⚠️ Encurtar é tirar REDUNDÂNCIA (repetição, cacoete, conectivo longo), nunca
FATO. NUNCA corte medida, temperatura, tempo, ingrediente ou passo. Se não
couber sem perder informação, ENTREGUE ASSIM MESMO.
"""


def dica_de_genero(genero: str | None) -> str:
    """Frase que vai NO TOPO do prompt de narração, quando a seleção soube o
    gênero de quem fala.

    Existe porque o prompt sozinho manda inferir pelo TEXTO, e transcrição
    muitas vezes não tem pista nenhuma — aí o modelo chuta. A seleção, ao
    contrário, VÊ O VÍDEO. Em 25/08/2026 um clipe foi ao ar narrado como
    "A ESPECIALISTA EXPLICOU" com um homem na tela.
    """
    g = (genero or "").strip().lower()
    if g in ("masculino", "homem", "male"):
        return ("⚠️ QUEM FALA NESTE TRECHO E HOMEM (confirmado pela imagem do "
                "video). Use ele/dele e concordancia masculina do inicio ao "
                "fim. Isto vence qualquer pista do texto.\n\n")
    if g in ("feminino", "mulher", "female"):
        return ("⚠️ QUEM FALA NESTE TRECHO E MULHER (confirmado pela imagem do "
                "video). Use ela/dela e concordancia feminina do inicio ao "
                "fim. Isto vence qualquer pista do texto.\n\n")
    if g in ("varios", "vários", "multiplos", "múltiplos"):
        return ("⚠️ HA MAIS DE UMA PESSOA FALANDO neste trecho (confirmado "
                "pela imagem). Siga a regra de VARIOS PARTICIPANTES abaixo.\n\n")
    return ""


# Ritmo alvo da narracao, em palavras por minuto.
#
# MEDIDO no run #16 (31/08/2026, Make Butter do Chef Jean-Pierre):
#     56 frases, narracao 292,2s pro clipe de 188,3s  -> acelerando 1,55x
#     32 frases, narracao 164,4s pro clipe de 118,8s  -> acelerando 1,38x
#
# 1,55x e' praticamente o teto de 1,6x que o codigo chama de "robotico". O
# texto ja' chegava longo do modelo e so' restava ao `atempo` esmagar o audio.
#
# 150 ppm e' ritmo de narracao de documentario em portugues. Nao e' teto
# rigido: o prompt manda ENTREGAR ASSIM MESMO se nao couber sem perder
# informacao. Numa receita, perder uma medida estraga o video inteiro.
# ⚠️ 113, e nao 150. MEDIDO no run #17 da cozinha (31/08/2026), contando as
# palavras entregues contra a duracao REAL do audio sintetizado:
#
#     clipe A   221 palavras ->  98,2s  = 135 palavras/min
#     clipe B   384 palavras -> 224,0s  = 103 palavras/min
#     clipe C   205 palavras -> 120,2s  = 102 palavras/min
#                                 media   113 palavras/min
#
# O 150 da primeira versao veio de "ritmo de narracao de documentario" — um
# numero EDITORIAL, de referencia humana, nao do motor. O Chatterbox fala a
# 113, entao pedir 150 e' pedir 32% de texto a mais do que cabe na janela.
#
# A prova de que o orcamento em si funcionava: no clipe B o modelo entregou
# 384 palavras contra um orcamento de 379 — obedeceu — e mesmo assim o audio
# ficou 1,47x maior que a janela. A peca estava certa; o alvo e' que estava
# errado.
#
# ⚠️ NAO devolva pra 150 achando que soa mais natural. 150 e' o ritmo de um
# NARRADOR HUMANO; este numero descreve o que a SINTESE faz. Sao coisas
# diferentes, e foi confundi-las que causou o defeito.
#
# ⚠️ O ritmo VARIA por clipe (102 a 135 na mesma rodada), entao isto nunca
# sera' exato. E' o centro da faixa, nao uma garantia.
PALAVRAS_POR_MINUTO = 113


def orcamento_de_palavras(duracao_s: float | None) -> str:
    """A frase que entra no prompt dizendo quantas palavras cabem.

    Vazia quando nao ha' duracao — e ai' o prompt fica identico ao de antes.
    Falha ABERTA: clipe sem timing nao pode ficar sem narracao por isto.
    """
    if not duracao_s or duracao_s <= 0:
        return ""
    limite = int(duracao_s / 60.0 * PALAVRAS_POR_MINUTO)
    if limite < 10:
        return ""
    return (f"o texto tem que caber em cerca de {limite} PALAVRAS "
            f"(sao {duracao_s:.0f} segundos de video, e narracao boa em "
            f"portugues tem ~{PALAVRAS_POR_MINUTO} palavras por minuto). ")


def _formatar(prompt: str, texto: str, genero, duracao_s) -> str:
    campos = {"texto": texto}
    if "{dica_genero}" in prompt:
        campos["dica_genero"] = dica_de_genero(genero)
    if "{orcamento}" in prompt:
        campos["orcamento"] = orcamento_de_palavras(duracao_s)
    return prompt.format(**campos)


def _traduzir_texto(texto: str, prompt: str = PROMPT, genero: str | None = None,
                    duracao_s: float | None = None) -> str:
    # Converte medida ANTES de traduzir: o Gemini recebe a receita ja' em
    # grama e C e so' traduz o texto em volta. Deixar a conversao pra depois
    # da traducao daria ao modelo a chance de "ajudar" e desconverter — e a
    # regra de densidade por ingrediente ele nao tem. So' age em modo receita.
    if getattr(config, "MODO_RECEITA", False):
        from . import conversoes
        texto, _selos = conversoes.converter(texto)
    if not texto.strip():
        return texto

    rot = keys.gemini()
    ultimo_erro = None
    for _ in range(len(rot) * 2):
        chave = rot.proxima()
        try:
            r = requests.post(
                f"{config.GEMINI_URL}/models/{config.GEMINI_MODELO}:generateContent?key={chave}",
                json={
                    # `dica_genero` só existe no PROMPT_NARRACAO; o PROMPT
                    # comum não tem esse campo, então formatar com ele daria
                    # KeyError. Preenche só quando o prompt pede.
                    "contents": [{"parts": [{"text": (
                        # Preenche SO' os campos que o prompt pede. Sao tres
                        # prompts com campos diferentes: formatar com um campo
                        # que o texto nao tem da' KeyError, e formatar sem um
                        # que ele tem deixa o placeholder cru no pedido.
                        _formatar(prompt, texto, genero, duracao_s)
                    )}]}],
                    "generationConfig": {"temperature": 0.3},
                },
                timeout=60,
            )
            if r.status_code in (429, 403):
                rot.queimar(chave)
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.HTTPError as e:
            ultimo_erro = e
            if e.response is not None and e.response.status_code in (429, 403):
                rot.queimar(chave)
                continue
            # 503 é sobrecarga TRANSITÓRIA do servidor (mesmo padrão do
            # nemotron.py), não chave sem cota — tentar de novo resolve,
            # crashar o run inteiro por isso jogaria fora um clipe já
            # transcrito (medido: run 30860861087, clipe nota 96 perdido).
            if e.response is not None and e.response.status_code == 503:
                time.sleep(2)
                continue
            raise
        except Exception as e:
            ultimo_erro = e
            time.sleep(1)
    raise RuntimeError(f"tradução falhou em todas as chaves: {ultimo_erro}")


def checar_disponibilidade() -> None:
    """Falha cedo se nenhuma chave do Gemini tiver cota.

    A tradução roda no FIM do pipeline, depois de baixar, transcrever, narrar
    e renderizar. Quando a cota estoura, o run morre com ~1h de runner já
    gasta por vídeo — foi exatamente o que aconteceu nos runs #123-126 de
    08/08/2026 (todas as chaves em 429, morreu em traduzir_segmentos).

    O teste usa uma frase mínima pelo MESMO caminho de código que falharia
    depois (mesma rotação de chaves, mesmo tratamento de 429/403), então um
    verde aqui significa que aquele caminho funciona — não é um dublê mais
    fácil que a produção.
    """
    _traduzir_texto("ok")


def redistribuir_palavras(palavras_traduzidas: list[str], inicio: float, fim: float) -> list[dict]:
    """Espalha as palavras traduzidas dentro da janela [inicio, fim],
    proporcional ao tamanho de cada palavra (palavra maior demora mais).
    Pública porque `voz_clonada` reaproveita pra alinhar a legenda ao
    timing REAL do áudio dublado (não ao timing do vídeo original)."""
    if not palavras_traduzidas:
        return []
    pesos = [max(1, len(p)) for p in palavras_traduzidas]
    total = sum(pesos)
    dur = max(0.4, fim - inicio)

    saida, t = [], inicio
    for p, peso in zip(palavras_traduzidas, pesos):
        d = dur * (peso / total)
        saida.append({"palavra": p, "inicio": round(t, 3), "fim": round(t + d, 3)})
        t += d
    return saida


def _agrupar(palavras: list[dict], tamanho_janela_s: float) -> list[list[dict]]:
    grupos, atual = [], []
    inicio_grupo = palavras[0]["inicio"]
    for p in palavras:
        atual.append(p)
        if p["fim"] - inicio_grupo >= tamanho_janela_s:
            grupos.append(atual)
            atual = []
            inicio_grupo = p["fim"]
    if atual:
        grupos.append(atual)
    return grupos


def _distribuir_texto_em_janelas(texto: str, grupos: list[list[dict]]) -> list[dict]:
    """Divide um texto reescrito (já não bate mais 1:1 com as janelas
    originais, porque a reescrita muda o número de palavras) nas mesmas
    janelas de tempo dos grupos, proporcional à duração de cada uma —
    igual espírito do _redistribuir, mas em nível de texto corrido em vez
    de palavra por palavra."""
    texto = texto.strip()
    inicio_total = grupos[0][0]["inicio"]
    fim_total = grupos[-1][-1]["fim"]
    duracao_total = max(0.1, fim_total - inicio_total)
    n = len(texto)

    resultado, pos, acumulado = [], 0, 0.0
    for i, grupo in enumerate(grupos):
        acumulado += grupo[-1]["fim"] - grupo[0]["inicio"]
        if i == len(grupos) - 1:
            corte = n
        else:
            corte = round(n * (acumulado / duracao_total))
            while corte < n and not texto[corte].isspace():
                corte += 1
        resultado.append({
            "inicio": grupo[0]["inicio"],
            "fim": grupo[-1]["fim"],
            "texto": texto[pos:corte].strip(),
        })
        pos = corte
    return resultado


def traduzir_segmentos(palavras: list[dict], tamanho_janela_s: float = 4.0,
                        narrar: bool = False,
                        genero_falante: str | None = None,
                        literal_completo: bool = False) -> list[dict]:
    """Recebe [{palavra, inicio, fim}] no idioma original e devolve trechos
    traduzidos em texto corrido: [{inicio, fim, texto}]. Usado pra dublagem
    (TTS fala o texto inteiro do trecho, não palavra por palavra).

    narrar=True (usado com --dublar): em vez de traduzir cada janela de
    ~4s isoladamente (o que preserva vaivém de diálogo e cacoetes de fala
    da transcrição original), reescreve o trecho INTEIRO de uma vez como
    narração de um narrador só, depois distribui esse texto nas mesmas
    janelas de tempo. Ver PROMPT_NARRACAO."""
    if not palavras:
        return []

    if narrar or literal_completo:
        # Os dois traduzem o texto INTEIRO de uma vez e so' depois distribuem
        # nas janelas de tempo. A diferenca e' o prompt: narrar reescreve como
        # narrador; literal_completo mantem a fala da pessoa.
        #
        # POR QUE literal_completo existe (28/08/2026): `--fala-literal` caia no
        # caminho de baixo, que traduz cada janela de ~4s SOZINHA. Cada janela
        # ganhava ponto final proprio, e o TTS poe uma PAUSA em cada ponto — a
        # dublagem saiu "Mistura tudo ate. / Incorporar." e "Se. / Ja se
        # perguntou". Uma janela que pegou so' o "Allow" de "allow to cool"
        # virou a frase "Permitir." sozinha no fim do video.
        texto_completo = " ".join(p["palavra"] for p in palavras)
        # A janela sai das PROPRIAS palavras — nao precisa mudar quem chama.
        try:
            dur = float(palavras[-1]["fim"]) - float(palavras[0]["inicio"])
        except (KeyError, TypeError, ValueError, IndexError):
            dur = None
        texto_novo = _traduzir_texto(
            texto_completo,
            prompt=PROMPT_NARRACAO if narrar else PROMPT_LITERAL,
            genero=genero_falante if narrar else None,
            duracao_s=dur)
        if dur and dur > 0:
            n = len(texto_novo.split())
            ppm = n / (dur / 60.0)
            alvo = int(dur / 60.0 * PALAVRAS_POR_MINUTO)
            marca = "" if ppm <= 200 else "  [!] acima de 200 ppm"
            print(f"      narracao: {n} palavras em {dur:.0f}s = "
                  f"{ppm:.0f} palavras/min (alvo {alvo}){marca}")
        grupos = _agrupar(palavras, tamanho_janela_s)
        return _distribuir_texto_em_janelas(texto_novo, grupos)

    resultado = []
    for grupo in _agrupar(palavras, tamanho_janela_s):
        texto_original = " ".join(p["palavra"] for p in grupo)
        traduzido = _traduzir_texto(texto_original)
        resultado.append({
            "inicio": grupo[0]["inicio"],
            "fim": grupo[-1]["fim"],
            "texto": traduzido,
        })
    return resultado


def segmentos_para_palavras(segmentos: list[dict]) -> list[dict]:
    """Converte [{inicio, fim, texto}] em [{palavra, inicio, fim}] pra
    legenda karaokê, redistribuindo o texto de cada segmento na sua janela."""
    resultado = []
    for seg in segmentos:
        novas_palavras = re.findall(r"\S+", seg["texto"])
        resultado.extend(redistribuir_palavras(novas_palavras, seg["inicio"], seg["fim"]))
    return resultado


def traduzir_palavras(palavras: list[dict], tamanho_janela_s: float = 4.0,
                       narrar: bool = False) -> list[dict]:
    """Recebe [{palavra, inicio, fim}] no idioma original e devolve a mesma
    estrutura traduzida pra pt-BR, com timing reencaixado.

    Traduz em janelas de ~tamanho_janela_s (não a palavra isolada, nem o
    clipe inteiro de uma vez) pra manter contexto de frase sem estourar
    muito a sincronia do trecho.
    """
    if not palavras:
        return []
    segmentos = traduzir_segmentos(palavras, tamanho_janela_s, narrar=narrar)
    return segmentos_para_palavras(segmentos)
