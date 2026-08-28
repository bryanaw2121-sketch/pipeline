"""Gera .ass com efeito karaokê (palavra acende conforme é falada) e
destaque de palavra por grupo (ver engine/destaque.py).
"""
import itertools
import os
from pathlib import Path

from . import destaque as _destaque

MAX_LINHA = 3          # palavras por tela — Shorts pede pouco texto e grande
BASE = "&H00FFFFFF"      # branco

# Paleta do destaque de palavra — girada por grupo, na ordem abaixo.
# Valores em BGR (formato de override do ASS, "&HBBGGRR&"), sem rosa: pedido
# do Bryan em 02/08/2026 foi mapear a referência (rosa/vermelho/azul) para
# azul/verde/vermelho, mantendo vermelho como vermelho.
_AZUL = "&HFF9900&"       # RGB(0,153,255)
_VERDE = "&H76E600&"      # RGB(0,230,118)
_VERMELHO = "&H303BFF&"   # RGB(255,59,48)
PALETA = (_AZUL, _VERDE, _VERMELHO)

# Cor por SENTIDO da palavra, não por rotação (pedido do Bryan em 26/08/2026).
# Quem decide qual é qual é o Gemini, em engine/destaque.py — aqui só traduz o
# nome pra cor do ASS.
POR_NOME = {"vermelho": _VERMELHO, "azul": _AZUL, "verde": _VERDE}
_RESET = "&HFFFFFF&"      # branco, pra voltar depois da palavra destacada

# Estilo 1 = o que o canal já usava até 02/08/2026 (Inter Black, corpo fixo).
# Estilo 2 = pedido do Bryan em 02/08/2026: réplica da referência (Erica
# Bruno) — mesma fonte do card de título (Poppins Bold, engine/render.py),
# mesmo esquema de cor do destaque (idêntico ao estilo 1, já bate com a
# referência), e a dinâmica de tamanho variável entre grupos (a "linha de
# cima" às vezes maior que a de baixo). Não dá pra saber ao certo QUAL grupo
# ela aumenta — a regra escolhida aqui é: o grupo que tem palavra destacada
# (mais "peso" na frase) cresce, o resto fica no tamanho normal. Reaproveita
# o mesmo destaque.marcar() já chamado, sem gasto extra de API.
FONTE_ESTILO_2 = "Poppins Bold"
_ESTILO_2_CRESCE = 1.22   # corpo do grupo COM destaque
_ESTILO_2_NORMAL = 0.90   # corpo do grupo SEM destaque
# Bryan (02/08/2026, olhando o teste): "não tá igual", "tem um sombreado
# também", "sombreado meio esfumaçado" — o \shad do ASS é sombra DURA
# (silhueta sólida deslocada), a referência tem sombra com borda suave. \be
# (blur edges) desfoca contorno E sombra juntos — é o jeito do ASS chegar
# perto de "esfumaçado" sem precisar pré-renderizar em PIL feito o título.
#
# BUG achado depois de 3 rodadas de teste sem sombra visível nenhuma: o byte
# de alfa do ASS é INVERTIDO do que parece óbvio — 00 é OPACO, FF é
# TRANSPARENTE. BackColour estava em &H80000000 (~50% transparente, quase
# some) achando que era "bem visível". Confirmado isolado num fundo cinza
# antes de mexer no vídeo de verdade: com &H00000000 (opaco) a sombra
# esfumaçada aparece de vez.
#
# 2ª correção no mesmo dia: o \shad do ASS desloca a sombra pra
# baixo-direita (silhueta duplicada, não um halo). Bryan queria o efeito
# ENVOLVENDO a letra inteira, não puxado pra um lado. Solução: SHADOW=0 (sem
# deslocamento) e o halo vem do próprio CONTORNO borrado por \be.
#
# 3ª correção: comparando com a referência lado a lado, ela não é borrada
# por igual — a borda BEM colada na letra é nítida, só a parte mais externa
# desfoca (gradiente nítido→difuso). Um \be só não faz isso: ele borra tudo
# junto por igual. Precisa de DUAS camadas desenhadas na mesma posição:
# uma sombra preta grossa e borrada por trás (Layer 0), e o texto de
# verdade por cima, com contorno fino e SEM blur (Layer 1) — a parte da
# sombra que fica embaixo do texto nítido não aparece, só a franja borrada
# que sobra pra fora do contorno fino.
_ESTILO_2_BLUR = 4.5
_PRETO = "&H00000000"   # opaco — ver bug do alfa acima


def _t(seg: float) -> str:
    seg = max(0.0, seg)
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def escrever(palavras: list[dict], destino: Path, largura: int, altura: int,
             estilo: int = 1) -> Path | None:
    """Cria o arquivo .ass. Devolve None se não houver o que legendar.

    `estilo`: 1 = padrão do canal (Inter Black, corpo fixo). 2 = réplica da
    referência (Poppins Bold, corpo variável — ver FONTE_ESTILO_2 acima)."""
    if not palavras:
        return None

    # fonte proporcional à altura: mesma leitura em 9:16 e 16:9. Menor que
    # antes e com margem lateral generosa — texto fica num bloco central,
    # nunca encosta na borda mesmo em frase mais longa.
    corpo = max(22, int(altura * 0.038))
    fontname = FONTE_ESTILO_2 if estilo == 2 else "Inter Black"
    # LEGENDA_MARGEM_V_FRAC: override pontual pra vídeo específico com algo
    # cobrindo a legenda na posição normal (ex: caixa branca de UI na fonte).
    #
    # Padrão subiu de 0.18 para 0.30 em 28/07/2026: a 18% da base a legenda
    # cai justamente na faixa que a UI do TikTok ocupa — nome do perfil,
    # curtir, comentar, compartilhar. O corpus recomenda o texto
    # ligeiramente acima do centro (PLAYBOOK §5). Legenda escondida atrás
    # de botão não é lida, e legenda é uma das 3 camadas de edição que
    # sustentam o RPM.
    frac_v = float(os.environ.get("LEGENDA_MARGEM_V_FRAC", "0.30"))
    margem_v = int(altura * frac_v)   # sobe o texto: no Shorts a UI cobre a base
    margem_lat = int(largura * 0.12)
    # Estilo 1: contorno único, sem sombra à parte (como sempre foi).
    # Estilo 2: contorno FINO e nítido na camada de cima (Style K) — a
    # sombra borrada vem de uma camada separada atrás (Style S), mais grossa
    # de propósito pra sobrar franja borrada pra fora do contorno nítido.
    contorno = max(2, corpo // (24 if estilo == 2 else 14))
    contorno_sombra = max(3, corpo // 6)
    sombra = 0 if estilo == 2 else 2
    cor_sombra = "&H80000000"   # só usado no estilo 1

    estilo_s = ""
    if estilo == 2:
        estilo_s = (f"\nStyle: S,{fontname},{corpo},{_PRETO},{_PRETO},{_PRETO},"
                    f"{_PRETO},-1,0,0,0,100,100,0,0,1,{contorno_sombra},0,2,"
                    f"{margem_lat},{margem_lat},{margem_v},1")

    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: K,{fontname},{corpo},{BASE},{BASE},&H00000000,{cor_sombra},-1,0,0,0,100,100,0,0,1,{contorno},{sombra},2,{margem_lat},{margem_lat},{margem_v},1{estilo_s}

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    grupos = [palavras[i:i + MAX_LINHA] for i in range(0, len(palavras), MAX_LINHA)]
    destaques = _destaque.marcar(grupos)

    linhas = []
    for grupo, (idx_destaque, nome_cor) in zip(grupos, destaques):
        ini, fim = grupo[0]["inicio"], grupo[-1]["fim"]
        if fim <= ini:
            fim = ini + 0.4
        cor = POR_NOME.get(nome_cor or "", _VERDE) if idx_destaque is not None else None

        # Estilo 2: o grupo inteiro cresce ou encolhe conforme tem ou não
        # destaque — é a dinâmica de "linha de cima às vezes maior" da
        # referência. \fs é override de tamanho por trecho de texto do ASS;
        # vai uma vez no início da linha, vale pro resto dela.
        fs_override = ""
        if estilo == 2:
            fator = _ESTILO_2_CRESCE if idx_destaque is not None else _ESTILO_2_NORMAL
            fs_override = f"\\fs{round(corpo * fator)}"

        # \k usa centésimos de segundo
        partes = [f"{{{fs_override}}}"] if fs_override else []
        for j, p in enumerate(grupo):
            dur = max(1, int((p["fim"] - p["inicio"]) * 100))
            palavra = p["palavra"].upper()
            if j == idx_destaque:
                partes.append(f"{{\\k{dur}\\c{cor}}}{palavra} {{\\c{_RESET}}}")
            else:
                partes.append(f"{{\\k{dur}}}{palavra} ")
        texto = "".join(partes).strip()
        linhas.append(f"Dialogue: 1,{_t(ini)},{_t(fim)},K,,0,0,0,,{texto}")

        if estilo == 2:
            # Camada de sombra, MESMO texto (sem cor — só a silhueta borrada
            # importa), Layer 0 = desenhada ATRÁS da camada nítida acima.
            palavras_planas = " ".join(p["palavra"].upper() for p in grupo)
            texto_sombra = f"{{{fs_override}\\be{_ESTILO_2_BLUR}}}{palavras_planas}"
            linhas.append(f"Dialogue: 0,{_t(ini)},{_t(fim)},S,,0,0,0,,{texto_sombra}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")
    return destino
