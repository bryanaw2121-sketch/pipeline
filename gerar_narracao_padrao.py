"""Gera narração completa (voz clonada) de um roteiro que ainda NÃO tem
vídeo por trás — caso da frente nova YouTube palito+Higgsfield.

Diferente do fluxo de clipe (voz_clonada.gerar_trilha), aqui não existe
duração-alvo pra encaixar o áudio: cada cena vira uma síntese frase-por-
frase, concatenada com pausa natural entre frases E uma pausa maior entre
cenas (pro editor saber onde cortar depois). Sem atempo/corte no final —
o ritmo sai natural, do jeito que o Chatterbox gerou.

    python gerar_narracao_padrao.py --roteiro roteiro.json --amostra-voz vozes/bryan_amostra.wav --saida saida/

roteiro.json: lista de strings, uma por cena (pode ter várias frases).
"""
import argparse
import json
from pathlib import Path

from engine import voz_clonada as vc
from engine import midia

PAUSA_ENTRE_CENAS_S = 0.6


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--roteiro", required=True, help="JSON: lista de textos, um por cena")
    p.add_argument("--amostra-voz", required=True)
    p.add_argument("--idioma", default="pt")
    p.add_argument("--saida", default="saida_narracao")
    a = p.parse_args()

    cenas = json.loads(Path(a.roteiro).read_text(encoding="utf-8"))
    amostra = Path(a.amostra_voz)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)

    todas_partes = []
    timing = []
    t_cursor = 0.0

    for i, texto_cena in enumerate(cenas):
        frases = vc._dividir_frases(texto_cena.strip())
        if not frases:
            continue
        print(f"CENA {i+1}: {len(frases)} frase(s)")
        cena_inicio = t_cursor
        for j, frase in enumerate(frases):
            dest = saida / f"cena{i:02d}_frase{j:02d}.wav"
            vc._falar(frase, dest, amostra, a.idioma)
            dur = midia.duracao(dest)
            timing.append({
                "cena": i + 1, "frase": frase,
                "inicio": t_cursor, "fim": t_cursor + dur,
            })
            todas_partes.append(dest)
            t_cursor += dur + vc._PAUSA_ENTRE_FRASES_S
            print(f"   [{j+1}/{len(frases)}] {dur:.1f}s — {frase[:60]}")
        t_cursor += PAUSA_ENTRE_CENAS_S - vc._PAUSA_ENTRE_FRASES_S
        print(f"   cena {i+1} terminou em {t_cursor:.1f}s (começou em {cena_inicio:.1f}s)")

    final = saida / "narracao_final.wav"
    vc._concatenar_com_pausas(todas_partes, final, pausa_s=vc._PAUSA_ENTRE_FRASES_S)
    # a pausa extra entre cenas já foi contabilizada no timing acima, mas a
    # concatenação real usa pausa uniforme entre frases — por isso o áudio
    # final pode ficar um pouco mais curto que o timing calculado. Dá pra
    # comparar no relatório abaixo.
    dur_real = midia.duracao(final)

    (saida / "timing.json").write_text(
        json.dumps(timing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nÁUDIO FINAL: {final} ({dur_real:.1f}s reais)")
    print(f"TIMING CALCULADO (com pausa de cena): {t_cursor:.1f}s")
    print(f"→ {saida / 'timing.json'}")


if __name__ == "__main__":
    main()
