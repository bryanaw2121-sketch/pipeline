"""O cérebro: Gemini escolhe os momentos e já escreve os metadados do post.

Aguenta 9,5h de áudio por prompt, então o vídeo inteiro vai de uma vez —
sem chunking, sem offset pra corrigir.
"""
import json, re, time
from pathlib import Path
import requests

import config
from . import keys

PROMPT = """Você é editor de cortes virais. Analise este {tipo} INTEIRO e escolha
os {n} melhores momentos para YouTube Shorts.

ESTRUTURA GPC (Gancho-Progresso-Clímax) — o trecho escolhido precisa ter as
três partes dentro dele, não só o gancho:
1. GANCHO (primeiros ~2s do corte): frase de impacto que já entrega tensão
   ou dúvida. Nunca comece explicando contexto ("hoje eu vou falar sobre...",
   "então like é o seguinte...") — corte DEPOIS dessa introdução, direto no
   ponto.
2. PROGRESSO: a fala cumpre o que o gancho prometeu, sem enrolação.
3. CLÍMAX: a ideia se resolve dentro do próprio corte — vira redondo sozinho,
   sem precisar do resto do vídeo pra fazer sentido. Termine logo após o pico
   (frase mais forte), de forma abrupta — NUNCA inclua despedida, agradecimento,
   "se inscreva", resumo do que foi dito ou qualquer fala de encerramento
   depois do pico: isso quebra a retenção e "trava" o Short no algoritmo.

CRITÉRIOS (nesta ordem de peso):
1. Gancho nos 2 primeiros segundos — precisa prender antes do usuário deslizar.
2. Ideia COMPLETA (GPC inteiro, ver acima).
3. Carga emocional: surpresa, contradição, revelação, opinião forte, humor.
4. Corte em pausa natural da fala — nunca no meio de uma palavra ou frase.

REGRAS DURAS:
- Duração entre {dmin} e {dmax} segundos. Nunca fora disso.
- O mínimo de {dmin}s é INEGOCIÁVEL: o TikTok só paga por vídeo acima de
  60 segundos. Um trecho ótimo de 50s não serve — ou você abre o recorte
  pra pegar o contexto em volta e passar de {dmin}s, ou descarta o trecho.
- Ponto ideal: 70-95s. Só passe de 95s (até o limite de {dmax}) quando o
  arco da história PRECISA do contexto todo pra fazer sentido — não estique
  por preguiça de cortar.
- Preencher com enrolação pra alcançar {dmin}s é PIOR que descartar:
  enrolação derruba a retenção, e retenção é o que governa a DISTRIBUIÇÃO
  do vídeo pelo algoritmo. Um clipe elegível que ninguém assiste não vale
  nada.
- Os trechos NÃO podem se sobrepor.
- Prefira começar logo antes da frase de impacto, não muito antes.

IDIOMA DO TEXTO (título, descrição, tags, porque): SEMPRE em português do
Brasil, MESMO QUE a fala original do vídeo esteja em outro idioma (ex:
inglês). Só o "gancho" pode citar a frase original quando fizer sentido.

TÍTULO: seja bem chamativo — gera curiosidade, usa números/contraste/
tensão quando possível, sem ser genérico. Pense em título que faz alguém
parar de rolar o feed. Máximo 80 caracteres, sem hashtag.

DESCRIÇÃO: coloque a palavra-chave mais importante do assunto já nos
primeiros caracteres (não enrole com frase de efeito antes dela) — é o que
o YouTube lê primeiro pra indexar o vídeo na busca.

CLASSIFICAÇÃO POR TAGS (pra permitir comparar e filtrar candidatos entre
vídeos diferentes, não só pela nota geral) — escolha 1 de cada dimensão,
a que melhor descreve o corte:

tipo_conteudo: revelacao | debate | historia-pessoal | previsao | alerta |
  explicacao | controversia | comparacao | noticia-quente | humor |
  conselho-de-vida | demonstracao-tecnica

emocao_dominante: surpresa | indignacao | medo | admiracao | humor | tensao |
  orgulho | ceticismo | esperanca | choque

dinamica: confronto | entrevista-tensa | refutacao | confissao | provocacao |
  vulnerabilidade | autoridade-desafiada | monologo-direto

marcador_viral: frase-de-efeito | virada-inesperada | numero-chocante |
  previsao-ousada | contradicao | tabu-quebrado | meme-potencial |
  estatistica-absurda | valor-pratico

arquetipo: bastidor-revelado | previsao-que-assusta | especialista-alerta |
  duelo-de-ideias | confissao-inesperada | dado-chocante | mito-derrubado |
  vitoria-contra-tudo

SUBNOTAS (0-10 cada, além da "nota" geral 0-100):
- forca_gancho: quão forte é o gancho nos 2 primeiros segundos
- compartilhabilidade: alguém mandaria isso pra um amigo?
- independencia: faz sentido sozinho, sem precisar do resto do vídeo?
- intensidade_emocional: quão forte é a carga emocional
- valor_social: o quanto compartilhar isto diz algo BOM sobre quem
  compartilha — "olha que interessante eu sou por saber disso", "isso
  representa o que eu penso". Compartilhar é ato de identidade, não só
  reação ao conteúdo: pesquisa mostra que a decisão de transmitir integra
  consequências esperadas pra própria imagem social. Nota alta = a pessoa
  ganha status/identidade ao repassar. Nota baixa = interessante de ver,
  mas ninguém se define por aquilo.

PESO ENTRE AS DIMENSÕES (evidência de pesquisa, não palpite):
- Emoção de ALTA ATIVAÇÃO (surpresa, indignação, admiração, medo) prevê
  compartilhamento melhor do que utilidade prática. Entre dois candidatos
  parecidos, prefira o de carga emocional forte ao de "dica útil".
- SURPRESA concentra atenção mais que alegria — trate `surpresa` e
  `virada-inesperada` como sinal premium.
- Tristeza / baixa ativação REDUZ compartilhamento. Desconfie de trecho
  comovente-mas-parado.
- `valor-pratico` continua válido, mas como contribuinte, não como o
  critério dominante.

LINGUAGEM MENOS CRUA no "titulo" e na "descricao": quando o assunto envolver
violencia, morte ou dano a pessoas, diga o FATO sem a palavra mais grafica —
"o fim de milhares de pessoas" em vez de "a morte de milhares", "eliminar" em
vez de "assassinar". Nao e' censura: o fato continua claro e com a mesma
forca, e' escolha de vocabulario (do jeito que documentario de TV narra
tragedia). Se a palavra crua for indispensavel pro sentido, use.

NUNCA use aspas duplas (") DENTRO de nenhum valor de texto do JSON — nem no
"gancho", nem no "titulo", nem na "descricao". Se precisar citar uma fala,
use aspas simples ('assim') ou nenhuma. Aspas duplas não escapadas quebram o
JSON no meio e a resposta inteira é perdida.

Responda SOMENTE com JSON válido, sem markdown, neste formato:
{{"clipes":[{{
  "inicio_s": <float, segundos desde o começo>,
  "fim_s": <float>,
  "nota": <0-100, potencial viral>,
  "gancho": "<a frase exata que prende, curta>",
  "porque": "<1 frase em pt-BR: por que viraliza>",
  "genero_falante": "<masculino | feminino | varios | indefinido — de quem
     aparece falando NESTE trecho. Voce esta' vendo o video, entao decida pela
     IMAGEM e pela voz, nao pelo texto. Isso alimenta a narracao: em 25/08/2026
     um clipe saiu dizendo 'A ESPECIALISTA EXPLICOU' com um homem na tela.
     'varios' se houver mais de uma pessoa falando; 'indefinido' so' se
     realmente nao der pra saber>",
  "titulo": "<título chamativo em pt-BR, max 80 chars, sem hashtag>",
  "descricao": "<2-3 frases em pt-BR para a descrição do YouTube>",
  "tags": ["<5 a 8 tags em pt-BR, sem #>"],
  "tipo_conteudo": "<uma das opções acima>",
  "emocao_dominante": "<uma das opções acima>",
  "dinamica": "<uma das opções acima>",
  "marcador_viral": "<uma das opções acima>",
  "arquetipo": "<uma das opções acima>",
  "forca_gancho": <0-10>,
  "compartilhabilidade": <0-10>,
  "independencia": <0-10>,
  "intensidade_emocional": <0-10>,
  "valor_social": <0-10>
}}]}}

Ordene do maior para o menor "nota". Use segundos absolutos com 1 decimal."""


def _subir_arquivo(caminho: Path, mime: str, chave: str) -> str:
    """Upload resumable para a File API do Gemini."""
    tam = caminho.stat().st_size
    r = requests.post(
        f"{config.GEMINI_UPLOAD_URL}?key={chave}",
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(tam),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": caminho.name}},
        timeout=60,
    )
    r.raise_for_status()
    url = r.headers.get("X-Goog-Upload-URL")
    if not url:
        raise RuntimeError("Gemini não devolveu URL de upload")

    with open(caminho, "rb") as fh:
        r2 = requests.post(
            url,
            headers={
                "Content-Length": str(tam),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=fh,
            timeout=1800,
        )
    r2.raise_for_status()
    info = r2.json()["file"]

    # o arquivo fica PROCESSING até o Gemini indexar; áudio longo demora
    nome, uri = info["name"], info["uri"]
    for _ in range(180):
        s = requests.get(f"{config.GEMINI_URL}/{nome}?key={chave}", timeout=30).json()
        estado = s.get("state")
        if estado == "ACTIVE":
            return uri
        if estado == "FAILED":
            raise RuntimeError("Gemini falhou ao processar o arquivo")
        time.sleep(3)
    raise RuntimeError("timeout esperando o Gemini processar")


def _extrair_json(txt: str) -> dict:
    """Lê o JSON da resposta, tolerando cerca de markdown.

    Quando falha, imprime o trecho EM VOLTA do erro — não o começo do texto.
    Em 29/07/2026 três runs (#30, #36, #51) morreram aqui com
    `Expecting ',' delimiter` em posições bem diferentes (char 963, 1114,
    6693), e o log só mostrava a mensagem seca: não dava pra saber o que o
    modelo tinha escrito de errado.

    Suspeita principal: o prompt pede `"gancho": "<a frase exata que
    prende>"` — citação literal da fala. Aspas dentro dessa frase, sem
    escape, quebram o JSON no meio de um campo de texto, que é exatamente o
    sintoma. Imprimir o entorno confirma ou derruba isso na próxima vez.
    """
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError as e2:
                e = e2
        ini = max(0, e.pos - 220)
        print(f"   [!] JSON inválido na posição {e.pos}: {e.msg}")
        print(f"   [!] trecho: ...{txt[ini:e.pos + 220]}...")
        raise


def _pedir(caminho: Path, mime: str, monta_corpo, oquefaz: str, valida=None) -> str:
    """Faz a chamada ao Gemini com DUAS camadas de tolerância a falha.

    1. Rodízio de chaves dentro do mesmo modelo.
    2. **Cascata de modelos**: o tier gratuito é de 20 requisições por dia
       POR MODELO, então quando todas as chaves esgotam no modelo principal
       ainda há cota cheia no próximo da lista. Sem isso, um dia de trabalho
       de lote deixava o motor parado até a virada (aconteceu em 27/07/2026).

    O upload do arquivo é refeito a cada chave porque a Files API é por
    projeto — o `file_uri` só vale para a chave que subiu.
    """
    rot = keys.gemini()
    modelos = [config.GEMINI_MODELO] + list(
        getattr(config, "GEMINI_MODELOS_RESERVA", []))
    ultimo_erro = None

    for i_mod, modelo in enumerate(modelos):
        if i_mod:
            print(f"   [!] caindo para o modelo reserva: {modelo}")
        sem_cota: set[str] = set()

        for tentativa in range(len(rot) * 2):
            if len(sem_cota) >= len(rot):
                break                      # esgotou este modelo, vai pro próximo
            chave = rot.proxima()
            if chave in sem_cota:
                continue
            try:
                uri = _subir_arquivo(caminho, mime, chave)
                r = requests.post(
                    f"{config.GEMINI_URL}/models/{modelo}:generateContent?key={chave}",
                    json=monta_corpo(uri), timeout=900,
                )
                if r.status_code in (401, 429, 403):
                    # 401 não é cota, é chave inválida ou revogada — mas o
                    # tratamento é o mesmo: descarta e segue pra próxima.
                    # Antes o 401 caía no raise e derrubava o corte inteiro
                    # por causa de UMA chave ruim entre catorze (runs #46 e
                    # #48, 29/07/2026). As 8 chaves do .env local estão boas,
                    # então a defeituosa é uma que só existe como secret do
                    # GitHub, e secret não dá pra ler pra descobrir qual.
                    if r.status_code == 401:
                        print(f"   [!] chave Gemini rejeitada (401), pulando")
                    sem_cota.add(chave)
                    continue
                if r.status_code in (500, 502, 503, 504):
                    # sobrecarga do modelo, não é problema da chave
                    print(f"   [!] {modelo} {r.status_code} (sobrecarga), repetindo...")
                    time.sleep(5)
                    continue
                if r.status_code == 400:
                    # diagnóstico: 400 apareceu em vídeos grandes (28/07/2026,
                    # 274MB+) sem saber a causa exata — imprime o corpo real
                    # em vez de só deixar o raise_for_status() genérico.
                    print(f"   [!] {modelo} 400: {r.text[:1000]}")
                r.raise_for_status()
                saida = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                if valida is not None:
                    # JSON malformado é RETENTÁVEL: com temperature 0.7 o
                    # modelo às vezes escorrega no formato, e antes isso
                    # matava o corte inteiro mesmo havendo 14 chaves livres
                    # (runs #30, #36, #51 em 29/07/2026). Outra tentativa
                    # costuma sair bem — é falha de amostragem, não de chave.
                    try:
                        valida(saida)
                    except Exception as err:
                        print(f"   [!] resposta inválida ({type(err).__name__}), "
                              f"tentando de novo...")
                        ultimo_erro = err
                        continue
                return saida
            except requests.HTTPError as e:
                ultimo_erro = e
                cod = e.response.status_code if e.response is not None else None
                if cod in (401, 429, 403):
                    # Mesmo motivo do bloco acima. O 401 costuma vir do
                    # _subir_arquivo(), que roda ANTES do generateContent —
                    # por isso precisa ser tratado aqui também.
                    if cod == 401:
                        print(f"   [!] chave Gemini rejeitada (401) no upload, pulando")
                    sem_cota.add(chave)
                    continue
                if cod in (500, 502, 503, 504):
                    time.sleep(5)
                    continue
                raise
            except Exception as e:                       # noqa: BLE001
                ultimo_erro = e
                print(f"   [!] tentativa {tentativa+1} ({oquefaz}) falhou: {e}")
                time.sleep(2)

    raise RuntimeError(
        f"Gemini falhou em {oquefaz}: todas as chaves esgotadas em "
        f"{modelos}. Último erro: {ultimo_erro}")


def escolher(caminho: Path, dur_total: float, usar_video: bool,
             qtd: int = config.QTD_CLIPES) -> list[dict]:
    """Devolve os melhores momentos, já com título/descrição/tags.

    usar_video=True manda o vídeo (o Gemini VÊ a cena — pega reação, expressão,
    corte visual). Custa mais tokens, escolhe melhor.
    usar_video=False manda só o áudio: bem mais barato.
    """
    mime = "video/mp4" if usar_video else "audio/flac"
    tipo = "vídeo" if usar_video else "áudio"
    prompt = PROMPT.format(tipo=tipo, n=qtd,
                           dmin=config.DUR_MIN, dmax=config.DUR_MAX)

    def corpo(uri):
        return {"contents": [{"parts": [
            {"file_data": {"mime_type": mime, "file_uri": uri}},
            {"text": prompt},
        ]}], "generationConfig": {"temperature": 0.7,
                                  "response_mime_type": "application/json"}}

    txt = _pedir(caminho, mime, corpo, "escolha de clipes", valida=_extrair_json)
    dados = _extrair_json(txt)
    clipes = dados if isinstance(dados, list) else dados.get("clipes", [])
    return _validar(clipes, dur_total)


PROMPT_METADADOS = """Este é um corte de vídeo JÁ PRONTO para YouTube Shorts/TikTok.
Não escolha momentos, não sugira recortes — só escreva os metadados do post.

IDIOMA: tudo em português do Brasil, MESMO QUE a fala esteja em outro idioma.

TÍTULO: bem chamativo — gera curiosidade, usa números/contraste/tensão,
nunca genérico. Máximo 80 caracteres, sem hashtag.

DESCRIÇÃO: a palavra-chave mais importante do assunto nos primeiros
caracteres (sem frase de efeito antes dela) — é o que a plataforma indexa
primeiro. 2-3 frases.

Classifique também (mesma taxonomia usada na seleção normal — escolha 1 de
cada, a que melhor descreve o corte):
tipo_conteudo: revelacao | debate | historia-pessoal | previsao | alerta |
  explicacao | controversia | comparacao | noticia-quente | humor |
  conselho-de-vida | demonstracao-tecnica
emocao_dominante: surpresa | indignacao | medo | admiracao | humor | tensao |
  orgulho | ceticismo | esperanca | choque
dinamica: confronto | entrevista-tensa | refutacao | confissao | provocacao |
  vulnerabilidade | autoridade-desafiada | monologo-direto
marcador_viral: frase-de-efeito | virada-inesperada | numero-chocante |
  previsao-ousada | contradicao | tabu-quebrado | meme-potencial |
  estatistica-absurda | valor-pratico
arquetipo: bastidor-revelado | previsao-que-assusta | especialista-alerta |
  duelo-de-ideias | confissao-inesperada | dado-chocante | mito-derrubado |
  vitoria-contra-tudo

Responda SOMENTE com JSON válido, sem markdown:
{"titulo": "<max 80 chars, pt-BR, sem hashtag>",
 "descricao": "<2-3 frases em pt-BR>",
 "tags": ["<5 a 8 tags em pt-BR, sem #>"],
 "gancho": "<a frase mais forte do corte, curta>",
 "porque": "<1 frase em pt-BR: por que esse corte funciona>",
 "nota": <0-100, potencial viral>,
 "tipo_conteudo": "<uma das opções acima>",
 "emocao_dominante": "<uma das opções acima>",
 "dinamica": "<uma das opções acima>",
 "marcador_viral": "<uma das opções acima>",
 "arquetipo": "<uma das opções acima>",
 "forca_gancho": <0-10>,
 "compartilhabilidade": <0-10>,
 "independencia": <0-10>,
 "intensidade_emocional": <0-10>,
 "valor_social": <0-10>}"""


def metadados(caminho: Path, usar_video: bool = True) -> dict:
    """Gera título/descrição/tags para um corte JÁ definido (modo --recorte),
    em que o usuário escolheu o trecho na mão e não há seleção a fazer."""
    mime = "video/mp4" if usar_video else "audio/flac"

    def corpo(uri):
        return {"contents": [{"parts": [
            {"file_data": {"mime_type": mime, "file_uri": uri}},
            {"text": PROMPT_METADADOS},
        ]}], "generationConfig": {"temperature": 0.7,
                                  "response_mime_type": "application/json"}}

    return _extrair_json(_pedir(caminho, mime, corpo, "metadados",
                                valida=_extrair_json))


def _num(c: dict, campo: str, padrao: float = 0.0) -> float:
    try:
        return float(c.get(campo, padrao))
    except (TypeError, ValueError):
        return padrao


def _validar(clipes: list[dict], dur_total: float) -> list[dict]:
    """O modelo às vezes devolve tempo fora do vídeo ou duração absurda.
    Corrige o que dá, descarta o resto — melhor perder um clipe que
    renderizar lixo.

    Também aplica o piso de gancho (config.GANCHO_MIN). O modelo já devolve
    `forca_gancho` 0-10 por clipe, e até 29/07/2026 esse número era gravado
    no post.json e **nunca usado** — nem pra ordenar, nem pra filtrar.
    Descartar gancho fraco importa porque o ECR (assistir além de ~5s) é o
    que prevê sustentação de atenção, e watch time é o sinal dominante da
    promoção (PLAYBOOK §22, N=50 papers).
    """
    bons, ocupados = [], []
    fracos = []
    for c in sorted(clipes, key=lambda x: -_num(x, "nota")):
        gancho = _num(c, "forca_gancho", 10.0)   # ausente = não penaliza
        if gancho < config.GANCHO_MIN:
            fracos.append((c.get("titulo") or c.get("gancho") or "?", gancho))
            continue
        try:
            ini = max(0.0, float(c["inicio_s"]) - config.MARGEM)
            fim = min(dur_total, float(c["fim_s"]) + config.MARGEM)
        except (KeyError, TypeError, ValueError):
            continue
        if fim - ini < config.DUR_MIN:
            continue
        if fim - ini > config.DUR_MAX:
            fim = ini + config.DUR_MAX
        if any(ini < f and fim > i for i, f in ocupados):   # sobreposição
            continue
        ocupados.append((ini, fim))
        c["inicio_s"], c["fim_s"] = round(ini, 2), round(fim, 2)
        c["duracao_s"] = round(fim - ini, 2)
        bons.append(c)

    for titulo, g in fracos:
        print(f"      [!] descartado gancho {g:.0f}/10 "
              f"(piso {config.GANCHO_MIN}): \"{str(titulo)[:44]}\"")
    # Só entra na média quem TEM o campo: contar clipe sem nota de gancho
    # como zero puxaria a média pra baixo e daria um número falso no log.
    com_nota = [_num(c, "forca_gancho") for c in bons if "forca_gancho" in c]
    if com_nota:
        print(f"      gancho médio dos aprovados: "
              f"{sum(com_nota)/len(com_nota):.1f}/10 "
              f"({len(com_nota)} de {len(bons)} com nota)")
    return bons
