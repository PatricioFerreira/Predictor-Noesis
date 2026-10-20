"""Verificación por variable y pronóstico propio ("nuestro") ponderado por acierto.

- Guarda una foto diaria de lo que dijo cada fuente (data/historial/pronosticos-AAAA-MM.csv).
- Compara lo pronosticado el día anterior contra lo medido (data/historial/medido-AAAA-MM.csv).
- Calcula, por zona y variable, el error medio (MAE) y el sesgo de cada fuente en los últimos 30 días.
- Arma "nuestro" con pesos 1/(MAE + e) por variable y le resta nuestro propio sesgo cuando hay datos.
"""
import csv, glob, json, math, os, datetime as dt

VARS = ["tmax", "tmin", "mm", "prob", "viento", "dir", "humedad", "pmin"]
EPS = {"tmax": .5, "tmin": .5, "mm": .5, "prob": .05, "viento": 2, "dir": 15, "humedad": 3, "pmin": .5}
CAB_P = ["emitido", "zona", "fuente", "fecha_objetivo", "tmax", "tmin", "mm", "prob", "viento", "dir", "humedad", "pmin"]
CAB_M = ["fecha", "zona", "tmax", "tmin", "mm", "viento", "dir", "humedad", "pmin", "n", "estacion"]
INU_ZONA = {"salto": [66], "montevideo": [88], "este": [89, 68]}
MIN_N = 5


def prob_de_mm(mm):
    if mm is None: return None
    return 10 if mm < .5 else 35 if mm < 3 else 60 if mm < 8 else 80


def inumet(get):
    d = json.loads(get("https://www.inumet.gub.uy/reportes/pronosticos/pronosticoV4.json"))
    ini = dt.date.fromisoformat(d["inicioPronostico"][:10])
    out = {}
    for z, ids in INU_ZONA.items():
        dias = {}
        for zid in ids:
            for it in d.get("items", []):
                if it.get("zonaId") != zid: continue
                f = (ini + dt.timedelta(days=int(it.get("diaMasN", 0)))).isoformat()
                if f in dias and dias[f].get("tmax") is not None: continue
                def num(x):
                    try: return float(x)
                    except Exception: return None
                txt = " ".join((sg.get("descripcion") or "") + " " + (sg.get("descripcionExtra") or "") for sg in it.get("subgrupos") or []).lower()
                pl = it.get("probLluvia")
                if pl: prob = {"nula": 5, "baja": 20, "media": 50, "alta": 80}.get(pl.lower())
                elif txt.strip():
                    prob = 70 if any(w in txt for w in ("tormenta", "lluvias", "chaparr")) else 50 if any(w in txt for w in ("lluvia", "lloviz", "precip")) else 10
                else: prob = None
                dias[f] = {"fecha": f, "tmax": num(it.get("tempMax")), "tmin": num(it.get("tempMin")), "prob": prob, "texto": txt.strip()[:160]}
        out[z] = sorted(dias.values(), key=lambda x: x["fecha"])
    return out, d.get("fechaPublicacion")


def _migrar(ruta, cab):
    """Si la planilla tiene columnas viejas, la reescribe con las nuevas (sin perder filas)."""
    if not os.path.exists(ruta): return
    filas = list(csv.reader(open(ruta)))
    if not filas or filas[0] == cab: return
    vieja = filas[0]
    nuevas = [cab] + [[dict(zip(vieja, r)).get(c, "") for c in cab] for r in filas[1:]]
    if "modelo" in vieja:
        for r, o in zip(nuevas[1:], filas[1:]): r[cab.index("fuente")] = dict(zip(vieja, o)).get("modelo", "")
    csv.writer(open(ruta, "w", newline="")).writerows(nuevas)


def _append(ruta, cab, filas):
    _migrar(ruta, cab)
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="") as f:
        w = csv.writer(f)
        if nuevo: w.writerow(cab)
        w.writerows(filas)


def guardar_foto(ahora, modelos_por_zona, inu, nuestro):
    """Una foto por día de lo que dice cada fuente (corrida de las 20 a 22 h)."""
    mes = ahora.strftime("%Y-%m"); hoy = ahora.strftime("%Y-%m-%d")
    ruta = f"data/historial/pronosticos-{mes}.csv"
    _migrar(ruta, CAB_P)
    if os.path.exists(ruta) and any(r.get("emitido") == hoy and r.get("fuente") == "NUESTRO" for r in csv.DictReader(open(ruta))):
        return False
    filas = []
    for z, mods in modelos_por_zona.items():
        for M, dias in mods.items():
            for d in dias:
                filas.append([hoy, z, M, d["fecha"], d.get("tmax"), d.get("tmin"), d.get("mm"), prob_de_mm(d.get("mm")),
                              d.get("vientoKmh"), d.get("vientoDir"), d.get("humedad"), d.get("presionMin")])
        for d in inu.get(z, []):
            filas.append([hoy, z, "INUMET", d["fecha"], d.get("tmax"), d.get("tmin"), "", d.get("prob"), "", "", "", ""])
        for d in nuestro.get(z, []):
            filas.append([hoy, z, "NUESTRO", d["fecha"], d.get("tmax"), d.get("tmin"), d.get("mm"), d.get("probLluvia"),
                          d.get("vientoKmh"), d.get("vientoDir"), d.get("humedad"), d.get("presionMin")])
    _append(ruta, CAB_P, filas)
    return True


def guardar_medido(ahora, med_zonas):
    """Lo medido por día (días completos). Si el día ya estaba, completa las columnas que falten."""
    mes = ahora.strftime("%Y-%m")
    ruta = f"data/historial/medido-{mes}.csv"
    _migrar(ruta, CAB_M)
    filas = {(r["fecha"], r["zona"]): r for r in csv.DictReader(open(ruta))} if os.path.exists(ruta) else {}
    for z, v in med_zonas.items():
        for d in v.get("dias", []):
            if not d.get("completo") or not d["fecha"].startswith(mes): continue
            nuevo = {"fecha": d["fecha"], "zona": z, "tmax": d.get("tmax"), "tmin": d.get("tmin"), "mm": d.get("mm"), "viento": d.get("vientoKmh"),
                     "dir": d.get("vientoDir"), "humedad": d.get("humedad"), "pmin": d.get("presionMin"), "n": d.get("n"), "estacion": v.get("estacion")}
            viejo = filas.get((d["fecha"], z), {})
            filas[(d["fecha"], z)] = {c: (viejo.get(c) if viejo.get(c) not in (None, "") else ("" if nuevo[c] is None else nuevo[c])) for c in CAB_M}
    with open(ruta, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAB_M); w.writeheader()
        for k in sorted(filas): w.writerow(filas[k])


def _f(x):
    try: return float(x)
    except Exception: return None


def verificar(ahora, dias=30):
    """Error de cada fuente (pronóstico emitido el día anterior) contra lo medido, por zona y variable."""
    lim = (ahora.date() - dt.timedelta(days=dias)).isoformat()
    med = {}
    for ruta in sorted(glob.glob("data/historial/medido-*.csv"))[-2:]:
        _migrar(ruta, CAB_M)
        for r in csv.DictReader(open(ruta)):
            if r["fecha"] >= lim: med[(r["fecha"], r["zona"])] = r
    acc = {}; filas = {}
    for ruta in sorted(glob.glob("data/historial/pronosticos-*.csv"))[-2:]:
        _migrar(ruta, CAB_P)
        for r in csv.DictReader(open(ruta)):
            filas[(r["emitido"], r["zona"], r["fuente"], r["fecha_objetivo"])] = r  # si hay dos fotos del mismo día, vale la última
    for r in filas.values():
        if True:
            try:
                if (dt.date.fromisoformat(r["fecha_objetivo"]) - dt.date.fromisoformat(r["emitido"])).days != 1: continue
            except Exception:
                continue
            m = med.get((r["fecha_objetivo"], r["zona"]))
            if not m: continue
            for v in VARS:
                key = {"viento": "viento", "dir": "dir", "pmin": "pmin", "prob": "prob"}.get(v, v)
                p = _f(r.get(key))
                if v == "prob":
                    o = _f(m.get("mm"))
                    if p is None or o is None: continue
                    err = (p / 100 - (1.0 if o >= 1 else 0.0)) ; e_abs = err * err  # Brier
                elif v == "dir":
                    o = _f(m.get("dir")); w = _f(m.get("viento"))
                    if p is None or o is None or (w is not None and w < 6): continue
                    err = ((p - o + 180) % 360) - 180; e_abs = abs(err)
                else:
                    o = _f(m.get(v))
                    if p is None or o is None: continue
                    err = p - o; e_abs = abs(err)
                a = acc.setdefault(r["zona"], {}).setdefault(v, {}).setdefault(r["fuente"].lower(), [0, 0.0, 0.0])
                a[0] += 1; a[1] += e_abs; a[2] += err
    out = {}
    for z, vs in acc.items():
        for v, fs in vs.items():
            for fu, (n, se, sb) in fs.items():
                out.setdefault(z, {}).setdefault(v, {})[fu] = {"mae": round(se / n, 3 if v == "prob" else 2), "sesgo": round(sb / n, 2), "n": n}
    return out


def mezclar(modelos_por_zona, inu, verif, hoy):
    """Nuestro pronóstico por zona y día: promedio ponderado por variable según el acierto de cada fuente."""
    res = {}
    for z, mods in modelos_por_zona.items():
        vz = verif.get(z, {})
        fechas = sorted({d["fecha"] for ds in mods.values() for d in ds if d["fecha"] >= hoy})[:8]
        inu_d = {d["fecha"]: d for d in inu.get(z, [])}
        dias = []
        for f in fechas:
            val = {}  # var -> {fuente: valor}
            for M, ds in mods.items():
                d = next((x for x in ds if x["fecha"] == f), None)
                if not d: continue
                for v, k in (("tmax", "tmax"), ("tmin", "tmin"), ("mm", "mm"), ("viento", "vientoKmh"), ("dir", "vientoDir"), ("humedad", "humedad"), ("pmin", "presionMin")):
                    if d.get(k) is not None: val.setdefault(v, {})[M.lower()] = d[k]
                if d.get("mm") is not None: val.setdefault("prob", {})[M.lower()] = prob_de_mm(d["mm"])
            if f in inu_d:
                for v in ("tmax", "tmin", "prob"):
                    if inu_d[f].get(v) is not None: val.setdefault(v, {})["inumet"] = inu_d[f][v]
            out = {"fecha": f, "pesos": {}}
            for v, fv in val.items():
                st = vz.get(v, {})
                todos = all(st.get(fu, {}).get("n", 0) >= MIN_N for fu in fv)
                w = {fu: (1 / (st[fu]["mae"] + EPS[v]) if todos else 1.0) for fu in fv}
                tot = sum(w.values())
                w = {fu: x / tot for fu, x in w.items()}
                if v == "dir":
                    vel = val.get("viento", {})
                    u = sum(w[fu] * max(vel.get(fu, 1), 1) * math.sin(math.radians(x)) for fu, x in fv.items())
                    c = sum(w[fu] * max(vel.get(fu, 1), 1) * math.cos(math.radians(x)) for fu, x in fv.items())
                    x = math.degrees(math.atan2(u, c)) % 360
                else:
                    x = sum(w[fu] * fv[fu] for fu in fv)
                    ns = vz.get(v, {}).get("nuestro")
                    if ns and ns["n"] >= MIN_N and v not in ("prob",):
                        x -= ns["sesgo"]
                out[v] = x
                out["pesos"][v] = {fu: round(x_, 2) for fu, x_ in w.items()}
            tx, tn = val.get("tmax", {}), val.get("tmin", {})
            disp = 0
            if tx and tn: disp = max(max(tx.values()) - min(tx.values()), max(tn.values()) - min(tn.values()))
            dias.append({"fecha": f,
                         "tmax": round(out["tmax"], 1) if "tmax" in out else None, "tmin": round(out["tmin"], 1) if "tmin" in out else None,
                         "mm": round(max(out.get("mm", 0), 0), 1), "probLluvia": round(out["prob"]) if "prob" in out else None,
                         "vientoKmh": round(out["viento"]) if "viento" in out else None, "vientoDir": round(out["dir"]) if "dir" in out else None,
                         "humedad": round(out["humedad"]) if "humedad" in out else None, "presionMin": round(out["pmin"], 1) if "pmin" in out else None,
                         "dispersion": round(disp, 1), "confianza": "alta" if disp <= 2.5 else "media" if disp <= 5 else "baja",
                         "nFuentes": len(set(tx) | set(tn)), "pesos": out["pesos"]})
        res[z] = dias
    return res
