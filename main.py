"""Motor de cortes — Nitro 5.

    python main.py --url "https://youtube.com/watch?v=..."
    python main.py --arquivo "C:\\videos\\live.mp4" --qtd 15
    python main.py --url "..." --so-audio        # mais barato, não vê a imagem

Divisão de trabalho:
    Gemini  -> escolhe os momentos e escreve título/descrição/tags
    Groq    -> legenda palavra a palavra (só nos clipes, nunca no vídeo cheio)
    ffmpeg  -> corta, enquadra no rosto, queima legenda, renderiza (NVENC)
"""
import argparse, json, re, shutil, sys, time, unicodedata
from datetime import datetime
from pathlib import Path

import config
from engine import (midia, selecao, transcricao, legendas, render, traducao,
                    dublagem, status, ancoragem, pos_producao, voz_clonada, suavizar)

# console do Windows costuma abrir em cp1252, que não tem caractere "→"
# usado nos prints de progresso — força UTF-8 pra não derrubar o processo
# no meio de um render por causa de log.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def _limpar(nome: str) -> str:
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "")
    return nome.strip()[:60].rstrip() or "clipe"


def _hashtag(tag: str) -> str:
    """Transforma uma tag em hashtag válida.

    Hashtag NÃO pode ter espaço: "#Elon Musk" é lido como "#Elon" + texto
    solto "Musk" — a segunda palavra vira lixo na legenda. Acento também é
    ruim pra descoberta (quem busca digita sem), então normaliza pra ASCII.
    """
    sem_acento = (unicodedata.normalize("NFKD", tag)
                  .encode("ascii", "ignore").decode("ascii"))
    return "#" + "".join(ch for ch in sem_acento if ch.isalnum())


def _legenda(c: dict) -> str:
    """Legenda pronta pra colar: título, descrição e hashtags válidas."""
    tags = " ".join(_hashtag(t) for t in (c.get("tags") or []) if t)
    return f"{c.get('titulo','')}\n\n{c.get('descricao','')}\n\n{tags}".strip()


def processar(fonte: Path, qtd: int, usar_video: bool, idioma: str,
              so_vertical: bool, traduzir: bool = True, dublar: bool = False,
              url_origem: str = "", recorte: tuple[float, float] | None = None,
              estilo_legenda: int = 1, manter_temp: bool = False,
              fala_literal: bool = False) -> Path:
    t0 = time.time()
    config.TRABALHO.mkdir(parents=True, exist_ok=True)
    nome_fonte = fonte.name

    dur = midia.duracao(fonte)
    print(f"\n[1/5] fonte: {fonte.name}  ({dur/60:.1f} min)")

    # Gemini recusa vídeo com muitos frames: "Please use fewer than 10800
    # images" (descoberto 28/07/2026, vídeo de 247min e outro de 134min
    # falharam com 400). Sem saber a taxa de amostragem exata, 90min é
    # limite seguro observado — acima disso cai pra só-áudio, sem imagem,
    # sem limite de frame (perde "ver a cena", mas processa qualquer duração).
    LIMITE_VIDEO_MIN = 90
    if usar_video and dur / 60 > LIMITE_VIDEO_MIN:
        print(f"      [!] vídeo passa de {LIMITE_VIDEO_MIN}min — Gemini rejeita "
              f"por excesso de frames, caindo pra modo só-áudio")
        usar_video = False

    # ---- áudio: só é necessário se o Gemini for analisar sem a imagem
    print("[2/5] extraindo áudio 16kHz mono...")
    status.etapa(nome_fonte, "extraindo_audio")
    audio = midia.extrair_audio(fonte, config.TRABALHO / "audio.flac")
    print(f"      {midia.mb(audio):.1f} MB")

    if recorte:
        # Modo manual: o usuário já sabe qual trecho quer (ex: refazer um
        # corte que performou bem). Não há seleção a fazer, e a checagem de
        # congelamento é DE PROPÓSITO pulada — a escolha é explícita dele,
        # e nesse vídeo o filtro descartava justamente o trecho bom.
        ini_r, fim_r = recorte
        fim_r = min(fim_r, dur)
        if fim_r <= ini_r:
            sys.exit(f"--recorte inválido: {ini_r}-{fim_r}")
        print(f"[3/5] recorte manual {ini_r:.1f}s→{fim_r:.1f}s "
              f"(pula seleção do Gemini e a checagem de congelamento)")
        status.etapa(nome_fonte, "gemini_metadados")
        trecho = render.cortar(fonte, ini_r, fim_r,
                               config.TRABALHO / "recorte_meta.mp4")
        meta = selecao.metadados(trecho, usar_video)
        meta["inicio_s"], meta["fim_s"] = round(ini_r, 2), round(fim_r, 2)
        meta["duracao_s"] = round(fim_r - ini_r, 2)
        clipes = [meta]
        print(f"      \"{str(meta.get('titulo',''))[:60]}\"")
    else:
        # ---- Gemini vê o material INTEIRO de uma vez (aguenta 9,5h)
        alvo = fonte if usar_video else audio
        print(f"[3/5] Gemini analisando {'vídeo (com imagem)' if usar_video else 'áudio'}"
              f" — {midia.mb(alvo):.0f} MB, sem chunking...")
        status.etapa(nome_fonte, "gemini_selecionando")
        clipes = selecao.escolher(alvo, dur, usar_video, qtd)
        if not clipes:
            print("nenhum momento aprovado na validação.")
            if url_origem:
                status.marcar_item(url_origem, "erro", erro="nenhum momento aprovado")
            sys.exit(1)
        print(f"      {len(clipes)} momentos escolhidos")

        # o Gemini escolhe pelo áudio/fala — não percebe se a câmera do
        # entrevistado travou (comum em gravação remota). Descarta aqui antes
        # de gastar Groq/render com um clipe de imagem parada.
        status.etapa(nome_fonte, "checando_congelamento")
        bons = []
        for c in clipes:
            cong = midia.congelamento_s(fonte, c["inicio_s"], c["fim_s"])
            if cong > config.CONGELAMENTO_MAX_S:
                print(f"      [!] descartado \"{c.get('titulo','')[:40]}\": "
                      f"bloco de {cong:.1f}s com imagem travada")
                continue
            bons.append(c)
        clipes = bons
        if not clipes:
            print("todos os momentos tinham câmera travada — nenhum clipe sobrou.")
            if url_origem:
                status.marcar_item(url_origem, "erro", erro="só sobrou clipe com câmera travada")
            sys.exit(1)

    destino = config.SAIDA / datetime.now().strftime("%Y-%m-%d_%H%M") / _limpar(fonte.stem)
    destino.mkdir(parents=True, exist_ok=True)

    resumo = []
    for i, c in enumerate(clipes, 1):
        ini, fim = c["inicio_s"], c["fim_s"]
        if not recorte:   # no modo manual o usuário mandou os tempos exatos
            # ANTES do congelamento: recua o início até o começo da frase.
            # Medido em 30/07 nos insights reais — os clipes abriam no meio da
            # frase ("A GENTE PROVAVELMENTE...") e metade da audiência saía
            # em 0:02. Ver engine/ancoragem.py.
            ini = ancoragem.ancorar(fonte, ini, fim, idioma)
            c["inicio_s"] = ini

            nova_ini = midia.pular_congelamento_inicial(fonte, ini, fim)
            if nova_ini > ini:
                print(f"      início ajustado {ini:.1f}s→{nova_ini:.1f}s "
                      f"(pulando frame travado na abertura do clipe)")
                ini = nova_ini
                c["inicio_s"] = ini
            novo_fim = midia.pular_congelamento_final(fonte, ini, fim)
            if novo_fim < fim:
                print(f"      fim ajustado {fim:.1f}s→{novo_fim:.1f}s "
                      f"(pulando frame travado no fechamento do clipe)")
                fim = novo_fim
                c["fim_s"] = fim
        pasta = destino / f"{i:02d}_nota{int(c.get('nota', 0))}_{_limpar(c.get('titulo', ''))}"
        pasta.mkdir(parents=True, exist_ok=True)
        print(f"\n[4/5] clipe {i}/{len(clipes)}  {ini:.1f}s→{fim:.1f}s  "
              f"nota {c.get('nota')}  \"{str(c.get('gancho',''))[:50]}\"")

        status.etapa(nome_fonte, "cortando", c.get("titulo", ""), i, len(clipes))
        bruto = render.cortar(fonte, ini, fim, config.TRABALHO / f"bruto_{i:02d}.mp4")

        # ---- decupagem: tira as pausas mortas (retenção + originalidade)
        # Não roda com --dublar: a trilha dublada é gerada pra duração do
        # recorte original e dessincronizaria.
        dur_final = fim - ini
        if config.CORTAR_SILENCIOS and not dublar:
            enxuto = midia.cortar_silencios(
                bruto, config.TRABALHO / f"bruto_{i:02d}_enxuto.mp4")
            if enxuto != bruto:
                nova_dur = midia.duracao(enxuto)
                if nova_dur < config.DUR_MIN:
                    # encurtar até aqui derrubaria o clipe abaixo do mínimo
                    # que garante monetização — melhor manter as pausas.
                    print(f"      [!] decupagem descartada: deixaria o clipe "
                          f"em {nova_dur:.1f}s (< DUR_MIN {config.DUR_MIN}s)")
                else:
                    bruto, dur_final = enxuto, nova_dur

        if config.ESTABILIZAR:
            print("      estabilizando (vidstab)...")
            bruto = pos_producao.estabilizar(
                bruto, config.TRABALHO / f"bruto_{i:02d}_estavel.mp4")

        # legenda: só este pedacinho vai pra Groq (~1 MB, longe dos 25 MB).
        # Extrai do PRÓPRIO clipe (não fatia o áudio da fonte) — depois da
        # decupagem os tempos não batem mais com o original.
        peda = midia.extrair_audio(bruto, config.TRABALHO / f"clip_{i:02d}.flac")
        print(f"      Groq transcrevendo ({midia.mb(peda):.1f} MB)...")
        status.etapa(nome_fonte, "transcrevendo", c.get("titulo", ""), i, len(clipes))
        ps = transcricao.palavras(peda, idioma)

        # guardrail de ritmo [PAPER]: acima de ~200 palavras/min a
        # compreensão cai (Weinstein-Shr & Griffiths). A decupagem não
        # acelera a fala, mas aumenta a densidade — vale medir e avisar.
        if ps and dur_final > 0:
            wpm = len(ps) / (dur_final / 60)
            if wpm > 200:
                print(f"      [!] ritmo alto: {wpm:.0f} palavras/min "
                      f"(acima de 200 a compreensão cai)")

        # dublado implica legenda traduzida também (áudio e texto combinando)
        precisa_traduzir = (traduzir or dublar) and idioma != "pt" and ps
        audio_dublado = None
        if precisa_traduzir:
            print("      traduzindo pra pt-BR...")
            status.etapa(nome_fonte, "traduzindo", c.get("titulo", ""), i, len(clipes))
            # `genero_falante` vem da SELECAO, que ve' o video — o prompt de
            # narracao sozinho so' consegue inferir pelo texto, e transcricao
            # costuma nao ter pista. Em 25/08/2026 um clipe foi ao ar dizendo
            # 'A ESPECIALISTA EXPLICOU' com um homem na tela.
            segmentos = traducao.traduzir_segmentos(
                ps, narrar=dublar and not fala_literal,
                genero_falante=c.get("genero_falante"))
            ps = traducao.segmentos_para_palavras(segmentos)
            if dublar:
                if config.VOZ_CLONADA_ATIVA:
                    print("      dublando (voz clonada, Chatterbox)...")
                    status.etapa(nome_fonte, "dublando", c.get("titulo", ""), i, len(clipes))
                    audio_dublado, timing_dub = voz_clonada.gerar_trilha(
                        segmentos, fim - ini, config.TRABALHO / f"dub_{i:02d}",
                        amostra_voz=config.VOZ_CLONADA_AMOSTRA)
                    # a legenda tem que seguir o timing REAL do áudio
                    # dublado (pausas entre frases + atempo final mudam o
                    # ritmo em relação ao vídeo fonte), não o timing de
                    # `ps`/`segmentos` — senão ela "corre" na frente ou
                    # atrás da voz (Bryan reportou em 05/08/2026).
                    if timing_dub:
                        palavras_dub = []
                        for tm in timing_dub:
                            novas = re.findall(r"\S+", tm["frase"])
                            palavras_dub.extend(traducao.redistribuir_palavras(
                                novas, tm["inicio"], tm["fim"]))
                        if palavras_dub:
                            ps = palavras_dub
                else:
                    print("      dublando (edge-tts)...")
                    status.etapa(nome_fonte, "dublando", c.get("titulo", ""), i, len(clipes))
                    audio_dublado = dublagem.gerar_trilha(
                        segmentos, fim - ini, config.TRABALHO / f"dub_{i:02d}")

        # Palavra sensivel vira grafia adaptada (morte -> m0rte) APENAS no texto
        # escrito: legenda na tela, card de titulo e legenda do post. O audio
        # da dublagem ja' foi gerado acima com a palavra ORIGINAL, e continua
        # assim de proposito — o TTS leria "m0rte" como "m zero erre te e", e
        # fala natural e' o que sustenta a retencao. Ver engine/suavizar.py.
        # Pedido do Bryan em 25/08/2026: "nao quero perder videos bons, temos
        # a oportunidade de modificar para evitar certas palavras".
        if config.SUAVIZAR_TEXTO:
            ps = suavizar.palavras(ps)
            c = dict(c)
            c["titulo"] = suavizar.texto(c.get("titulo", ""))
            c["descricao"] = suavizar.texto(c.get("descricao", ""))

        lv, av = config.VERTICAL
        ass_v = legendas.escrever(ps, config.TRABALHO / f"v_{i:02d}.ass", lv, av,
                                   estilo=estilo_legenda)
        print("      renderizando 9:16 com face tracking...")
        status.etapa(nome_fonte, "renderizando_vertical", c.get("titulo", ""), i, len(clipes))
        # O título vai NA TELA nos primeiros segundos, não só na descrição.
        # O Gemini já devolvia esse campo e ele só era usado como legenda do
        # post — a informação existia e estava sendo jogada fora justamente
        # onde ela decide se a pessoa para de rolar. Ver render.filtro_titulo.
        render.vertical(bruto, ass_v, pasta / "short_9x16.mp4", audio_dublado,
                        titulo=c.get("titulo", ""))

        if not so_vertical:
            lh, ah = config.HORIZONTAL
            ass_h = legendas.escrever(ps, config.TRABALHO / f"h_{i:02d}.ass", lh, ah,
                                       estilo=estilo_legenda)
            print("      renderizando 16:9 tela cheia...")
            status.etapa(nome_fonte, "renderizando_horizontal", c.get("titulo", ""), i, len(clipes))
            render.horizontal(bruto, ass_h, pasta / "fullscreen_16x9.mp4", audio_dublado)

        render.capa(bruto, pasta / "capa.jpg")

        meta = {k: c.get(k) for k in
                ("titulo", "descricao", "tags", "gancho", "porque",
                 "nota", "inicio_s", "fim_s", "duracao_s",
                 "tipo_conteudo", "emocao_dominante", "dinamica",
                 "genero_falante",
                 "marcador_viral", "arquetipo", "forca_gancho",
                 "compartilhabilidade", "independencia",
                 "intensidade_emocional", "valor_social")}
        meta["fonte"] = fonte.name
        # duracao_s vinha do recorte na fonte; depois da decupagem o clipe
        # é mais curto. O que vale pra regra dos 60s é a duração FINAL.
        meta["duracao_recorte_s"] = round(fim - ini, 2)
        meta["duracao_s"] = round(dur_final, 2)
        meta["decupado"] = bool(dur_final < (fim - ini) - 0.01)
        # Guarda a URL AQUI, não só no _origem.json do lote — post.json é o
        # arquivo que sobrevive em qualquer cópia/organização do clipe
        # (Drive, Desktop, etc). Perder a URL de origem já aconteceu (vídeo
        # do Geoffrey Hinton, 26/07/2026) porque _origem.json não é sempre
        # escrito. Redundância aqui evita repetir.
        meta["url_origem"] = url_origem or ""
        (pasta / "post.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (pasta / "post.txt").write_text(_legenda(c), encoding="utf-8")
        resumo.append(meta)

        # Limpa os intermediários DESTE clipe assim que ele termina — sem
        # isso, tudo (bruto, versão enxuta, estabilizada, áudio, faixa
        # dublada) fica acumulando em disco até o fim do lote inteiro, e um
        # runner do GitHub Actions (só ~14GB livres) estoura "No space left
        # on device" no meio de um vídeo com --dublar e vários clipes
        # (medido em 04/08/2026, run 30899785124, quebrou no clipe 2 de 10).
        if not manter_temp:
            for padrao in (f"bruto_{i:02d}*.mp4", f"clip_{i:02d}.flac",
                          f"v_{i:02d}.ass", f"h_{i:02d}.ass"):
                for f in config.TRABALHO.glob(padrao):
                    f.unlink(missing_ok=True)
            dub_dir = config.TRABALHO / f"dub_{i:02d}"
            if dub_dir.is_dir():
                shutil.rmtree(dub_dir, ignore_errors=True)

    (destino / "_resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    # Legendas de todos os clipes num arquivo só. O rascunho do TikTok NÃO
    # carrega legenda (a API de inbox só aceita o arquivo de vídeo), então o
    # usuário digita/cola na mão no celular — juntar tudo aqui evita abrir
    # pasta por pasta.
    (destino / "LEGENDAS.txt").write_text(
        "\n\n".join(
            f"{'='*60}\n[{i:02d}] nota {m.get('nota')}  "
            f"({m.get('duracao_s')}s)\n{'='*60}\n{_legenda(m)}"
            for i, m in enumerate(resumo, 1)
        ),
        encoding="utf-8")
    if url_origem:
        (destino / "_origem.json").write_text(
            json.dumps({"url": url_origem}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[5/5] pronto em {(time.time()-t0)/60:.1f} min → {destino}")
    if url_origem:
        status.marcar_item(url_origem, "concluido", pasta=str(destino),
                           concluido_em=time.time())
    status.ocioso()
    return destino


def main():
    p = argparse.ArgumentParser(description="Vídeo longo -> Shorts prontos")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="link do YouTube/etc")
    g.add_argument("--arquivo", help="vídeo já no disco")
    p.add_argument("--qtd", type=int, default=config.QTD_CLIPES)
    p.add_argument("--so-audio", action="store_true",
                   help="Gemini analisa só o áudio: mais barato, mas não vê a cena")
    p.add_argument("--com-horizontal", action="store_true",
                   help="também renderiza o 16:9 tela cheia. Padrão é só o 9:16: "
                        "o destino agora é TikTok, que é vertical-first — "
                        "horizontal lá tem desempenho ruim e o render dobrava o tempo")
    p.add_argument("--idioma", default="pt", help="idioma da fala (pt, en, es...)")
    p.add_argument("--sem-traducao", action="store_true",
                   help="mantém a legenda no idioma original (--idioma), sem traduzir pra pt-BR")
    p.add_argument("--dublar", action="store_true",
                   help="troca o áudio original por voz pt-BR (edge-tts) + legenda traduzida")
    p.add_argument("--fala-literal", action="store_true",
                   help="só com --dublar: dubla o que a pessoa REALMENTE está falando "
                        "(tradução literal), em vez do padrão do canal (narrador contando "
                        "o contexto). Use pra entrevistas onde a fala em si é o valor "
                        "editorial (declarações, posições) — não é o padrão, é exceção "
                        "pontual por pedido.")
    p.add_argument("--recorte", metavar="INICIO-FIM",
                   help="corta um trecho exato em segundos (ex: 113.4-162.9) em vez de "
                        "deixar o Gemini escolher. Pula a checagem de congelamento — "
                        "use pra refazer um corte que você já sabe que funciona")
    p.add_argument("--manter-temp", action="store_true")
    p.add_argument("--estilo-legenda", type=int, choices=(1, 2), default=1,
                   help="1 = padrão do canal (Inter Black, corpo fixo). "
                        "2 = réplica da referência Erica Bruno (Poppins Bold, "
                        "corpo variável — ver engine/legendas.py)")
    a = p.parse_args()

    recorte = None
    if a.recorte:
        try:
            ini_s, fim_s = (float(x) for x in a.recorte.split("-", 1))
        except ValueError:
            p.error("--recorte precisa ser INICIO-FIM em segundos, ex: 113.4-162.9")
        recorte = (ini_s, fim_s)

    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b):
            sys.exit(f"'{b}' não encontrado no PATH. Rode: .\\setup_nitro5.ps1")

    # Cota do Gemini ANTES de gastar runner: a tradução só acontece no fim do
    # pipeline, então uma cota zerada custava ~1h de processamento por vídeo
    # antes de aparecer (runs #123-126 de 08/08/2026 morreram assim).
    if not a.sem_traducao:
        try:
            traducao.checar_disponibilidade()
        except Exception as e:
            sys.exit(f"tradução indisponível: {e}\n"
                     "Cota do Gemini provavelmente zerada — o run morreria só no fim, "
                     "depois de baixar, narrar e renderizar. Espere o reset diário ou "
                     "use --sem-traducao pra manter a legenda no idioma original.")

    if a.url:
        if not shutil.which("yt-dlp"):
            sys.exit("yt-dlp não encontrado. Rode: .\\setup_nitro5.ps1")
        print("baixando...")
        status.etapa(a.url, "baixando")
        status.marcar_item(a.url, "processando", iniciado_em=time.time())
        fonte = midia.baixar(a.url, config.TRABALHO / "download")
    else:
        fonte = Path(a.arquivo)
        if not fonte.exists():
            sys.exit(f"não encontrei: {fonte}")

    try:
        processar(fonte, a.qtd, not a.so_audio, a.idioma, not a.com_horizontal,
                  traduzir=not a.sem_traducao, dublar=a.dublar,
                  url_origem=a.url or "", recorte=recorte,
                  estilo_legenda=a.estilo_legenda, manter_temp=a.manter_temp,
                  fala_literal=a.fala_literal)
    finally:
        if not a.manter_temp and config.TRABALHO.exists():
            shutil.rmtree(config.TRABALHO, ignore_errors=True)
        status.ocioso()


if __name__ == "__main__":
    main()
