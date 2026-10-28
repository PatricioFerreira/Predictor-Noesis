"""Baja la historia de la telemetría de CTM (niveles cada 15 min) y la guarda como serie horaria.

Uso: python collector/historia_rio.py [meses]   (por defecto 24)
Salida: data/historial/ctm-niveles-horario.csv  (t local UTC-3, una columna por estación, nivel en m)
Pide un mes por vez y por estación, con pausas, para no cargar el servidor de CTM.
"""
import os, sys, csv, time, datetime as dt, urllib.request, urllib.parse, re, html as H

sys.path.insert(0, os.path.dirname(__file__))
from collect import CTM_EST

LOC = dt.timezone(dt.timedelta(hours=-3))
UA = {"User-Agent": "Mozilla/5.0 (predictor-noesis; github.com/PatricioFerreira/Predictor-Noesis)"}
SALIDA = "data/historial/ctm-niveles-horario.csv"
ORDEN = ["El Soberbio", "Garruchos", "Santo Tomé", "Yapeyú", "Paso de los Libres", "Bonpland", "Monte Caseros", "Belén",
         "Federación", "Salto Grande", "Salto", "Puerto Concordia"]


def bajar(cod, desde, hasta):
    q = {"estacion": cod, "desde": desde.strftime("%d/%m/%Y"), "hasta": hasta.strftime("%d/%m/%Y")}
    for intento in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request("https://www.saltogrande.org/datos_estacion.php?" + urllib.parse.urlencode(q), headers=UA), timeout=120) as r:
                txt = r.read().decode("utf-8", "replace")
            break
        except Exception as e:
            print("  reintento", intento, e, flush=True); time.sleep(10)
    else:
        return []
    filas = []
    for fila in re.findall(r"<tr.*?</tr>", txt, flags=re.S):
        c = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td.*?</td>", fila, flags=re.S)]
        if len(c) < 2 or not re.match(r"\d\d/\d\d/\d{4} \d\d:\d\d", c[0]): continue
        try:
            v = float(c[1].replace(",", "."))
        except Exception:
            continue
        filas.append((dt.datetime.strptime(c[0], "%d/%m/%Y %H:%M"), v))
    return filas


LOG = "data/historial/ctm-historia-log.txt"
CLAVE = ["Garruchos", "Santo Tomé", "Yapeyú", "Paso de los Libres", "Monte Caseros", "Salto Grande", "Salto", "Puerto Concordia"]


def main(meses=12):
    log = open(LOG, "w")
    def p(*x):
        print(*x, flush=True); print(*x, file=log, flush=True)
    hoy = dt.datetime.now(LOC).replace(tzinfo=None)
    # 1) qué largo de tramo acepta el servidor
    tramo = None
    for dias in (31, 15, 8, 4):
        f = bajar(CTM_EST["Salto"], hoy - dt.timedelta(days=dias), hoy)
        p(f"prueba Salto {dias} días: {len(f)} datos" + (f" ({f[0][0]} a {f[-1][0]})" if f else ""))
        if f and (f[-1][0] - f[0][0]).days >= dias - 2:
            tramo = dias; break
        time.sleep(1.5)
    if not tramo:
        p("el servidor no devolvió tramos completos; se usa 4 días"); tramo = 4
    serie = {}
    for nom in [k for k in ORDEN if k in CLAVE]:
        cod = CTM_EST.get(nom)
        n, vacios, fin = 0, 0, hoy
        while fin > hoy - dt.timedelta(days=30.5 * meses):
            ini = fin - dt.timedelta(days=tramo)
            filas = bajar(cod, ini, fin)
            n += len(filas); vacios = 0 if filas else vacios + 1
            for t, v in filas:
                serie.setdefault(t.replace(minute=0), {}).setdefault(nom, []).append(v)
            fin = ini
            time.sleep(1.2)
            if vacios >= 4: break  # varios tramos seguidos sin datos: no hay más historia
        p(f"{nom}: {n} datos")
    with open(SALIDA, "w", newline="") as f:
        w = csv.writer(f)
        cols = [k for k in ORDEN if k in CLAVE]
        w.writerow(["t"] + cols)
        for t in sorted(serie):
            d = serie[t]
            w.writerow([t.strftime("%Y-%m-%dT%H:00")] + [round(sum(d[k]) / len(d[k]), 3) if k in d else "" for k in cols])
    p("filas", len(serie), "desde", min(serie) if serie else None)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
