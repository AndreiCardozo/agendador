"""Partes comuns do robô da nuvem: ler/gravar as filas no GitHub e processar o que chegou a hora."""
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

ATRASO_MAX = timedelta(hours=6)          # se o robô ficou parado muito tempo, não posta tudo de uma vez


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def atualizar():
    git("fetch", "-q", "origin", "main")
    git("reset", "-q", "--hard", "origin/main")


def ler(arq):
    try:
        return json.load(open(arq, encoding="utf-8"))
    except Exception:
        return []


def salvar(arq, id_, **campos):
    """Grava o status de UM post direto no GitHub (pega a versão mais nova antes; o PC também mexe na fila)."""
    for _ in range(6):
        atualizar()
        fila = ler(arq)
        for e in fila:
            if e["id"] == id_:
                e.update(campos)
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(fila, f, ensure_ascii=False, indent=1)
        git("commit", "-qam", f"robô: {id_} {campos.get('status')}")
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            return True
        time.sleep(5)
    return False


def hora(e):
    return datetime.strptime(e["horario_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def processar(arq, tag, postar, assets, rotulo):
    """Posta (uma vez só) cada item da fila cuja hora chegou; trava como 'postando' antes de enviar."""
    agora = datetime.now(timezone.utc)
    for e in ler(arq):
        if e.get("status") == "postando" and agora - hora(e) > timedelta(hours=1):
            salvar(arq, e["id"], status="erro", erro=f"o robô parou no meio do envio; confira no {rotulo} se saiu")
        if e.get("status") != "aguardando" or hora(e) > agora:
            continue
        if agora - hora(e) > ATRASO_MAX:
            salvar(arq, e["id"], status="erro", erro="o robô ficou parado e o horário passou muito; não postei atrasado")
        else:
            if not salvar(arq, e["id"], status="postando"):       # trava antes: nunca posta duas vezes
                print("não consegui travar", e["id"])
                continue
            try:
                link = postar(e)
                salvar(arq, e["id"], status="postado", link=link,
                       quando=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
                print(rotulo, "postado", e["id"], link, flush=True)
            except Exception as x:
                salvar(arq, e["id"], status="erro", erro=str(x)[:300])
                print(rotulo, "erro", e["id"], x, flush=True)
        for nome in assets(e):
            subprocess.run(["gh", "release", "delete-asset", tag, nome, "-y"], check=False, capture_output=True)
