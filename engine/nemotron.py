"""Cliente Nemotron (NVIDIA build API), com rodízio de chaves.

Existe porque a cota diária do Gemini estoura em trabalho de lote pesado
(destilação de corpus). O Nemotron Ultra tem 512k de contexto e aguenta
lote grande.

Pegadinhas que já custaram tempo, todas tratadas aqui:
1. São modelos de RACIOCÍNIO: se `max_tokens` for baixo, o modelo gasta
   tudo pensando e devolve `content: null` com `finish_reason: length`.
   Por isso o mínimo é alto.
2. `503 ResourceExhausted: Worker local total request limit reached` é
   capacidade transitória do servidor, NÃO chave sem cota — retentar em
   outra chave resolve, não adianta queimar a chave.
"""
import json
import time

import requests

from . import keys

URL = "https://integrate.api.nvidia.com/v1/chat/completions"

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"      # 512k ctx, o mais forte
SUPER = "nvidia/nemotron-3-super-120b-a12b"      # mais rápido
PADRAO = ULTRA


def conversar(prompt: str, *, modelo: str = PADRAO, temperatura: float = 0.2,
              max_tokens: int = 16000, json_mode: bool = False,
              tentativas: int = 12, timeout: int = 900) -> str:
    """Manda um prompt e devolve o texto da resposta.

    json_mode=True pede JSON explicitamente (o modelo não tem um flag
    nativo confiável, então reforçamos na instrução e limpamos cercas).
    """
    rot = keys.nvidia()
    msgs = []
    if json_mode:
        msgs.append({"role": "system",
                     "content": "Responda SEMPRE com JSON válido e nada mais. "
                                "Sem texto antes ou depois, sem cercas markdown."})
    msgs.append({"role": "user", "content": prompt})

    ultimo = None
    for _ in range(tentativas):
        chave = rot.proxima()
        try:
            r = requests.post(
                URL,
                headers={"Authorization": f"Bearer {chave}"},
                json={"model": modelo, "messages": msgs,
                      "temperature": temperatura, "max_tokens": max_tokens},
                timeout=timeout,
            )
            if r.status_code == 429:
                rot.queimar(chave)
                continue
            if r.status_code in (500, 502, 503, 504):
                # capacidade do servidor, não da chave
                time.sleep(4)
                continue
            r.raise_for_status()
            esc = r.json()["choices"][0]
            txt = esc["message"].get("content")
            if not txt:
                # gastou tudo raciocinando: pede mais espaço e tenta de novo
                if esc.get("finish_reason") == "length":
                    max_tokens = min(int(max_tokens * 1.8), 60000)
                continue
            return txt.strip()
        except Exception as e:                          # noqa: BLE001
            ultimo = e
            time.sleep(3)
    raise RuntimeError(f"Nemotron falhou após {tentativas} tentativas: {ultimo}")


def _limpar_cerca(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def json_de(prompt: str, **kw) -> dict:
    """Igual a conversar(), mas devolve dict já parseado."""
    bruto = conversar(prompt, json_mode=True, **kw)
    limpo = _limpar_cerca(bruto)
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        # às vezes vem prosa em volta; pega do 1º { ao último }
        i, f = limpo.find("{"), limpo.rfind("}")
        if i >= 0 and f > i:
            return json.loads(limpo[i:f + 1])
        raise
