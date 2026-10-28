"""Diagnóstico: ¿se puede bajar historia larga de las estaciones de Brasil? (SACE con más horas, y telemetría ANA)"""
import sys, re, json, datetime as dt, urllib.request, urllib.parse, time
sys.path.insert(0, "collector")
import sace
out = []
def p(*x): print(*x, flush=True); out.append(" ".join(str(y) for y in x))
s = sace._Sesion()
for horas in (168, 720, 2160, 8760):
    try:
        t0 = time.time(); h = s.ver_dados(29, horas); filas, cotas = sace._tabla(h)
        p(f"SACE Uruguaiana {horas} h: {len(filas)} filas" + (f" · {filas[0][0]:%d/%m/%Y %H:%M} a {filas[-1][0]:%d/%m/%Y %H:%M}" if filas else "") + f" · {time.time()-t0:.0f} s")
    except Exception as e:
        p(f"SACE {horas} h: error {e}")
    time.sleep(3)
UA = {"User-Agent": "Mozilla/5.0 (predictor-noesis)"}
for url in ["https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?" + urllib.parse.urlencode({"codEstacao": "77150000", "dataInicio": "01/09/2026", "dataFim": "30/09/2026"}),
            "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?" + urllib.parse.urlencode({"codEstacao": "7715000", "dataInicio": "01/09/2026", "dataFim": "30/09/2026"}),
            "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?" + urllib.parse.urlencode({"codEstacao": "77150000", "dataInicio": "01/11/2025", "dataFim": "30/11/2025"})]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            t = r.read().decode("utf-8", "replace")
        niv = re.findall(r"<Nivel>([^<]*)</Nivel>", t); dh = re.findall(r"<DataHora>([^<]*)</DataHora>", t)
        p(f"ANA {url[-60:]}: {len(t)} bytes · {len(niv)} niveles · {dh[-1] if dh else ''} a {dh[0] if dh else ''} · muestra {niv[:3]}")
        if not niv: p("   inicio respuesta:", re.sub(r'\s+', ' ', t[:300]))
    except Exception as e:
        p(f"ANA error {e}")
open("diag/brasil_historia.txt", "w").write("\n".join(out) + "\n")
