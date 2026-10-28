"""Recolector "en vivo": corre dentro de GitHub Actions durante ~5 h 45 min.
- Cada 5 min: lo medido ahora (aeropuertos, río en el puerto, represa) -> data/ahora.json y publica la página.
- Cada 15 min: corrida completa liviana del recolector (modelos, pronóstico, verificación).
- Cada hora (en punto): corrida completa (incluye documentos y lluvia de la cuenca) y guarda todo en el repositorio.
La página se publica en la rama gh-pages, siempre con un único commit (no crece el historial).
"""
import os, sys, json, time, subprocess, importlib, datetime as dt, traceback
sys.path.insert(0, os.path.dirname(__file__))
import collect as C

LOC = dt.timezone(dt.timedelta(hours=-3))
DURACION = float(os.environ.get("VIVO_MINUTOS", "345")) * 60
inicio = time.time()


def sh(cmd):
    print("+", cmd, flush=True)
    return subprocess.run(cmd, shell=True, check=False)


def ahora_json():
    out = {"generado": dt.datetime.now(LOC).isoformat(timespec="seconds"), "zonas": {}, "rio": {}}
    try:
        med = json.load(open("data/medido.json"))
    except Exception:
        med = {"zonas": {}}
    for z, cfg in C.ZONAS.items():
        try:
            obs = C.metar(cfg["icao"], horas=3)
            a = C.actual_de(obs)
            if not a: continue
            prev = (med.get("zonas", {}).get(z, {}) or {}).get("horariaCorregida") or []
            hit = next((m for m in prev if m["t"][:13] == a["t"][:13]), None)
            if hit and a.get("temp") is not None:
                a["previsto"] = hit["temp"]; a["desvio"] = round(a["temp"] - hit["temp"], 1)
            out["zonas"][z] = {"actual": a}
        except Exception as e:
            print("metar", z, e)
    try:
        r = C.ctm_estaciones(1, {"Salto": C.CTM_EST["Salto"]}, horario=False)["estaciones"].get("Salto")
        if r: out["rio"]["salto"] = r["ultimo"]
    except Exception as e:
        print("ctm", e)
    try:
        rep = C.ctm_horario(1)
        u = [f for f in rep if f.get("temp") is not None]
        if u: out["zonas"].setdefault("salto", {})["represa"] = {"temp": u[-1]["temp"], "hora": u[-1]["t"][11:16]}
    except Exception as e:
        print("represa", e)
    json.dump(out, open("data/ahora.json", "w"), ensure_ascii=False)


def publicar():
    sh("git fetch -q origin main && git checkout origin/main -- web/ collector/fusionar.py 2>/dev/null || true")  # siempre la última versión de la página
    sh("python web/armar_sitio.py")
    sh("cp data/ahora.json _site/data/ 2>/dev/null || true")
    sh("cd _site && rm -rf .git && git init -q -b gh-pages && git add -A && "
       "git -c user.name=recolector -c user.email=recolector@users.noreply.github.com commit -qm 'Página' && "
       f"git push -qf https://x-access-token:{os.environ.get('GITHUB_TOKEN', '')}@github.com/{os.environ.get('GITHUB_REPOSITORY', '')}.git gh-pages")
    # pedirle a GitHub Pages que publique ya (por si el push con el token del workflow no dispara la publicación)
    sh(f"curl -s -o /dev/null -w 'pages build %{{http_code}}\\n' -X POST -H 'Authorization: Bearer {os.environ.get('GITHUB_TOKEN', '')}' "
       f"-H 'Accept: application/vnd.github+json' https://api.github.com/repos/{os.environ.get('GITHUB_REPOSITORY', '')}/pages/builds")


def recargar_codigo():
    """Trae el código del recolector de main y lo recarga, así un cambio entra en la próxima corrida completa
    (una por hora) sin esperar a que termine esta tanda de casi 6 horas."""
    global C
    antes = subprocess.run("git rev-parse HEAD:collector", shell=True, capture_output=True, text=True).stdout.strip()
    sh("git fetch -q origin main && git checkout origin/main -- collector/ 2>/dev/null || true")
    despues = subprocess.run("git rev-parse origin/main:collector", shell=True, capture_output=True, text=True).stdout.strip()
    if not despues or despues == getattr(recargar_codigo, "ultimo", antes): return
    recargar_codigo.ultimo = despues
    try:
        for m in ("sace", "documentos", "rioverif", "verif", "tablero", "collect"):
            if m in sys.modules: importlib.reload(sys.modules[m])
        C = sys.modules["collect"]
        print("código del recolector recargado", despues[:8], flush=True)
    except Exception:
        traceback.print_exc()  # si algo falla al recargar, sigue con lo que ya estaba cargado


def guardar_repo():
    sh("git add data/ && (git diff --cached --quiet || git -c user.name=recolector -c user.email=recolector@users.noreply.github.com "
       "commit -qm \"Datos $(date -u +%Y-%m-%dT%H:%MZ)\") && git pull -q --rebase -X theirs origin main; git push -q origin HEAD:main || true")


if len(sys.argv) > 1 and sys.argv[1] == "una":
    C.main(ligero=False); ahora_json(); publicar(); guardar_repo(); sys.exit(0)

ultimo_completo = 0
ultima_hora = -1
while time.time() - inicio < DURACION:
    t0 = time.time()
    now = dt.datetime.now(LOC)
    try:
        if now.hour != ultima_hora:
            recargar_codigo()
            C.main(ligero=False); ultima_hora = now.hour; ultimo_completo = t0
            guardar_repo()
        elif t0 - ultimo_completo >= 15 * 60 - 30:
            C.main(ligero=True); ultimo_completo = t0
    except Exception:
        traceback.print_exc()
    try:
        ahora_json()
        publicar()
    except Exception:
        traceback.print_exc()
    espera = 300 - (time.time() - t0)
    if espera > 0 and time.time() - inicio + espera < DURACION:
        time.sleep(espera)
    elif espera > 0:
        break
guardar_repo()
