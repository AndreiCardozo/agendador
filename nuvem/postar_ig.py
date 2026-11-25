"""Robô da nuvem do Agendador @seisestrelaz: posta no Instagram os Reels cuja hora chegou.

Roda no GitHub Actions a cada 15 min (ver .github/workflows/instagram.yml). Lê nuvem/fila_ig.json,
publica o que já passou da hora, marca o resultado e apaga o vídeo temporário da release "ig-fila".
O token fica nos Secrets do GitHub (IG_TOKEN, IG_ID), nunca no código.
"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HOST = "https://graph.facebook.com/v27.0"
TOKEN, IG_ID = os.environ["IG_TOKEN"], os.environ["IG_ID"]
ARQ = os.environ.get("ARQ", "nuvem/fila_ig.json")
TAG = os.environ.get("TAG", "ig-fila")
ATRASO_MAX = timedelta(hours=6)          # se o robô ficou parado muito tempo, não posta tudo de uma vez


def chamar(metodo, caminho, **dados):
    dados["access_token"] = TOKEN
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


def postar(e):
    extra = {"cover_url": e["capa_url"]} if e.get("capa_url") else {}
    cont = chamar("POST", f"{IG_ID}/media", media_type="REELS", video_url=e["video_url"], caption=e["legenda"],
                  share_to_feed="true", **extra)["id"]
    for _ in range(60):                       # até ~10 min processando
        st = chamar("GET", cont, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram recusou o vídeo: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram demorou demais processando")
    pub = chamar("POST", f"{IG_ID}/media_publish", creation_id=cont)
    return chamar("GET", pub["id"], fields="permalink").get("permalink", "")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def salvar(id_, **campos):
    """Grava o status de UM post direto no GitHub (pega a versão mais nova antes; o PC também mexe na fila)."""
    for _ in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        fila = json.load(open(ARQ, encoding="utf-8"))
        for e in fila:
            if e["id"] == id_:
                e.update(campos)
        with open(ARQ, "w", encoding="utf-8") as f:
            json.dump(fila, f, ensure_ascii=False, indent=1)
        git("commit", "-qam", f"robô: {id_} {campos.get('status')}")
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            return True
        time.sleep(5)
    return False


def main():
    git("config", "user.name", "agendador-bot")
    git("config", "user.email", "agendador-bot@users.noreply.github.com")
    fila = json.load(open(ARQ, encoding="utf-8"))
    agora = datetime.now(timezone.utc)
    for e in fila:
        if e.get("status") == "postando" and agora - datetime.strptime(
                e["horario_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > timedelta(hours=1):
            salvar(e["id"], status="erro", erro="o robô parou no meio do envio; confira no Instagram se saiu")
        if e.get("status") != "aguardando":
            continue
        hora = datetime.strptime(e["horario_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if hora > agora:
            continue
        if agora - hora > ATRASO_MAX:
            salvar(e["id"], status="erro", erro="robô ficou parado e o horário passou muito; não postei atrasado")
        else:
            if not salvar(e["id"], status="postando"):       # trava antes: nunca posta duas vezes
                print("não consegui travar", e["id"])
                continue
            try:
                link = postar(e)
                salvar(e["id"], status="postado", link=link, quando=agora.strftime("%Y-%m-%d %H:%M UTC"))
                print("postado", e["id"], link)
            except Exception as x:
                salvar(e["id"], status="erro", erro=str(x)[:300])
                print("erro", e["id"], x)
        for nome in (f"{e['id']}.mp4", f"{e['id']}_capa.jpg"):
            subprocess.run(["gh", "release", "delete-asset", TAG, nome, "-y"], check=False)


if __name__ == "__main__":
    main()
