"""Corte e render final. Aqui a GTX 1650 trabalha (NVENC)."""
from functools import lru_cache
from pathlib import Path

import config
from . import midia, enquadrar, pos_producao

_NVENC = None


def _encoder() -> list[str]:
    """Detecta NVENC uma vez. No Nitro 5 usa a 1650; sem NVIDIA usa a CPU."""
    global _NVENC
    if _NVENC is None:
        _NVENC = midia.tem_nvenc()
        print(f"   encoder: {'NVENC (GPU)' if _NVENC else 'libx264 (CPU)'}")
    if _NVENC:
        return ["-c:v", config.NVENC, "-preset", "p5", "-rc", "vbr",
                "-cq", "23", "-b:v", "0"]
    return ["-c:v", config.CPU_ENC, "-preset", "medium", "-crf", "20"]


def _escapar(p: Path) -> str:
    """ffmpeg trata ':' e '\\' como sintaxe dentro de filtro. No Windows o
    caminho C:\\... quebra o filtro subtitles= se não for escapado.

    A APÓSTROFO também: o valor vai entre aspas simples no filtro, então um
    caminho com `'` fecha a string no meio e o ffmpeg devolve "Error
    initializing a simple filtergraph" — sem dizer qual filtro nem por quê.
    Derrubou o run #63 em 31/07: a pasta do clipe herda o nome do vídeo, e o
    vídeo era "Figure's First Full HQ Tour". Os outros dois runs do mesmo
    lote passaram porque o nome deles era só o ID do YouTube.
    """
    # APÓSTROFO não tem escape que funcione aqui. Tentei as duas formas
    # conhecidas em 31/07: \' o ffmpeg ignora e o filtro quebra ("No such
    # filter"); o truque de shell 'a'\''b' faz o parser aceitar mas entregar
    # um caminho corrompido ("Cannot read file"). A saída é não deixar
    # apóstrofo chegar aqui — ver filtro_titulo e vertical(), que gravam em
    # config.TRABALHO em vez da pasta do clipe (que herda o nome do vídeo).
    return str(p).replace("\\", "/").replace(":", r"\:")


def cortar(fonte: Path, inicio: float, fim: float, destino: Path) -> Path:
    """Corta sem reencodar o trecho (rápido). -ss antes do -i = seek veloz;
    o -ss depois garante precisão no frame."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    midia.roda([
        "ffmpeg", "-y",
        "-ss", f"{max(0, inicio - 5):.3f}", "-i", str(fonte),
        "-ss", f"{min(5, inicio):.3f}", "-t", f"{fim - inicio:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
        str(destino),
    ])
    return destino


# Normalização de volume, alvo do TikTok (~-14 LUFS). Cada podcast-fonte
# chega num volume diferente; sem isso um clipe sai abafado no feed e o
# seguinte sai estourado. É filtro nativo do ffmpeg — aritmética de ganho,
# nada de modelo — e entra na mesma passada que já roda pro vídeo.
# TP=-1.5 deixa margem de pico pra recodificação do TikTok não clipar.
AUDIO_LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"


# ------------------------------------------------------------ título na tela
#
# Pedido do Bryan em 30/07/2026, depois do diagnóstico do canal.
#
# Por que existe: o clipe tinha legenda karaokê e MAIS NADA no primeiro meio
# segundo — a legenda aparece palavra a palavra conforme a fala, então quem
# rola o feed não tem o que ler pra decidir parar. Sete fontes independentes
# do corpus `destravar-tiktok` apontam o título em texto na abertura como a
# alavanca nº 1 pra fazer o dedo parar: o cérebro lê mais rápido do que ouve,
# e a decisão de assistir acontece antes do gancho falado terminar.
#
# É título de TÓPICO, não legenda: diz do que o vídeo trata em uma linha.

TITULO_SEGUNDOS = 3.5      # tempo na tela; o gancho falado cobre o resto
TITULO_MAX_LINHAS = 3      # acima disso vira parágrafo e ninguém lê
# Fração da largura do vídeo que o título pode ocupar. 0,88 deixa 6% de
# respiro de cada lado — sem isso a letra encosta na borda e fica com cara de
# print cortado, mesmo quando tecnicamente cabe.
TITULO_MARGEM = 0.88
# Piso do encolhimento, em fração do corpo ideal. Abaixo disso o título fica
# pequeno demais para ser lido em 3,5 s de tela, e é melhor a linha ficar
# comprida do que ilegível.
TITULO_CORPO_MIN = 0.55

# A fonte VIAJA COM O REPOSITÓRIO — não depender da fonte da máquina: o corte
# roda no ubuntu do GitHub Actions, e cada runner tem um conjunto diferente.
# Com a fonte no repo, o resultado é idêntico aqui e na nuvem.
FONTES_DIR = Path(__file__).resolve().parent / "fontes"


@lru_cache(maxsize=128)
def _largura_px(texto: str, fonte: str, corpo: int) -> float:
    """Largura RENDERIZADA do texto, em pixels, na fonte e no corpo dados.

    Sem Pillow cai numa estimativa por caractere — pior, mas nunca derruba o
    render. O fator 0,52 é a razão média largura/corpo das duas fontes usadas
    (ambas condensadas); serve de rede, não de medida.
    """
    try:
        from PIL import ImageFont
        return ImageFont.truetype(fonte, corpo).getlength(texto)
    except Exception:
        return len(texto) * corpo * 0.52


def _quebrar(texto: str, fonte: str, corpo: int, max_px: float) -> list[str]:
    """Quebra em até TITULO_MAX_LINHAS linhas que caibam em `max_px` PIXELS.

    Bug corrigido em 31/07/2026: ao fechar a última linha permitida, o laço
    saía com `break` e a palavra que tinha acabado de virar `atual` nunca
    era gravada — o título perdia a última palavra (ex: "...dominar a" sem
    "humanidade"). A última linha passou a absorver o resto do título.

    Bug corrigido em 01/08/2026: a quebra era por CONTAGEM DE CARACTERE
    (TITULO_LINHA_MAX=21), e caractere não tem largura fixa — "W" e "í" não
    ocupam o mesmo espaço. Linha dentro do limite de caracteres estourava os
    1080 px, e o drawtext não recorta nem encolhe: desenha centralizado e o
    que passa da borda some. Os títulos saíam cortados nas DUAS pontas
    ("Revolucionar a Medicina e a Vida" virava "evolucionar a Medicina e a
    Vid"). Agora a medida é a largura real na fonte, e quem garante que a
    última linha (a que absorve o resto) cabe é o encolhimento em
    `_ajustar_titulo`.
    """
    linhas: list[str] = []
    atual = ""
    for palavra in (texto or "").split():
        candidata = f"{atual} {palavra}".strip()
        ultima_linha = len(linhas) == TITULO_MAX_LINHAS - 1
        # `not atual`: palavra sozinha mais larga que a linha inteira entra
        # assim mesmo — senão o laço nunca a coloca em lugar nenhum. Quem
        # resolve esse caso é o encolhimento da fonte.
        if not atual or ultima_linha or _largura_px(candidata, fonte, corpo) <= max_px:
            atual = candidata
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas[:TITULO_MAX_LINHAS]


def _ajustar_titulo(texto: str, fonte: str, largura: int,
                    corpo_ideal: int) -> tuple[list[str], int]:
    """Maior corpo de fonte em que o título inteiro cabe na largura do vídeo.

    Encolher a fonte é o que resolve de vez: com quebra por pixel mas corpo
    fixo, um título longo continuaria estourando na última linha (que absorve
    o resto por desenho, para não perder palavra). Aqui o corpo cede antes da
    palavra sumir.
    """
    max_px = largura * TITULO_MARGEM
    minimo = max(12, round(corpo_ideal * TITULO_CORPO_MIN))
    corpo = corpo_ideal
    while True:
        linhas = _quebrar(texto, fonte, corpo, max_px)
        maior = max((_largura_px(l, fonte, corpo) for l in linhas), default=0.0)
        if maior <= max_px or corpo <= minimo:
            return linhas, corpo
        # Passo proporcional ao excesso: em vez de 1 px por volta, pula direto
        # para o corpo que faria a linha mais larga caber. Converge em 1-2
        # voltas mesmo num título que estoura muito.
        corpo = max(minimo, min(corpo - 1, int(corpo * max_px / maior)))


# Card de título em caixa branca arredondada por linha, estilo visto numa
# referência (Erica Bruno, TikTok, 02/08/2026) — pedido do Bryan pra
# substituir o drawtext (texto branco + contorno preto) de vez.
#
# drawtext não tem canto arredondado nativo, então o card inteiro é
# pré-renderizado como PNG com PIL (que já é dependência, via _largura_px) e
# sobreposto ao vídeo com o filtro `overlay` do ffmpeg — não dá pra fazer via
# `-vf` só, precisa de um 2º input (a imagem) e `-filter_complex`.
FONTE_TITULO_CAIXA = str(FONTES_DIR / "Poppins-Bold.ttf")

TITULO_PAD_X_FRAC = 0.38   # respiro horizontal dentro da caixa, fração do corpo
TITULO_PAD_Y_FRAC = 0.30
TITULO_RAIO_FRAC = 0.32    # raio do canto arredondado, fração da altura da caixa
TITULO_GAP_FRAC = 0.16     # respiro vertical entre uma caixa e a próxima
# Onde o card de título começa, em fração da altura. Sobe/desce o bloco
# inteiro. Ver o comentário em `vertical()` pro porquê de 0.16.
TITULO_TOPO_FRAC = 0.16


def imagem_titulo(texto: str, largura: int, altura: int, pasta_tmp: Path) -> Path | None:
    """Gera o PNG do card de título (transparente, com as caixas brancas
    arredondadas já desenhadas) ou None se não houver título ou fonte."""
    from PIL import Image, ImageDraw, ImageFont
    from . import destaque as _destaque

    texto = (texto or "").strip()
    if not texto or not Path(FONTE_TITULO_CAIXA).exists():
        return None

    texto = _destaque.marcar_titulo(texto)

    corpo_ideal = round(altura * 0.040)
    linhas, corpo = _ajustar_titulo(texto, FONTE_TITULO_CAIXA, largura, corpo_ideal)
    if not linhas:
        return None

    fonte = ImageFont.truetype(FONTE_TITULO_CAIXA, corpo)
    pad_x = round(corpo * TITULO_PAD_X_FRAC)
    pad_y = round(corpo * TITULO_PAD_Y_FRAC)
    gap = round(corpo * TITULO_GAP_FRAC)

    medidas = []
    for linha in linhas:
        bbox = fonte.getbbox(linha)          # (x0, y0, x1, y1) — y0 pode ser negativo
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        medidas.append((linha, bbox, w, h))

    altura_total = sum(h + 2 * pad_y for _, _, _, h in medidas) + gap * (len(medidas) - 1)
    img = Image.new("RGBA", (largura, altura_total), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = 0.0
    for linha, bbox, w, h in medidas:
        box_w, box_h = w + 2 * pad_x, h + 2 * pad_y
        x0 = (largura - box_w) / 2
        raio = round(box_h * TITULO_RAIO_FRAC)
        draw.rounded_rectangle([x0, y, x0 + box_w, y + box_h],
                               radius=raio, fill=(255, 255, 255, 255))
        draw.text((x0 + pad_x - bbox[0], y + pad_y - bbox[1]), linha,
                   font=fonte, fill=(0, 0, 0, 255))
        y += box_h + gap

    pasta_tmp.mkdir(parents=True, exist_ok=True)
    caminho = pasta_tmp / "titulo_caixa.png"
    img.save(caminho)
    return caminho


def _render(bruto: Path, filtro_video: str, ass: Path | None,
            destino: Path, audio_dublado: Path | None = None,
            img_titulo: Path | None = None, topo_titulo: int = 0) -> Path:
    cadeia = filtro_video
    if ass is not None:
        # fontsdir aponta pra pasta de fontes do repositório. O .ass pede
        # "Inter Black" pelo NOME (legendas.py), e o ubuntu do GitHub Actions
        # não tem Inter instalada — o libass caía calado numa fonte qualquer.
        # A legenda dos vídeos até 30/07 provavelmente não era Inter.
        cadeia += (f",subtitles='{_escapar(ass)}'"
                   f":fontsdir='{_escapar(FONTES_DIR)}'")

    if img_titulo is not None:
        # O card de título agora é PNG (ver imagem_titulo) sobreposto com
        # `overlay` — drawtext dava pra fazer só com -vf, overlay precisa de
        # um input a mais e -filter_complex. -loop 1 deixa a imagem estática
        # "infinita" — e MEDIDO em 02/08/2026: sem -shortest o processo não
        # termina sozinho quando o vídeo principal acaba (testei sem, o
        # ffmpeg ficou rodando e o arquivo de saída passou de 800 MB pra um
        # clipe de 84s). -shortest é obrigatório aqui, com ou sem dublagem.
        if audio_dublado is not None:
            filtro = (f"[0:v]{cadeia}[base];"
                      f"[base][2:v]overlay=0:{topo_titulo}:"
                      f"enable='lt(t,{TITULO_SEGUNDOS})'[v]")
            midia.roda([
                "ffmpeg", "-y",
                "-i", str(bruto), "-i", str(audio_dublado),
                "-loop", "1", "-i", str(img_titulo),
                "-filter_complex", filtro,
                "-map", "[v]", "-map", "1:a:0",
                *_encoder(),
                "-af", AUDIO_LOUDNORM,
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(destino),
            ])
        else:
            filtro = (f"[0:v]{cadeia}[base];"
                      f"[base][1:v]overlay=0:{topo_titulo}:"
                      f"enable='lt(t,{TITULO_SEGUNDOS})'[v]")
            midia.roda([
                "ffmpeg", "-y",
                "-i", str(bruto),
                "-loop", "1", "-i", str(img_titulo),
                "-filter_complex", filtro,
                "-map", "[v]", "-map", "0:a:0",
                *_encoder(),
                "-af", AUDIO_LOUDNORM,
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(destino),
            ])
        return destino

    if audio_dublado is not None:
        # troca a trilha original pela dublada — vídeo vem do bruto (input 0),
        # áudio vem do arquivo dublado (input 1)
        midia.roda([
            "ffmpeg", "-y", "-i", str(bruto), "-i", str(audio_dublado),
            "-vf", cadeia, *_encoder(),
            "-map", "0:v:0", "-map", "1:a:0",
            "-af", AUDIO_LOUDNORM,
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(destino),
        ])
        return destino

    midia.roda([
        "ffmpeg", "-y", "-i", str(bruto),
        "-vf", cadeia, *_encoder(),
        "-af", AUDIO_LOUDNORM,
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(destino),
    ])
    return destino


# Punch-in cíclico. Antes era um Ken Burns monotônico de 1.00→1.06 ao longo
# do clipe inteiro — o PLAYBOOK §5 classifica isso como "sutil demais" e pede
# variação de enquadramento a cada 5-8s, porque essa camada de edição é o que
# separa corte transformado de republicação (e sustenta o RPM).
#
# A oscilação é COSSENOIDAL de propósito: zoom que sobe e reinicia de golpe
# produziria o mesmo salto visível que o crop em degrau produzia (corrigido
# em enquadrar.py no mesmo dia). Cosseno não tem descontinuidade — o quadro
# respira, sem tranco em ponto nenhum do ciclo.
_PUNCH_AMPLITUDE = 0.10   # 1.00 -> 1.10 no pico do ciclo
_PUNCH_PERIODO_S = 6.5    # dentro da faixa de 5-8s que o corpus recomenda


def _ken_burns(bruto: Path, largura: int, altura: int) -> str:
    """Punch-in cíclico suave. Além de disfarçar trecho parado, é edição de
    verdade em cima do material — importa pra não cair em 'conteúdo
    reaproveitado sem transformação' quando o corte é de vídeo de terceiros.

    Usa o fps NATIVO da fonte (nunca força 30) — forçar conversão de frame
    rate no zoompan foi o que causou legenda dessincronizando do áudio.
    """
    fps = midia.fps(bruto)
    ciclo = max(1.0, _PUNCH_PERIODO_S) * fps          # frames por ciclo
    meia = _PUNCH_AMPLITUDE / 2
    # (1-cos)/2 varia 0..1 sem quina; 'on' é o número do frame de saída.
    z = f"1+{meia:.4f}*(1-cos(2*PI*on/{ciclo:.3f}))"
    return (f",zoompan=z='{z}':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={largura}x{altura}:fps={fps:.3f}")


def vertical(bruto: Path, ass: Path | None, destino: Path,
             audio_dublado: Path | None = None, titulo: str = "") -> Path:
    """9:16 para Shorts, com o quadro seguindo o rosto.

    `titulo` desenha o card de abertura (ver imagem_titulo) — caixa branca
    arredondada por linha, sobreposta com `overlay` depois do punch-in de
    propósito: o zoompan reescala o quadro, e a caixa entraria ampliada e
    cortada se viesse antes dele.
    """
    l, a = midia.dimensoes(bruto)
    caminho = enquadrar.trajetoria(bruto, l, a)
    lv, av = config.VERTICAL
    filtro = enquadrar.filtro_vertical(l, a, caminho) + _ken_burns(bruto, lv, av)
    if config.GRADE_CINEMATICO:
        filtro += pos_producao.FILTRO_COR_CINEMATICO
    # A imagem do título vai pra pasta de TRABALHO, não pra pasta do clipe: a
    # pasta do clipe herda o nome do vídeo-fonte, e nome de vídeo tem
    # apóstrofo, dois-pontos e o que mais o YouTube deixar. Caminho previsível
    # aqui é o que evita a próxima quebra de filtro (ver _escapar).
    img_titulo = imagem_titulo(titulo, lv, av, config.TRABALHO / "titulo")
    # 0.075 -> 0.16 em 25/08/2026. A 7,5% o titulo comecava a 144 px do topo
    # de 1920, e a MINIATURA DA GRADE do perfil do TikTok recorta a celula
    # pra um formato mais quadrado que 9:16, cortando ~1/4 da altura pelo
    # TOPO. Resultado medido nos prints do Bryan: titulo de 4 linhas perdia a
    # primeira ("Exercito Cria Baratas" sumia de "CIBORGUES para zonas de
    # guerra"), e ele reenquadrava na mao clipe a clipe. A capa custom nao
    # resolve: a API do Buffer respondeu que rede social nenhuma aceita
    # imagem de capa propria — so' da' pra escolher o FRAME, nao o recorte.
    #
    # 0.16 = 307 px, abaixo da linha de corte estimada (~240 px). Continua
    # longe da legenda, que fica a 30% da base. ESTIMATIVA a validar no
    # proximo lote: se ainda cortar, subir pra 0.20.
    topo = round(av * TITULO_TOPO_FRAC)
    return _render(bruto, filtro, ass, destino, audio_dublado,
                    img_titulo=img_titulo, topo_titulo=topo)


def horizontal(bruto: Path, ass: Path | None, destino: Path,
               audio_dublado: Path | None = None) -> Path:
    """16:9 tela cheia — o corte de 1 minuto que você queria também."""
    lh, ah = config.HORIZONTAL
    filtro = (f"scale={lh}:{ah}:force_original_aspect_ratio=decrease,"
              f"pad={lh}:{ah}:(ow-iw)/2:(oh-ih)/2:black") + _ken_burns(bruto, lh, ah)
    if config.GRADE_CINEMATICO:
        filtro += pos_producao.FILTRO_COR_CINEMATICO
    return _render(bruto, filtro, ass, destino, audio_dublado)


def capa(bruto: Path, destino: Path, em: float = 1.0) -> Path:
    """Thumbnail: pega um frame já com o crop vertical aplicado."""
    l, a = midia.dimensoes(bruto)
    filtro = enquadrar.filtro_vertical(l, a, [])
    midia.roda(["ffmpeg", "-y", "-ss", f"{em:.2f}", "-i", str(bruto),
                "-vf", filtro, "-frames:v", "1", "-q:v", "2", str(destino)])
    return destino
