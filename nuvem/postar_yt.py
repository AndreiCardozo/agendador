"""Robô da nuvem: sobe no YouTube os Shorts cuja hora chegou (fila em nuvem/fila_yt*.json).

Sobe 1 vídeo por post, na hora (assim não estoura o limite diário de envios do canal). As chaves do Google
ficam nos Secrets do GitHub (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN).
"""
import json
import os
import tempfile
import urllib.parse
import urllib.request

import fila


def token(cid, sec, refresh):
    corpo = urllib.parse.urlencode({"client_id": cid, "client_secret": sec, "refresh_token": refresh,
                                    "grant_type": "refresh_token"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=corpo),
                                    timeout=60) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google recusou o acesso ({e.read()[:150]!r}); conecte o YouTube de novo no painel")


def postar(e, cid, sec, refresh):
    at = token(cid, sec, refresh)
    arq = os.path.join(tempfile.gettempdir(), f"{e['id']}.mp4")
    urllib.request.urlretrieve(e["video_url"], arq)
    tam = os.path.getsize(arq)
    meta = {"snippet": {"title": e["titulo"], "description": e["descricao"], "tags": e.get("tags", []),
                        "categoryId": "20"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    ini = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(meta).encode(), method="POST",
        headers={"Authorization": f"Bearer {at}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tam)})
    try:
        with urllib.request.urlopen(ini, timeout=60) as r:
            local = r.headers["Location"]
        with open(arq, "rb") as f:
            envio = urllib.request.Request(local, data=f.read(), method="PUT",
                                           headers={"Authorization": f"Bearer {at}", "Content-Type": "video/mp4"})
        with urllib.request.urlopen(envio, timeout=1800) as r:
            vid = json.loads(r.read())["id"]
    except urllib.error.HTTPError as x:
        raise RuntimeError(f"YouTube recusou: {x.read()[:250]!r}")
    finally:
        os.remove(arq)
    if e.get("capa_url"):                     # capa personalizada (se o agendador mandou)
        try:
            cap = urllib.request.urlopen(e["capa_url"], timeout=60).read()
            urllib.request.urlopen(urllib.request.Request(
                f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", data=cap,
                method="POST", headers={"Authorization": f"Bearer {at}", "Content-Type": "image/jpeg"}), timeout=60)
        except Exception as x:
            print("capa não entrou:", x)
    return f"https://youtube.com/shorts/{vid}"


def rodar(arq, tag, cid, sec, refresh):
    fila.processar(arq, tag, lambda e: postar(e, cid, sec, refresh),
                   lambda e: (f"yt_{e['id']}.mp4", f"yt_{e['id']}_capa.jpg"), "YouTube")
