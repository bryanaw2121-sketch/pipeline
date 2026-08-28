"""Face tracking: decide POR ONDE o quadro 9:16 passeia no vídeo 16:9.

Sem isso o crop vertical fica fixo no centro e corta a cabeça de quem está
falando de lado. Roda em CPU numa boa (MediaPipe é leve).
"""
import config

MAX_DEGRAUS = 60   # teto de mudanças de enquadramento por clipe


def _suavizar(pontos: list[float], alfa: float) -> list[float]:
    """Média exponencial nos dois sentidos: tira o tremor sem atrasar o
    movimento (só um sentido faria o quadro correr atrás do rosto)."""
    if not pontos:
        return []
    ida = [pontos[0]]
    for p in pontos[1:]:
        ida.append(alfa * ida[-1] + (1 - alfa) * p)
    volta = [ida[-1]]
    for p in reversed(ida[:-1]):
        volta.append(alfa * volta[-1] + (1 - alfa) * p)
    return list(reversed(volta))


MODELO_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
              "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")
MODELO = config.RAIZ / "modelos" / "blaze_face_short_range.tflite"


def _garantir_modelo():
    """O MediaPipe Tasks não embute o modelo: precisa do .tflite em disco.
    São ~230 KB, então baixar na primeira vez sai barato e o arquivo fica
    em cache — no runner do Actions isso acontece uma vez por execução."""
    if MODELO.exists() and MODELO.stat().st_size > 0:
        return True
    try:
        import urllib.request
        MODELO.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODELO_URL, MODELO)
        return MODELO.stat().st_size > 0
    except Exception as e:
        print(f"   [!] não consegui baixar o modelo de rosto ({e})")
        return False


def trajetoria(clipe, largura: int, altura: int) -> list[tuple[float, float]]:
    """Devolve [(tempo, x_centro)] normalizado 0..1. Vazio = usa o centro."""
    # mp.solutions saiu no MediaPipe 1.0 — o caminho atual é o Tasks API.
    # Diferenças que importam aqui: o modelo vem de arquivo, e a bounding box
    # volta em PIXELS (a antiga vinha normalizada 0..1).
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as e:
        print(f"   [!] face tracking indisponível ({e}) — crop fixo no centro")
        return []

    if not _garantir_modelo():
        print("   [!] face tracking sem modelo — crop fixo no centro")
        return []

    try:
        det = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODELO)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.5,
        ))
    except Exception as e:
        print(f"   [!] face tracking indisponível ({e}) — crop fixo no centro")
        return []

    cap = cv2.VideoCapture(str(clipe))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    salto = max(1, int(round(fps / config.AMOSTRA_FPS)))

    tempos, xs = [], []
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % salto == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                # detect_for_video exige timestamp crescente em ms
                res = det.detect_for_video(imagem, int(idx / fps * 1000))
                if res.detections:
                    # com várias faces, segue a maior (quem está em primeiro plano)
                    d = max(res.detections, key=lambda x: x.bounding_box.width)
                    bb = d.bounding_box
                    largura_frame = frame.shape[1] or 1
                    centro = (bb.origin_x + bb.width / 2) / largura_frame
                    xs.append(min(1.0, max(0.0, centro)))
                    tempos.append(idx / fps)
            idx += 1
    finally:
        cap.release()
        det.close()

    if len(xs) < 3:
        return []
    return list(zip(tempos, _suavizar(xs, config.SUAVIZACAO)))


def filtro_vertical(largura: int, altura: int,
                    caminho: list[tuple[float, float]]) -> str:
    """Monta o filtro ffmpeg do crop 9:16 seguindo o rosto."""
    alvo_l = int(altura * 9 / 16)          # largura da janela vertical
    if alvo_l >= largura:
        # fonte já é estreita: só escala e preenche as bordas
        lv, av = config.VERTICAL
        return (f"scale={lv}:-2,pad={lv}:{av}:(ow-iw)/2:(oh-ih)/2:black")

    max_x = largura - alvo_l
    if not caminho:
        expr = f"{max_x // 2}"
    else:
        # Converte a trajetória em degraus (tempo -> x em pixels), descartando
        # variações pequenas: encurta muito a expressão e ainda tira tremor.
        # Sobe o limiar até caber num número seguro de degraus: expressão
        # muito longa deixa o parser do ffmpeg lento e frágil.
        pixels = [(t, int(min(max_x, max(0, xn * largura - alvo_l / 2))))
                  for t, xn in caminho]
        limiar = max(8, alvo_l // 60)
        while True:
            degraus: list[tuple[float, int]] = []
            for t, x in pixels:
                if not degraus or abs(x - degraus[-1][1]) >= limiar:
                    degraus.append((t, x))
            if len(degraus) <= MAX_DEGRAUS or limiar > alvo_l:
                break
            limiar = int(limiar * 1.5) + 1

        # INTERPOLA entre os degraus em vez de saltar de um pro outro.
        #
        # Antes isto era uma função degrau — if(lt(t,corte), x1, x2) — e o
        # recorte ficava imóvel e PULAVA no instante do corte, no mínimo
        # `limiar` pixels de um frame pro outro. Era o "microtravadas" que o
        # usuário viu nos clipes de 28/07: o _suavizar() acima produzia uma
        # curva suave e a quantização a destruía logo em seguida.
        #
        # Agora cada trecho vira uma rampa linear entre (t_i, x_i) e
        # (t_i+1, x_i+1), então o movimento é contínuo. A expressão fica mais
        # longa, mas o teto de MAX_DEGRAUS continua segurando o tamanho.
        if len(degraus) == 1:
            expr = f"{degraus[0][1]}"
        else:
            # Depois do último degrau o valor congela — não há pra onde ir.
            expr = f"{degraus[-1][1]}"
            for i in range(len(degraus) - 2, -1, -1):
                t0, x0 = degraus[i]
                t1, x1 = degraus[i + 1]
                dt = max(1e-3, t1 - t0)          # nunca divide por zero
                rampa = f"({x0}+({x1 - x0})*(t-{t0:.2f})/{dt:.3f})"
                expr = f"if(lt(t,{t1:.2f}),{rampa},{expr})"

    lv, av = config.VERTICAL
    return f"crop={alvo_l}:{altura}:'{expr}':0,scale={lv}:{av}"
