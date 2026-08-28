"""Geração de imagem via Pollinations (image.pollinations.ai) — grátis, sem
chave de API. Testado em 03/08/2026: modelo "flux" dá resultado cinematográfico
consistente (ver teste_imagens_ia/pollinations_1..3.png), embora só "sana"
apareça hoje em /models — "flux" continua respondendo 200, mantido aqui como
padrão, mas trocável caso pare de funcionar sem aviso (serviço sem contrato).

Tamanho: usa config.VERTICAL (1080x1920) por padrão. ATENÇÃO (medido em
03/08/2026): o Pollinations respeita a PROPORÇÃO 9:16 pedida, mas às vezes
devolve um arquivo menor (ex: pedido 1080x1920, veio 576x1024) — por isso
`gerar()` sempre reamplia com PIL pro tamanho exato no final, garantido.

Estrutura de prompt: pesquisa (03/08/2026, guia de prompt do Flux 2) recomenda
montar o prompt em blocos fixos — Assunto + Cena + Estilo + Iluminação +
Câmera/Lente + Detalhe — em vez de um parágrafo solto. `montar_prompt()` monta
isso. Evitar detalhe não-visual (ex: "pássaros cantando ao fundo") — o modelo
não tem como desenhar som, só desperdiça tokens de atenção.
"""
import time
import urllib.parse
from pathlib import Path

import config

URL_BASE = "https://image.pollinations.ai/prompt"
MODELO_PADRAO = "flux"


def montar_prompt(assunto: str, cena: str, estilo: str, iluminacao: str,
                   camera: str, detalhe: str = "") -> str:
    """Monta o prompt na estrutura recomendada pro Flux: Assunto + Cena +
    Estilo + Iluminação + Câmera/Lente + Detalhe. Cada parte deve ser só o
    que dá pra DESENHAR — nada de som, cheiro ou conceito abstrato."""
    partes = [assunto, cena, estilo, iluminacao, camera, detalhe]
    return ", ".join(p.strip() for p in partes if p.strip())


def gerar(prompt: str, destino: Path, *,
          largura: int = config.VERTICAL[0], altura: int = config.VERTICAL[1],
          modelo: str = MODELO_PADRAO, seed: int | None = None,
          negativo: str | None = None, tentativas: int = 4) -> Path:
    """Gera 1 imagem a partir do prompt e salva em `destino`, já no tamanho
    certo pro Short (config.VERTICAL). Levanta RuntimeError se todas as
    tentativas falharem.

    `negativo`: suporte incerto (a API não documenta o parâmetro
    oficialmente, mas aceita sem erro) — usar como bônus, não depender dele.
    """
    import requests

    params = {
        "width": largura,
        "height": altura,
        "model": modelo,
        "nologo": "true",
    }
    if seed is not None:
        params["seed"] = seed
    if negativo:
        params["negative_prompt"] = negativo

    url = f"{URL_BASE}/{urllib.parse.quote(prompt)}?{urllib.parse.urlencode(params)}"

    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/"):
                raise RuntimeError(f"resposta não é imagem: {r.headers.get('content-type')}")
            destino.write_bytes(r.content)
            _garantir_tamanho(destino, largura, altura)
            return destino
        except Exception as e:
            ultimo_erro = e
            time.sleep(2 * (tentativa + 1))

    raise RuntimeError(f"geração de imagem falhou após {tentativas} tentativas: {ultimo_erro}")


def _garantir_tamanho(caminho: Path, largura: int, altura: int) -> None:
    """O Pollinations às vezes devolve menor que o pedido (proporção certa,
    pixels menores) — reamplia pro tamanho exato, sobrescrevendo o arquivo."""
    from PIL import Image
    img = Image.open(caminho)
    if img.size != (largura, altura):
        img = img.resize((largura, altura), Image.LANCZOS)
        img.save(caminho)
