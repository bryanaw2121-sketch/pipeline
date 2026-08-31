"""Rotação de chaves. Você tem 8 de cada; usar uma só é desperdício."""
import os, itertools, threading
from dotenv import load_dotenv

load_dotenv()


class Rotador:
    """Distribui chamadas entre as chaves e aposenta as que estouraram quota."""

    def __init__(self, prefixo: str):
        chaves = []
        if v := os.getenv(prefixo):
            chaves.append(v.strip())
    # ⚠️ O TETO E' O NUMERO DE SLOTS QUE O RODIZIO ENXERGA, e ele ja' cortou
    # chave viva: em 31/08/2026 os pools dos dois motores foram unificados
    # (ordem do Bryan, "todas rodam para todos") e a cozinha passou a ter o
    # slot 21 — que `range(2, 21)` NAO lia. A chave existia no repositorio,
    # aparecia na listagem de secrets, e nunca entrava no rodizio.
    #
    # Ao acrescentar chave alem deste teto, suba o numero aqui TAMBEM.
    for i in range(2, 41):
            if v := os.getenv(f"{prefixo}_{i}"):
                chaves.append(v.strip())
        if not chaves:
            raise RuntimeError(
                f"Nenhuma chave {prefixo} encontrada. Copie .env.sample para .env."
            )
        self.prefixo = prefixo
        self.todas = chaves
        self._ciclo = itertools.cycle(chaves)
        self._queimadas: set[str] = set()
        self._trava = threading.Lock()

    def __len__(self):
        return len(self.todas)

    def proxima(self) -> str:
        with self._trava:
            vivas = [k for k in self.todas if k not in self._queimadas]
            if not vivas:
                # todas estouraram: zera e tenta de novo (quota costuma
                # ser por minuto, então esperar já resolve)
                self._queimadas.clear()
                vivas = self.todas
            for _ in range(len(self.todas) * 2):
                k = next(self._ciclo)
                if k not in self._queimadas:
                    return k
            return vivas[0]

    def queimar(self, chave: str):
        """Marca a chave como sem quota; ela sai do rodízio."""
        with self._trava:
            self._queimadas.add(chave)
            restam = len(self.todas) - len(self._queimadas)
            print(f"   [!] chave {self.prefixo} sem quota ({restam} restantes)")


GEMINI = None
GROQ = None
NVIDIA = None
OPENROUTER = None


def gemini() -> Rotador:
    global GEMINI
    if GEMINI is None:
        GEMINI = Rotador("GEMINI_API_KEY")
    return GEMINI


def groq() -> Rotador:
    global GROQ
    if GROQ is None:
        GROQ = Rotador("GROQ_API_KEY")
    return GROQ


def nvidia() -> Rotador:
    """Nemotron pela API da NVIDIA (integrate.api.nvidia.com).
    Serve de reserva quando a cota do Gemini estoura."""
    global NVIDIA
    if NVIDIA is None:
        NVIDIA = Rotador("NVIDIA_API_KEY")
    return NVIDIA


def openrouter() -> Rotador:
    """OpenRouter. Os modelos `:free` têm teto DIÁRIO por chave —
    ao bater, só volta no dia seguinte, rodízio não resolve."""
    global OPENROUTER
    if OPENROUTER is None:
        OPENROUTER = Rotador("OPENROUTER_API_KEY")
    return OPENROUTER
