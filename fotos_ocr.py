# -*- coding: utf-8 -*-
"""Mede cada foto de anuncio: quanto texto tem, e se e' o mesmo produto da principal.

Roda na NUVEM (`.github/workflows/fotos_ocr.yml`), nunca na maquina do dono.
Entrada por ambiente: PREFIXO (comum a todas as URLs) e LISTA (JSON
{id: [sufixos]}, o primeiro de cada lista e' a foto principal).
Saida: `fotos_ocr.json` = {url_completa: {"texto": 0.0-1.0, "palavras": n,
"fid": cosseno contra a principal do mesmo id}}.

⚠️ FALHA POR FOTO, NUNCA POR LOTE. Foto que nao baixa ou nao decodifica sai
com {"erro": "..."} e as outras seguem: o publicador trata ausencia como
"nao medi" e fica com a principal.

⚠️ `texto` e' a AREA das caixas do OCR sobre a area da imagem, com
confianca >= 0,3. Texto impresso no produto (logo "Lenovo" no fone) conta
tambem — nao ha' como separar sem entender a cena. Por isso o publicador
compara fotos DO MESMO anuncio entre si, e nao contra um limiar absoluto.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

import numpy as np
import requests
from PIL import Image

LADO = 640
CONF_MIN = 0.3
UA = {"User-Agent": "Mozilla/5.0"}


def baixar(url: str) -> Image.Image:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    im.thumbnail((LADO, LADO))
    return im


def area_poligono(pts) -> float:
    x = [p[0] for p in pts]
    y = [p[1] for p in pts]
    return 0.5 * abs(sum(x[i] * y[(i + 1) % len(pts)] - x[(i + 1) % len(pts)] * y[i]
                         for i in range(len(pts))))


def main() -> None:
    prefixo = os.environ["PREFIXO"]
    lista = json.loads(os.environ["LISTA"])
    total = sum(len(v) for v in lista.values())
    print(f"{len(lista)} anuncios, {total} fotos")

    import easyocr
    import open_clip
    import torch
    leitor = easyocr.Reader(["pt", "en"], gpu=False, verbose=False)
    modelo, _, pre = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k")
    modelo.eval()

    def clip(im: Image.Image) -> np.ndarray:
        with torch.no_grad():
            v = modelo.encode_image(pre(im).unsqueeze(0))[0].float().numpy()
        return v / (np.linalg.norm(v) or 1.0)

    saida: dict[str, dict] = {}
    t0 = time.time()
    feitas = 0
    for pid, sufixos in lista.items():
        principal_v = None
        for i, suf in enumerate(sufixos):
            url = prefixo + suf
            try:
                im = baixar(url)
                w, h = im.size
                caixas = leitor.readtext(np.array(im))
                area = sum(area_poligono(c[0]) for c in caixas if c[2] >= CONF_MIN)
                palavras = sum(1 for c in caixas if c[2] >= CONF_MIN)
                v = clip(im)
                if i == 0:
                    principal_v = v
                fid = float(v @ principal_v) if principal_v is not None else None
                saida[url] = {"texto": round(min(1.0, area / (w * h)), 4),
                              "palavras": palavras,
                              "fid": round(fid, 4) if fid is not None else None}
            except Exception as e:  # noqa: BLE001 — falha por foto, ver cabecalho
                saida[url] = {"erro": f"{type(e).__name__}: {str(e)[:80]}"}
            feitas += 1
            if feitas % 50 == 0:
                print(f"  {feitas}/{total} em {time.time() - t0:.0f}s", flush=True)
    erros = sum(1 for v in saida.values() if "erro" in v)
    print(f"{len(saida)} medidas, {erros} com erro, {time.time() - t0:.0f}s")
    with open("fotos_ocr.json", "w", encoding="utf-8") as fh:
        json.dump(saida, fh, ensure_ascii=False)
    if erros == len(saida):
        sys.exit("todas as fotos falharam — nada a entregar")


if __name__ == "__main__":
    main()
