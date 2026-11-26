"""Robô da nuvem SEMPRE LIGADO: confere as filas a cada minuto por ~5h40 e, antes de acabar, chama a próxima
rodada (o relógio do GitHub atrasa/pula horários, então ele não é mais o gatilho principal, só a reserva).

Filas (cada uma só roda se os Secrets dela existirem):
  Instagram seisestrelaz       nuvem/fila_ig.json      IG_TOKEN / IG_ID
  Instagram Mundos Altern.     nuvem/fila_ig_ma.json   IG_TOKEN_MA / IG_ID_MA
  YouTube seisestrelaz         nuvem/fila_yt.json      YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
  YouTube Mundos Altern.       nuvem/fila_yt_ma.json   YT_CLIENT_ID_MA / YT_CLIENT_SECRET_MA / YT_REFRESH_TOKEN_MA
"""
import os
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fila
import postar_ig
import postar_yt

DURACAO = float(os.environ.get("DURACAO_MIN", 335)) * 60


def filas():
    out = []
    for suf in ("", "_ma"):
        S = suf.upper()
        if os.environ.get(f"IG_TOKEN{S}") and os.environ.get(f"IG_ID{S}"):
            out.append((f"Instagram{suf}", lambda a=f"nuvem/fila_ig{suf}.json", t=f"ig-fila{suf}",
                        tk=os.environ[f"IG_TOKEN{S}"], i=os.environ[f"IG_ID{S}"]: postar_ig.rodar(a, t, tk, i)))
        if os.environ.get(f"YT_REFRESH_TOKEN{S}"):
            out.append((f"YouTube{suf}", lambda a=f"nuvem/fila_yt{suf}.json", t=f"yt-fila{suf}",
                        c=os.environ[f"YT_CLIENT_ID{S}"], s=os.environ[f"YT_CLIENT_SECRET{S}"],
                        r=os.environ[f"YT_REFRESH_TOKEN{S}"]: postar_yt.rodar(a, t, c, s, r)))
    return out


def main():
    fila.git("config", "user.name", "agendador-bot")
    fila.git("config", "user.email", "agendador-bot@users.noreply.github.com")
    lista = filas()
    print("filas:", [n for n, _ in lista], flush=True)
    ini = time.time()
    while time.time() - ini < DURACAO:
        fila.atualizar()
        for nome, rodar in lista:
            try:
                rodar()
            except Exception:
                print("erro na fila", nome, flush=True)
                traceback.print_exc()
        time.sleep(60)
    if os.environ.get("ENCADEAR", "1") == "1":     # chama a próxima rodada (fica ligado sem depender do relógio)
        r = subprocess.run(["gh", "workflow", "run", "robo.yml"], capture_output=True, text=True)
        print("próxima rodada:", r.returncode, r.stderr.strip()[:200], flush=True)


if __name__ == "__main__":
    main()
