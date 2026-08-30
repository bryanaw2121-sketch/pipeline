# -*- coding: utf-8 -*-
"""Sobe os clipes prontos (e o FALA.txt de cada um) pro Drive.

Usa token OAuth de conta real, NAO conta de servico: conta de servico nao tem
cota de armazenamento e o Google recusa o upload com storageQuotaExceeded.
Medido em 28/08/2026 — criar pasta ela consegue (metadado nao ocupa bytes),
subir arquivo nao.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from engine.drive_query import aspas

ESCOPO = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--token", default="td.json")
    p.add_argument("--pasta", required=True)
    a = p.parse_args()
    sv = build("drive", "v3",
               credentials=Credentials.from_authorized_user_file(a.token, ESCOPO))
    n = 0
    for v in sorted(glob.glob("saida/**/short_9x16.mp4", recursive=True)):
        pasta = Path(v).parent
        try:
            meta = json.load(io.open(pasta / "post.json", encoding="utf-8"))
        except Exception:
            continue
        nome = f"{pasta.name[:2]}_nota{meta.get('nota',0)}_{meta.get('titulo','')[:46]}.mp4"
        nome = nome.replace("/", "-")
        antigos = sv.files().list(
            q=f"name='{aspas(nome)}' and '{aspas(a.pasta)}' in parents "
              "and trashed=false",
            fields="files(id)").execute().get("files", [])
        for x in antigos:
            sv.files().delete(fileId=x["id"]).execute()
        sv.files().create(
            body={"name": nome, "parents": [a.pasta]},
            media_body=MediaFileUpload(v, mimetype="video/mp4",
                                       resumable=True, chunksize=16 * 1024 * 1024),
            fields="id").execute()
        print(f"  subido: {nome[:60]}", flush=True)
        n += 1
        fala = pasta / "FALA.txt"
        if fala.exists():
            sv.files().create(
                body={"name": nome.replace(".mp4", "_FALA.txt"), "parents": [a.pasta]},
                media_body=MediaFileUpload(str(fala), mimetype="text/plain"),
                fields="id").execute()
    print(f"{n} clipe(s) no Drive")


if __name__ == "__main__":
    main()
