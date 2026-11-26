"""Robô da nuvem: posta no Instagram os Reels cuja hora chegou (fila em nuvem/fila_ig*.json).

Usado pelo robo.py (sempre ligado). O token fica nos Secrets do GitHub, nunca no código.
"""
import json
import os
import time
import urllib.parse
import urllib.request

import fila

HOST = "https://graph.facebook.com/v27.0"


def chamar(token, metodo, caminho, **dados):
    dados["access_token"] = token
    corpo = urllib.parse.urlencode(dados).encode()
    url = f"{HOST}/{caminho}"
    if metodo == "GET":
        url, corpo = f"{url}?{corpo.decode()}", None
    req = urllib.request.Request(url, data=corpo, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        erro = json.loads(e.read() or b"{}").get("error", {})
        raise RuntimeError(erro.get("message") or f"HTTP {e.code}")


def postar(e, token, ig_id):
    extra = {"cover_url": e["capa_url"]} if e.get("capa_url") else {}
    cont = chamar(token, "POST", f"{ig_id}/media", media_type="REELS", video_url=e["video_url"],
                  caption=e["legenda"], share_to_feed="true", **extra)["id"]
    for _ in range(60):                       # até ~10 min processando
        st = chamar(token, "GET", cont, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram recusou o vídeo: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram demorou demais processando")
    pub = chamar(token, "POST", f"{ig_id}/media_publish", creation_id=cont)
    return chamar(token, "GET", pub["id"], fields="permalink").get("permalink", "")


def rodar(arq, tag, token, ig_id):
    fila.processar(arq, tag, lambda e: postar(e, token, ig_id),
                   lambda e: (f"{e['id']}.mp4", f"{e['id']}_capa.jpg"), "Instagram")


if __name__ == "__main__":       # compatível com o jeito antigo (uma rodada só)
    fila.git("config", "user.name", "agendador-bot")
    fila.git("config", "user.email", "agendador-bot@users.noreply.github.com")
    rodar(os.environ.get("ARQ", "nuvem/fila_ig.json"), os.environ.get("TAG", "ig-fila"),
          os.environ["IG_TOKEN"], os.environ["IG_ID"])
