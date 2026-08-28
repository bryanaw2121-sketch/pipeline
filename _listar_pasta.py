import sys
from contas_drive import servico, conta_por_nome

conta = conta_por_nome(sys.argv[1] if len(sys.argv) > 1 else "principal")
svc = servico(conta)


def achar_filho(pai_id, nome):
    q = f"'{pai_id}' in parents and name = '{nome}' and trashed = false"
    r = svc.files().list(q=q, fields="files(id,name,mimeType)").execute()
    files = r["files"]
    if not files:
        raise SystemExit(f"não achei '{nome}' dentro de {pai_id}")
    return files[0]


def listar(pai_id):
    r = svc.files().list(
        q=f"'{pai_id}' in parents and trashed = false",
        fields="files(id,name,mimeType,size,modifiedTime)",
        orderBy="name",
        pageSize=1000,
    ).execute()
    return r["files"]


a_postar = conta["a_postar"]
tiktok = achar_filho(a_postar, "tik tok")
parte02 = achar_filho(tiktok["id"], "parte 02")

print(f"a_postar/tik tok/parte 02 = {parte02['id']}\n")
for f in listar(parte02["id"]):
    tipo = "PASTA" if f["mimeType"] == "application/vnd.google-apps.folder" else "arquivo"
    print(f"{f['id']}  [{tipo}]  {f['name']}")
