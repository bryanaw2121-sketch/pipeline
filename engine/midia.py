"""Tudo que fala com ffmpeg/ffprobe/yt-dlp. Nada sai da máquina aqui."""
import json, os, re, shutil, subprocess
from pathlib import Path

import config


def _exige(bin_: str):
    if not shutil.which(bin_):
        raise RuntimeError(f"'{bin_}' não está no PATH. Rode setup_nitro5.ps1.")


def roda(cmd: list[str], silencioso=True):
    r = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL if silencioso else None,
        stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"falhou: {' '.join(cmd[:3])}...\n{(r.stderr or '')[-1500:]}")
    return r


def tem_nvenc() -> bool:
    """GTX 1650 tem NVENC. Em máquina sem NVIDIA, ou com driver desatualizado
    demais pro NVENC (precisa checar de verdade, não só se o encoder existe
    no build do ffmpeg), cai pra CPU."""
    _exige("ffmpeg")
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if "h264_nvenc" not in r.stdout:
            return False
        # o encoder pode existir no build e mesmo assim falhar por driver
        # antigo — só sabemos tentando encodar de verdade.
        teste = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return teste.returncode == 0
    except Exception:
        return False


def baixar(url: str, destino: Path) -> Path:
    """yt-dlp. Limita a 1080p — não adianta baixar 4K pra cortar Short.

    destino é sempre a mesma pasta/nome ("fonte.*") entre chamadas — com
    --manter-temp o arquivo da rodada anterior sobrevive, e o yt-dlp pula o
    download vendo o arquivo já ali, processando a URL nova com o vídeo
    velho sem avisar. Por isso limpa qualquer fonte.* antigo antes de baixar."""
    _exige("yt-dlp")
    destino.mkdir(parents=True, exist_ok=True)
    for antigo in destino.glob("fonte.*"):
        antigo.unlink()
    alvo = destino / "fonte.%(ext)s"
    cmd = [
        "yt-dlp",
        "-f", "bv*[height<=480]+ba/b[height<=480]/b",
        "--merge-output-format", "mp4",
        # cliente Android costuma escapar do bloqueio "sign in to confirm
        # you're not a bot" que IPs de datacenter (GitHub Actions) levam
        # do YouTube — não muda nada pra quem roda local.
        "--extractor-args", "youtube:player_client=android",
    ]
    # em IP de datacenter (GitHub Actions) o Android client sozinho não
    # basta — passa cookies de uma sessão logada de verdade. Local não usa
    # isso (variável não fica setada).
    cookies = os.getenv("YTDLP_COOKIES_FILE")
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", cookies]
    # provedor de PO Token (bgutil) — gratuito, só ativa se o servidor
    # local do provider estiver de pé (setado só no workflow do GitHub
    # Actions; local não usa isso).
    pot_server = os.getenv("YTDLP_POT_SERVER")
    if pot_server:
        cmd += ["--extractor-args",
                f"youtubepot-bgutilscript:server_home={pot_server}"]
    cmd += ["-o", str(alvo), url]
    roda(cmd, silencioso=False)
    achados = list(destino.glob("fonte.*"))
    if not achados:
        raise RuntimeError("yt-dlp não produziu arquivo")
    return achados[0]


def duracao(video: Path) -> float:
    _exige("ffprobe")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def dimensoes(video: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    s = json.loads(r.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def fps(video: Path) -> float:
    """fps nativo da fonte. Usado pra não forçar conversão de frame rate em
    filtros como zoompan — reamostrar fps é uma causa clássica de legenda
    dessincronizar do áudio."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    s = json.loads(r.stdout)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    den = den or "1"
    return float(num) / float(den) if float(den) else 30.0


def extrair_audio(video: Path, saida: Path) -> Path:
    """16kHz mono FLAC.

    O Whisper converte pra 16kHz internamente de qualquer forma, então isso
    não perde informação — só encolhe o arquivo. FLAC é sem perda.
    """
    _exige("ffmpeg")
    saida.parent.mkdir(parents=True, exist_ok=True)
    roda(["ffmpeg", "-y", "-i", str(video), "-vn",
          "-ac", "1", "-ar", "16000", "-c:a", "flac", str(saida)])
    return saida


def fatiar_audio(audio: Path, inicio: float, fim: float, saida: Path) -> Path:
    """Recorta um pedaço do áudio (usado pra transcrever só os clipes)."""
    roda(["ffmpeg", "-y", "-ss", f"{inicio:.3f}", "-to", f"{fim:.3f}",
          "-i", str(audio), "-ac", "1", "-ar", "16000",
          "-c:a", "flac", str(saida)])
    return saida


def mb(caminho: Path) -> float:
    return caminho.stat().st_size / (1024 * 1024)


_FREEZE_START = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"lavfi\.freezedetect\.freeze_end:\s*([\d.]+)")


_SILENCIO_INI = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCIO_FIM = re.compile(r"silence_end:\s*([\d.]+)")


def detectar_silencios(arquivo: Path, limiar_db: float, dur_min: float
                       ) -> list[tuple[float, float]]:
    """Blocos de silêncio (início, fim) em segundos."""
    _exige("ffmpeg")
    r = subprocess.run(
        ["ffmpeg", "-i", str(arquivo),
         "-af", f"silencedetect=n={limiar_db}dB:d={dur_min}",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    saida = r.stderr or ""
    inicios = [float(x) for x in _SILENCIO_INI.findall(saida)]
    fins = [float(x) for x in _SILENCIO_FIM.findall(saida)]
    if len(inicios) > len(fins):        # silêncio aberto até o fim do arquivo
        fins.append(duracao(arquivo))
    return [(max(0.0, i), f) for i, f in zip(inicios, fins) if f > i]


def cortar_silencios(entrada: Path, saida: Path, *,
                     limiar_db: float | None = None,
                     dur_min: float | None = None,
                     folga: float | None = None) -> Path:
    """Remove as pausas mortas ("decupagem"), deixando o clipe mais rápido.

    É o ajuste de retenção de maior impacto segundo a destilação
    (PLAYBOOK_TIKTOK.md §4.4, CONSENSO 3) e ainda conta como camada de
    edição real pro bônus de originalidade do TikTok.

    Não corta o silêncio inteiro: deixa `folga` segundos em cada ponta,
    senão a fala fica colada e soa cortada na garganta. Também não mexe em
    pausa curta — só nas acima de `dur_min`, que é o tempo morto de fato.

    Devolve `saida` se cortou algo; devolve `entrada` intacta se não havia
    o que cortar (assim quem chama pode sempre usar o retorno).
    """
    limiar_db = config.SILENCIO_LIMIAR_DB if limiar_db is None else limiar_db
    dur_min = config.SILENCIO_DUR_MIN_S if dur_min is None else dur_min
    folga = config.SILENCIO_FOLGA_S if folga is None else folga

    total = duracao(entrada)
    silencios = detectar_silencios(entrada, limiar_db, dur_min)
    if not silencios:
        return entrada

    # o que MANTER é o complemento dos silêncios, com folga nas bordas
    manter, cursor = [], 0.0
    for ini, fim in silencios:
        corte_ini, corte_fim = ini + folga, fim - folga
        if corte_fim - corte_ini < 0.10:      # sobrou pouco, não vale cortar
            continue
        if corte_ini > cursor:
            manter.append((cursor, corte_ini))
        cursor = corte_fim
    if cursor < total:
        manter.append((cursor, total))

    manter = [(a, b) for a, b in manter if b - a > 0.05]
    if not manter:
        return entrada
    removido = total - sum(b - a for a, b in manter)
    if removido < 0.5:                        # ganho irrelevante
        return entrada

    partes = []
    for n, (a, b) in enumerate(manter):
        partes.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{n}];"
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{n}];")
    encadeia = "".join(f"[v{n}][a{n}]" for n in range(len(manter)))
    filtro = ("".join(partes)
              + f"{encadeia}concat=n={len(manter)}:v=1:a=1[v][a]")

    saida.parent.mkdir(parents=True, exist_ok=True)
    roda(["ffmpeg", "-y", "-i", str(entrada), "-filter_complex", filtro,
          "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-c:a", "aac", "-b:a", "192k", str(saida)])
    print(f"      silêncios: -{removido:.1f}s "
          f"({total:.1f}s → {duracao(saida):.1f}s, {len(manter)} pedaços)")
    return saida


def congelamento_s(fonte: Path, inicio: float, fim: float) -> float:
    """Maior ZONA de imagem travada (em segundos) dentro de [inicio, fim] —
    câmera/conexão do entrevistado congelando enquanto o áudio segue.
    Existe pra evitar cortar um trecho ótimo em áudio mas com vídeo ruim —
    o Gemini escolhe pelo que é dito, não vê esse tipo de falha.

    Travamento de verdade raramente é UM bloco limpo: geralmente pisca —
    trava, mostra um frame, trava de novo — o que o freezedetect registra
    como vários blocos curtos e próximos. Por isso agrupa blocos com menos
    de 1s de intervalo entre eles numa mesma zona antes de medir o maior
    trecho ruim; olhar só o maior bloco ISOLADO deixava passar exatamente
    esse tipo de travamento picotado.
    """
    _exige("ffmpeg")
    r = subprocess.run(
        ["ffmpeg", "-ss", f"{inicio:.3f}", "-i", str(fonte),
         "-t", f"{fim - inicio:.3f}",
         # n=-60dB é o padrão do ffmpeg. Estava em -45dB, e nessa tolerância
         # o filtro não distinguia NADA: medido em 28/07/2026, trecho de fala
         # normal e frame genuinamente congelado davam os mesmos 8,3s. A -60dB
         # o normal cai pra 0,9s e o congelamento real continua em 8,3s —
         # afrouxar não custou sensibilidade, só tirou o falso positivo.
         "-vf", "freezedetect=n=-60dB:d=0.5", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    saida = r.stderr or ""
    inicios = [float(m) for m in _FREEZE_START.findall(saida)]
    fins = [float(m) for m in _FREEZE_END.findall(saida)]
    blocos = sorted(zip(inicios, fins))
    if not blocos:
        return 0.0

    maior_zona = 0.0
    zona_ini, zona_fim = blocos[0]
    for ini_b, fim_b in blocos[1:]:
        if ini_b - zona_fim < 1.0:
            zona_fim = fim_b
        else:
            maior_zona = max(maior_zona, zona_fim - zona_ini)
            zona_ini, zona_fim = ini_b, fim_b
    maior_zona = max(maior_zona, zona_fim - zona_ini)
    return maior_zona


def pular_congelamento_inicial(fonte: Path, inicio: float, fim: float,
                               max_ajuste: float = 2.5) -> float:
    """Se o clipe começa em cima de um frame travado (comum quando o corte
    cai bem na borda de uma pausa/transição), empurra o início pra depois
    do congelamento em vez de abrir o Short com imagem parada.

    d=0.15 pega travamento curto que congelamento_s() (d=0.5, olha o
    clipe inteiro) ignora de propósito pra não confundir com fala parada
    normal — aqui o alvo é só o comecinho, onde qualquer trava incomoda."""
    _exige("ffmpeg")
    r = subprocess.run(
        ["ffmpeg", "-ss", f"{inicio:.3f}", "-i", str(fonte),
         "-t", f"{min(max_ajuste + 1.0, fim - inicio):.3f}",
         "-vf", "freezedetect=n=-60dB:d=0.15", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    saida = r.stderr or ""
    inicios = [float(m) for m in
               re.findall(r"lavfi\.freezedetect\.freeze_start:\s*([\d.]+)", saida)]
    fins = [float(m) for m in
            re.findall(r"lavfi\.freezedetect\.freeze_end:\s*([\d.]+)", saida)]
    blocos = list(zip(inicios, fins))
    if not blocos or blocos[0][0] > 0.1:
        return inicio   # não trava logo de cara, não mexe

    # pode ter vários blocos colados (0→0.56, 0.56→0.76, ...) — anda por
    # todos enquanto forem contínuos, o fim do congelamento é o fim do
    # último bloco sem lacuna
    fim_congelado = blocos[0][1]
    for ini_b, fim_b in blocos[1:]:
        if ini_b - fim_congelado > 0.1:
            break
        fim_congelado = fim_b

    deslocamento = min(fim_congelado + 0.1, max_ajuste)
    return inicio + deslocamento


def pular_congelamento_final(fonte: Path, inicio: float, fim: float,
                             max_ajuste: float = 2.5) -> float:
    """Espelho de pular_congelamento_inicial: se o clipe termina em cima de
    frame travado, puxa o fim pra antes do congelamento em vez de fechar o
    Short numa imagem parada — sabedoria/SABEDORIA_YT.md aponta tela parada
    no fim como um dos motivos do Short "travar" no algoritmo."""
    _exige("ffmpeg")
    janela = min(max_ajuste + 1.0, fim - inicio)
    r = subprocess.run(
        ["ffmpeg", "-ss", f"{fim - janela:.3f}", "-i", str(fonte),
         "-t", f"{janela:.3f}",
         "-vf", "freezedetect=n=-60dB:d=0.15", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    saida = r.stderr or ""
    inicios = [float(m) for m in
               re.findall(r"lavfi\.freezedetect\.freeze_start:\s*([\d.]+)", saida)]
    fins = [float(m) for m in
            re.findall(r"lavfi\.freezedetect\.freeze_end:\s*([\d.]+)", saida)]
    # tempos relativos à janela; converte pra absoluto na fonte
    blocos = [(fim - janela + a, fim - janela + b) for a, b in zip(inicios, fins)]
    # só interessa travamento que já está rolando ou começa perto do fim
    blocos = [b for b in blocos if fim - b[0] < max_ajuste + 0.2]
    if not blocos:
        return fim   # não trava no fim, não mexe

    inicio_congelado = min(b[0] for b in blocos)
    novo_fim = max(inicio + 1.0, inicio_congelado - 0.1)
    return max(novo_fim, fim - max_ajuste)
