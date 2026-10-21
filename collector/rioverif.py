"""Verificación de la previsión del río en el puerto de Salto.
Guarda en GitHub (data/historial/) cada previsión diaria y lo medido por día (telemetría CTM),
compara lo previsto con lo real según la anticipación (1 a 6 días) y devuelve la corrección aprendida.
"""
import csv, os, datetime as dt

PREV = "data/historial/rio-previsiones.csv"
MED = "data/historial/rio-medido.csv"
CAB_P = ["emitido", "fecha_objetivo", "anticipacion", "c", "min", "max"]
CAB_M = ["fecha", "medio", "max", "min", "ultimo", "n_estacion"]


def _leer(ruta):
    if not os.path.exists(ruta): return []
    return list(csv.DictReader(open(ruta)))


def _append(ruta, cab, filas):
    nuevo = not os.path.exists(ruta)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "a", newline="") as f:
        w = csv.writer(f)
        if nuevo: w.writerow(cab)
        w.writerows(filas)


def guardar(hoy, dias_prev, dias_med):
    """dias_prev: [{fecha ISO, c, min, max}] (el primero = hoy). dias_med: telemetría Salto [{fecha, media, max, min, ultimo}]."""
    hecho = {r["emitido"] for r in _leer(PREV)}
    if hoy.isoformat() not in hecho:
        _append(PREV, CAB_P, [[hoy.isoformat(), d["fecha"], k, d["c"], d["min"], d["max"]] for k, d in enumerate(dias_prev) if k >= 1])
    ya = {r["fecha"] for r in _leer(MED)}
    _append(MED, CAB_M, [[d["fecha"], d.get("media", round((d["max"] + d["min"]) / 2, 2)), d["max"], d["min"], d["ultimo"], "Salto"]
                         for d in dias_med if d["fecha"] < hoy.isoformat() and d["fecha"] not in ya])


def verificar(hoy, dias=30):
    med = {r["fecha"]: float(r["medio"]) for r in _leer(MED)}
    lim = (hoy - dt.timedelta(days=dias)).isoformat()
    por = {}
    comp = []
    for r in _leer(PREV):
        f = r["fecha_objetivo"]
        if f not in med or f < lim: continue
        k = int(r["anticipacion"]); c, mn, mx = float(r["c"]), float(r["min"]), float(r["max"])
        e = c - med[f]
        a = por.setdefault(k, {"err": [], "dentro": 0})
        a["err"].append(e); a["dentro"] += 1 if mn - 0.01 <= med[f] <= mx + 0.01 else 0
        comp.append({"fecha": f, "anticipacion": k, "previsto": c, "min": mn, "max": mx, "medido": med[f]})
    tabla = []
    for k in sorted(por):
        a = por[k]; n = len(a["err"])
        tabla.append({"dias": k, "n": n, "error": round(sum(abs(x) for x in a["err"]) / n, 2),
                      "sesgo": round(sum(a["err"]) / n, 2), "dentro": round(100 * a["dentro"] / n)})
    return tabla, sorted(comp, key=lambda x: (x["fecha"], x["anticipacion"]))


def corregir(dias_prev, tabla, minimo=5):
    """Resta el sesgo aprendido a cada anticipación y ajusta el ancho del rango según cuántas veces acertó."""
    t = {x["dias"]: x for x in tabla}
    aplicado = False
    for k, d in enumerate(dias_prev):
        v = t.get(k)
        if not k or not v or v["n"] < minimo: continue
        c0 = d["c"]; d["c"] = round(c0 - v["sesgo"], 2)
        f = 1.3 if v["dentro"] < 70 else 0.85 if v["dentro"] > 95 else 1.0
        d["min"] = round(d["c"] - (c0 - d["min"]) * f, 2); d["max"] = round(d["c"] + (d["max"] - c0) * f, 2)
        aplicado = True
    return aplicado
