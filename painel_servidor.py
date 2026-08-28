"""Servidor local só pra servir o painel (painel/index.html) e os JSONs de
estado (estado/status.json, estado/fila_atual.json). Sem framework, só
http.server da biblioteca padrão — não precisa instalar nada.

    python painel_servidor.py
    (abre sozinho http://localhost:8787)
"""
import http.server
import socketserver
import webbrowser
from pathlib import Path

import config
from engine import status

PORTA = 8787
RAIZ_SERVIDA = config.RAIZ


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(RAIZ_SERVIDA), **kw)

    def end_headers(self):
        # os JSONs de estado mudam a todo momento; sem isso o navegador
        # cacheia e o painel para de atualizar
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # silencioso, senão o terminal enche de linha de log a cada poll


def main():
    (config.RAIZ / "estado").mkdir(parents=True, exist_ok=True)
    contas = status.contas_conectadas()
    status._gravar(status.ARQ_CONTAS, {"contas": contas, "atualizado_em": None})
    with socketserver.TCPServer(("127.0.0.1", PORTA), Handler) as httpd:
        url = f"http://127.0.0.1:{PORTA}/painel/index.html"
        print(f"painel em {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print("Ctrl+C pra parar.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
