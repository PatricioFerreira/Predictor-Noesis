"""Arma data/tablero.json: todo lo numérico del tablero, listo para copiar a la base del artefacto.

La tarea programada solo tiene que fusionar este parche con el documento actual (collector/fusionar.py)
y escribir los textos que requieren lectura (resúmenes del día, PDFs de CTM, boletín de Brasil, ENSO).
"""
import json, re, math, datetime as dt, urllib.request

LOC = dt.timezone(dt.timedelta(hours=-3))
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DIAS_L = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRES = {"salto": "Salto", "montevideo": "Montevideo", "este": "Este (Punta del Este)"}
CUENCA = {"Alto Uruguai": (-27.6, -54.5), "São Borja": (-28.7, -56.0), "Uruguaiana": (-29.75, -57.09)}
UMBRAL_EVAC = 12.0


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "predictor-noesis/1.0 github.com/PatricioFerreira/Predictor-Noesis"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def metno(lat, lon):
    d = json.loads(_get(f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.3f}&lon={lon:.3f}"))
    out = []
    for it in d["properties"]["timeseries"]:
        t = dt.datetime.fromisoformat(it["time"].replace("Z", "+00:00")).astimezone(LOC)
        det = it["data"]["instant"]["details"]
        f = {"t": t, "temp": det.get("air_temperature"), "hPa": det.get("air_pressure_at_sea_level"),
             "hum": det.get("relative_humidity"), "ws": det.get("wind_speed"), "wd": det.get("wind_from_direction")}
        for k in ("next_1_hours", "next_6_hours", "next_12_hours"):
            if k in it["data"]:
                f[k] = {"s": it["data"][k].get("summary", {}).get("symbol_code"),
                        "mm": (it["data"][k].get("details") or {}).get("precipitation_amount")}
        out.append(f)
    return d["properties"]["meta"].get("updated_at"), out


def cielo_de_simbolo(s, hora):
    s = s or ""; n = hora < 7 or hora >= 20
    if "thunder" in s: return "tormenta"
    if "showers" in s: return "chaparron"
    if "heavyrain" in s or s.startswith("rain") or "sleet" in s: return "lluvia"
    if "lightrain" in s: return "llovizna"
    if "fog" in s: return "niebla"
    if "cloudy" in s and "partly" not in s: return "nube"
    if "partly" in s or "fair" in s: return "lunanube" if n else "solnube"
    if "clearsky" in s: return "luna" if n else "sol"
    return "solnube"


def c2(v):
    return f"{v:.2f}".replace(".", ",")


def etiqueta(fecha):
    d = dt.date.fromisoformat(fecha); return f"{DIAS[d.weekday()]} {d.day}"


def resumen_texto(dias):
    """Resumen corto y llano de la semana, armado con reglas (sin cifras de presión)."""
    if not dias: return ""
    def dia(d): return DIAS_L[dt.date.fromisoformat(d["fecha"]).weekday()]
    lluv = [d for d in dias[:7] if (d["nuestro"].get("probLluvia") or 0) >= 50 or (d["nuestro"].get("mm") or 0) >= 5]
    secos = [d for d in dias[:7] if d not in lluv]
    hoy = dias[0]["nuestro"]
    partes = [f"Hoy máxima de {round(hoy['tmax'])}° y mínima de {round(hoy['tmin'])}°" + (", con lluvia probable." if dias[0] in lluv else ", sin lluvia.")]
    if lluv:
        nombres = [dia(d) for d in lluv if d is not dias[0]][:3]
        if nombres:
            partes.append(("Lluvias probables el " + ", ".join(nombres[:-1]) + (" y " if len(nombres) > 1 else "") + nombres[-1] + ".") if len(nombres) > 1 else f"Lluvia probable el {nombres[0]}.")
    else:
        partes.append("Semana seca, buena para estar afuera.")
    mx = max(dias[:7], key=lambda d: d["nuestro"]["tmax"])
    if mx["nuestro"]["tmax"] >= hoy["tmax"] + 3:
        partes[-1] = partes[-1].rstrip(".") + f"; el día más caluroso sería el {dia(mx)}."
    return " ".join(partes[:2])


METODO_RIO_DESDE = "2026-10-29"  # primer día con el modelo aguas arriba: la verificación de la previsión del río arranca acá
MODELO_RIO = "data/modelo-rio.json"
EST_MODELO = ("Salto", "Santo Tomé", "Yapeyú", "Paso de los Libres", "Monte Caseros", "Salto Grande")


def _medias24(est):
    """Medias de 24 h por estación en la última hora con dato de Salto, 24 h antes y 48 h antes (telemetría horaria de CTM)."""
    ser = {}
    for n in EST_MODELO:
        ser[n] = {x["t"][:13]: x["nivel"] for x in (est.get(n) or {}).get("horario", []) if x.get("nivel") is not None}
    if not ser["Salto"]: raise RuntimeError("sin serie horaria de Salto")
    t_ult = dt.datetime.fromisoformat(max(ser["Salto"]) + ":00")
    def media(n, fin):
        v = [ser[n].get((fin - dt.timedelta(hours=j)).strftime("%Y-%m-%dT%H")) for j in range(24)]
        v = [x for x in v if x is not None]
        if len(v) < 20: raise RuntimeError(f"faltan datos horarios de {n}")
        return sum(v) / len(v)
    return {n: [media(n, t_ult - dt.timedelta(hours=24 * q)) for q in (0, 1, 2)] for n in EST_MODELO}


def modelo_rio(est):
    """Previsión del promedio diario en el puerto para D+1..D+6 con el modelo de data/modelo-rio.json, o None."""
    try:
        M = json.load(open(MODELO_RIO))
    except FileNotFoundError:
        return None
    m = _medias24(est)
    ply = [(m["Yapeyú"][q] + m["Paso de los Libres"][q]) / 2 for q in range(3)]
    x = {"dS24": m["Salto"][0] - m["Salto"][1],
         "dST24": m["Santo Tomé"][0] - m["Santo Tomé"][1], "dST48": m["Santo Tomé"][1] - m["Santo Tomé"][2],
         "dPLY24": ply[0] - ply[1], "dPLY48": ply[1] - ply[2],
         "dMC24": m["Monte Caseros"][0] - m["Monte Caseros"][1], "dMC48": m["Monte Caseros"][1] - m["Monte Caseros"][2],
         "dSG24": m["Salto Grande"][0] - m["Salto Grande"][1], "dSG48": m["Salto Grande"][1] - m["Salto Grande"][2]}
    base = m["Salto"][0]
    out = {"dias": {}, "mae": {}, "mae_ant": {}, "datos": M.get("datos", ""), "rasgos": x, "base": base}
    for k, hz in M["horizontes"].items():
        z = [(x[f] - mu) / sd for f, mu, sd in zip(M["rasgos"], hz["mu"], hz["sd"])]
        d = hz["w"][0] + sum(w * v for w, v in zip(hz["w"][1:], z))
        c = base + d
        out["dias"][int(k)] = (c, c + hz["p10"], c + hz["p90"])
        out["mae"][int(k)] = hz["mae_cv"]; out["mae_ant"][int(k)] = hz["mae_anterior"]
    # qué empuja la previsión a 2 días (para la lectura)
    hz = M["horizontes"]["2"]
    aporte = {f: w * (x[f] - mu) / sd for f, w, mu, sd in zip(M["rasgos"], hz["w"][1:], hz["mu"], hz["sd"])}
    nombres = {"ST": "Santo Tomé", "PLY": "Yapeyú y Paso de los Libres", "MC": "Monte Caseros", "SG": "el embalse de Salto Grande", "S": "el propio puerto"}
    grupos = {}
    for f, v in aporte.items():
        g = re.sub(r"^d|\d+$", "", f); grupos[g] = grupos.get(g, 0) + v
    g, v = max(grupos.items(), key=lambda kv: abs(kv[1]))
    if abs(v) >= 0.08 and g != "S":
        serie = ply if g == "PLY" else m[{"ST": "Santo Tomé", "MC": "Monte Caseros", "SG": "Salto Grande"}[g]]
        cambio = serie[0] - serie[1]
        out["explica"] = (f"Lo que más pesa: {nombres[g]} {'subió' if cambio > 0 else 'bajó'} {abs(cambio) * 100:.0f} cm en el último día, "
                          f"y eso suele {'subir' if v > 0 else 'bajar'} el puerto unos {abs(v) * 100:.0f} cm en dos días.")
    return out


def armar(ahora, ZONAS, res, med, rep, ctm, cuenca, nuestro, ver, inu, errores, docs=None):
    docs = docs or {}
    """Devuelve el parche del documento tablero/actual."""
    zonas = {}
    lluvia_cuenca = {}
    met = {}
    for z, cfg in ZONAS.items():
        try:
            met[z] = metno(cfg["lat"], cfg["lon"])
        except Exception as e:
            errores.append(f"metno {z}: {e}"); met[z] = (None, [])
    for n, (la, lo) in CUENCA.items():
        try:
            _, ts = metno(la, lo)
            fin = ahora + dt.timedelta(days=7)
            tot = 0.0
            for f in ts:
                if f["t"] < ahora or f["t"] > fin: continue
                if "next_1_hours" in f and f["next_1_hours"]["mm"] is not None: tot += f["next_1_hours"]["mm"]
                elif "next_6_hours" in f and f["t"].hour % 6 == 0 and f["next_6_hours"]["mm"] is not None and f["t"] > ahora + dt.timedelta(hours=60): tot += f["next_6_hours"]["mm"]
            lluvia_cuenca[n] = round(tot)
        except Exception as e:
            errores.append(f"metno cuenca {n}: {e}")

    for z in ZONAS:
        upd, ts = met[z]
        mz = med["zonas"].get(z, {})
        fut = [f for f in ts if f["t"] >= ahora.replace(minute=0, second=0, microsecond=0)]
        h0 = fut[0] if fut else None
        zo = {"nombre": NOMBRES[z]}
        if h0:
            zo["ahora"] = {"hora": h0["t"].strftime("%H:%M"), "temp": h0["temp"], "presion": h0["hPa"], "humedad": round(h0["hum"]) if h0["hum"] is not None else None,
                           "vientoKmh": round(h0["ws"] * 3.6) if h0["ws"] is not None else None, "vientoDir": round(h0["wd"]) if h0["wd"] is not None else None,
                           "fuente": f"ECMWF (MET Norway, corrida {upd[11:16] if upd else '?'} UTC), valor modelado"}
            n6 = h0.get("next_6_hours", {}); n12 = h0.get("next_12_hours", {})
            seis = next((f for f in fut if f["t"] >= h0["t"] + dt.timedelta(hours=6) and "next_6_hours" in f), None)
            zo["prox6h"] = {"simbolo": n6.get("s"), "mm": n6.get("mm")}
            mm12 = (n6.get("mm") or 0) + ((seis or {}).get("next_6_hours", {}).get("mm") or 0)
            zo["prox12h"] = {"simbolo": n12.get("s") or n6.get("s"), "mm": round(mm12, 1)}
            rot = []
            for k in range(7):
                tt = h0["t"] + dt.timedelta(hours=2 * k)
                f = next((x for x in fut if x["t"] == tt), None)
                if f and f["wd"] is not None:
                    rot.append({"h": tt.strftime("%Hh"), "dir": round(f["wd"]), "kmh": round(f["ws"] * 3.6)})
            zo["vientoRotacion"] = rot
            serie = []
            for f in ts:
                if f["t"] > ahora and f["t"].hour in (3, 9, 15, 21) and f["hPa"] is not None:
                    serie.append({"t": f"{DIAS[f['t'].weekday()]} {f['t']:%H}h", "hPa": round(f["hPa"], 1)})
            zo["presionSerie"] = serie[:28]
        # actual (medido) con respaldo
        a = dict(mz.get("actual") or {})
        edad = None
        if a.get("t"):
            edad = (ahora - dt.datetime.fromisoformat(a["t"])).total_seconds() / 3600
        if a and edad is not None and edad <= 3:
            a.pop("t", None); zo["actual"] = a
        else:
            rp = (mz.get("represa") or {}).get("ultimo")
            base = dict(zo.get("ahora") or {})
            if z == "salto" and rp and rp.get("temp") is not None and (ahora - dt.datetime.fromisoformat(rp["t"])).total_seconds() <= 2 * 3600:
                base.update({"temp": round(rp["temp"], 1), "hora": rp["t"][11:16], "fuente": "Represa Salto Grande (CTM)"})
            else:
                base["fuente"] = "modelo ECMWF"
            s1 = (h0 or {}).get("next_1_hours", {}).get("s")
            base["cielo"] = cielo_de_simbolo(s1, ahora.hour)
            if a.get("hora"): base["nota"] = f"El último dato medido ({a['hora']}) tiene más de 3 h."
            zo["actual"] = base
        if z == "salto":
            rp = (mz.get("represa") or {}).get("ultimo")
            if rp: zo["represa"] = {"temp": rp.get("temp"), "hora": rp["t"][11:16]}
        # presión: pasado medido (SYNOP) + próximas 3 h corregidas
        hist = {}
        lim = ahora - dt.timedelta(hours=27)
        for f in mz.get("synop") or []:
            if f.get("hPa") is None: continue
            t = dt.datetime.fromisoformat(f["t"])
            if t >= lim and t <= ahora: hist[t.strftime("%Y-%m-%dT%H:00:00-03:00")] = f["hPa"]
        for f in (mz.get("horariaCorregida") or [])[:3]:
            if f.get("hPa") is None: continue
            k = f["t"][:13] + ":00:00-03:00"
            hist.setdefault(k, f["hPa"])
        zo["presionHist"] = [{"t": k, "hPa": v} for k, v in sorted(hist.items())]
        sg = mz.get("sesgo") or {}
        zo["sesgo"] = sg
        zo["presionNota"] = "Pasado: presión medida (partes SYNOP de INUMET, con décimas). Próximas 3 h: nuestro pronóstico" + \
            (f" corregido por sesgo ({sg.get('presion', 0):+.1f} hPa, {sg.get('nPresion', 0)} mediciones)." if sg.get("nPresion", 0) >= 8 else ", todavía sin corrección (faltan mediciones).")
        # días
        dias = []
        inz = {d["fecha"]: d for d in (inu or {}).get(z, [])}
        modz = res["zonas"].get(z, {}).get("modelos", {})
        for n in (nuestro or {}).get(z, [])[:8]:
            f = n["fecha"]
            fu = {}
            for M, arr in modz.items():
                d = next((x for x in arr if x["fecha"] == f), None)
                if not d or d.get("tmax") is None: continue
                e = {k: d.get(k) for k in ("tmax", "tmin", "mm", "vientoKmh", "vientoDir", "humedad", "presionMin")}
                if M == "ECMWF" and d.get("presionMin") is not None: e["presion"] = d["presionMin"]
                fu[M.lower()] = e
            if f in inz:
                i = inz[f]; p = i.get("prob")
                fu["inumet"] = {"tmax": i.get("tmax"), "tmin": i.get("tmin"), "texto": i.get("texto"), "prob": p,
                                "lluvia": None if p is None else "Alta" if p >= 70 else "Media" if p >= 40 else "Baja" if p >= 15 else "Nula"}
            nu = {k: v for k, v in n.items() if k not in ("fecha", "pesos")}
            nu["presion"] = n.get("presionMin")
            dias.append({"etiqueta": etiqueta(f), "fecha": f, "fuentes": fu, "nuestro": nu})
        if dias:
            zo["dias"] = dias
            zo["resumen"] = resumen_texto(dias)
        zonas[z] = zo

    # río
    rio = {}
    est = (ctm or {}).get("estaciones", {})
    s = est.get("Salto")
    if s and s["ultimo"].get("nivel") is not None:
        rio["puerto"] = {"ultimaMedicion": {"altura": s["ultimo"]["nivel"], "fecha": s["ultimo"]["t"][:16], "nota": "Telemetría CTM (cada 15 min)"},
                         "serie": [{"f": d["fecha"][8:10] + "/" + d["fecha"][5:7], "h": d["ultimo"], "tipo": "medido"} for d in s["dias"][-9:]]}
    rio["estacionesCTM"] = {k: {"nivel": v["ultimo"]["nivel"], "t": v["ultimo"]["t"][:16],
                                "d24": round(v["ultimo"]["nivel"] - v["nivelHace24h"], 2) if v["ultimo"]["nivel"] is not None and v.get("nivelHace24h") is not None else None,
                                "lluvia72h": v.get("lluvia72h")} for k, v in est.items()}
    if cuenca:
        rio["lluviaMedidaCuenca"] = {"n": cuenca["n"], "promedio24h": cuenca["promedio24h"], "promedio72h": cuenca["promedio72h"],
                                     "max72h": {"n": cuenca["max72h"]["n"], "lluvia72h": cuenca["max72h"]["lluvia72h"]}}
    if rep:
        u = rep[-1]; t = dt.datetime.fromisoformat(u["t"])
        rio["represa"] = {"fecha": t.strftime("%d/%m %H:%M"), "embalse": u.get("embalse"), "aguasAbajo": u.get("restitucion"),
                          "turbinado": round(u["turbinado"] * 1000) if u.get("turbinado") and u["turbinado"] < 100 else u.get("turbinado"),
                          "vertido": round(u["vertido"] * 1000) if u.get("vertido") and u["vertido"] < 100 else u.get("vertido")}
    # previsión del río: modelo ajustado con un año de telemetría de CTM (data/modelo-rio.json, ver collector/ajustar_rio.py);
    # si falta algún dato, la fórmula anterior (tendencia medida amortiguada)
    if s and s["ultimo"].get("nivel") is not None:
        h = s["ultimo"]["nivel"]
        h72 = s.get("nivelHace72h"); h24 = s.get("nivelHace24h")
        pend = ((h - h72) / 3) if h72 is not None else ((h - h24) if h24 is not None else 0)
        pend = max(-0.25, min(0.25, pend))
        lluvia_prev = max(lluvia_cuenca.values()) if lluvia_cuenca else 0
        mod = None
        try:
            mod = modelo_rio(est)
        except Exception as e:
            errores.append(f"modelo río: {e}")
        dias_r = []; c = h
        up = [est.get(k, {}) for k in ("Garruchos", "Santo Tomé", "Paso de los Libres")]
        sube_arriba = sum(1 for v in up if v.get("ultimo", {}).get("nivel") is not None and v.get("nivelHace24h") is not None and v["ultimo"]["nivel"] > v["nivelHace24h"] + 0.05)
        for k in range(7):
            f = (ahora + dt.timedelta(days=k)).date()
            extra = 0.1 * (k - 3) * min(lluvia_prev, 150) / 100 if k >= 4 and lluvia_prev >= 30 else 0  # lluvia fuerte prevista en la cuenca alta
            if k and mod and k in mod["dias"]:
                c, lo, hi = mod["dias"][k]
                dias_r.append({"f": f"{DIAS[f.weekday()]} {f.day}", "fecha": f.isoformat(), "c": round(c, 2), "min": round(lo, 2), "max": round(hi + extra, 2)})
                continue
            if k: c = c + pend * (0.8 ** k) + (0.04 * sube_arriba if k >= 2 else 0)
            ancho = 0.04 + 0.07 * k
            dias_r.append({"f": f"{DIAS[f.weekday()]} {f.day}", "fecha": f.isoformat(), "c": round(c, 2), "min": round(c - ancho, 2), "max": round(c + ancho + extra, 2)})
        # verificación contra lo medido y corrección aprendida (historial en GitHub); solo previsiones del método vigente
        import rioverif as RV
        verif_rio, comp_rio, corregido = [], [], False
        try:
            verif_rio, comp_rio = RV.verificar(ahora.date(), desde=METODO_RIO_DESDE if mod else None)
            corregido = RV.corregir(dias_r, verif_rio)
            RV.guardar(ahora.date(), dias_r, s.get("dias", []))
        except Exception as e:
            errores.append(f"rioverif: {e}")
        tend = "baja" if pend < -0.02 else "sube" if pend > 0.02 else "se mantiene"
        d2 = dias_r[2] if len(dias_r) > 2 else dias_r[-1]
        pasado = ({"baja": f"en los últimos 3 días bajó unos {abs(pend) * 100:.0f} cm por día", "sube": f"en los últimos 3 días subió unos {abs(pend) * 100:.0f} cm por día"}
                  .get(tend, "en los últimos 3 días se mantuvo"))
        va = d2["c"] - h
        giro = (tend == "baja" and va > 0.1) or (tend == "sube" and va < -0.1)
        lectura = (f"El río en el puerto de Salto está en {c2(h)} m; {pasado}. "
                   + ("Pero se espera que cambie: " if giro else "")
                   + f"para el {DIAS_L[dt.date.fromisoformat(d2['fecha']).weekday()]} se prevé un promedio de {c2(d2['c'])} m"
                   + f" (probablemente entre {c2(d2['min'])} y {c2(d2['max'])} m).")
        if mod and mod.get("explica"):
            lectura += " " + mod["explica"]
        if lluvia_prev >= 50:
            lectura += f" Ojo: se prevén hasta {lluvia_prev} mm en la cuenca alta en la semana, y esa agua llega a Salto unos días después."
        elif max(d["max"] for d in dias_r) < UMBRAL_EVAC - 1:
            lectura += " Lejos de los 12 m en que empiezan las evacuaciones."
        else:
            alto = max(dias_r, key=lambda d: d["max"])
            lectura += (f" El extremo alto del rango llega a {c2(alto['max'])} m el {DIAS_L[dt.date.fromisoformat(alto['fecha']).weekday()]};"
                        " las evacuaciones empiezan en 12 m.")
        if mod:
            metodo = ("Modelo propio ajustado con un año de telemetría de CTM (" + mod["datos"] + "): parte del promedio de las últimas 24 h en el puerto "
                      "y suma lo que anticipan los cambios de las últimas 48 h en Santo Tomé, Yapeyú y Paso de los Libres, Monte Caseros y el embalse de Salto Grande. "
                      "Cada valor es el promedio del día (el puerto sube y baja dentro del día según opera la represa). "
                      f"Probado con meses que el modelo no vio: error medio de {mod['mae'][1] * 100:.0f} cm a 1 día y {mod['mae'][2] * 100:.0f} cm a 2 días "
                      f"(la fórmula anterior: {mod['mae_ant'][1] * 100:.0f} y {mod['mae_ant'][2] * 100:.0f} cm). El rango cubre 8 de cada 10 casos. "
                      "Si se prevé lluvia fuerte en la cuenca alta, el rango se abre hacia arriba desde el cuarto día.")
        else:
            metodo = ("Estimación automática: parte de la altura medida en el puerto (telemetría CTM), sigue la tendencia de los últimos 3 días amortiguada, "
                      "suma si aguas arriba (Garruchos, Santo Tomé, Paso de los Libres) está subiendo y abre el rango hacia arriba si se prevé lluvia fuerte en la cuenca alta.")
        rio["prevision"] = {"dias": dias_r, "lectura": lectura, "verificacion": verif_rio, "comparacion": comp_rio[-60:], "corregido": corregido,
                            "modelo": "regresión aguas arriba" if mod else "tendencia",
                            "lluviaCuenca": {"periodo": f"{ahora:%d/%m} al {(ahora + dt.timedelta(days=7)):%d/%m} · ECMWF (MET Norway)",
                                             "puntos": [{"n": f"{k}, ECMWF", "mm": v} for k, v in lluvia_cuenca.items()]},
                            "metodo": metodo + " Cada día se guarda la previsión y se compara con lo medido; con 5 o más comparaciones por anticipación se corrige el sesgo y el ancho del rango."}
    # documentos leídos automáticamente (CTM, Brasil, NOAA)
    com = docs.get("comunicado") or {}
    if com.get("pronostico"):
        rio.setdefault("puerto", {})["pronostico"] = com["pronostico"]
    if com.get("represa"):
        rio.setdefault("represa", {}).update({k: v for k, v in com["represa"].items() if v is not None})
    if docs.get("ctm"): rio["ctm"] = docs["ctm"]
    if docs.get("sgb"): rio["aguasArriba"] = docs["sgb"]
    # alertas automáticas
    alertas = []
    sg = (docs.get("sgb") or {}).get("estaciones") or []
    try:  # boletín de Brasil viejo (más de 48 h): no genera alertas
        fb = dt.datetime.strptime(f"{ahora.year}/{docs['sgb']['fecha']}", "%Y/%d/%m %H:%M")
        lim = 6 if "SACE" in docs["sgb"].get("fuente", "") else 48  # telemetría cada 15 min vs. boletín diario
        if (ahora.replace(tzinfo=None) - fb).total_seconds() > lim * 3600: sg = []
    except Exception:
        pass
    sobre = [e for e in sg if e.get("nivel") and e.get("inund") and e["nivel"] >= e["inund"]]
    cerca = [e for e in sg if e.get("nivel") and e.get("inund") and e.get("alerta", 0.8 * e["inund"]) <= e["nivel"] < e["inund"]]
    if sobre or cerca:
        baja = all(e.get("tend") == "baja" for e in sobre + cerca if e.get("tend"))
        lista = ", ".join(f"{e['n']} ({e['nivel'] / 100:.2f} m de {e['inund'] / 100:.2f} m)".replace(".", ",") for e in (sobre or cerca))
        alertas.append({"nivel": "rojo" if sobre else "amarillo",
                        "titulo": ("Río Uruguay sobre la cota de inundación en Brasil" if sobre else "Río Uruguay cerca de la cota de inundación en Brasil"),
                        "texto": f"{lista}." + (" Con tendencia a bajar." if baja else " Atención a la evolución en los próximos días."),
                        "fuente": "Serviço Geológico do Brasil", "fecha": (docs.get("sgb") or {}).get("fecha", ""),
                        "link": (docs.get("sgb") or {}).get("link", "https://sace.sgb.gov.br/uruguai/")})
    try:
        av = _get("https://www.inumet.gub.uy/aviso")
        if re.search(r"No hay aviso", av, re.I):
            alertas.append({"nivel": "verde", "titulo": "INUMET: sin avisos vigentes", "texto": "No hay avisos meteorológicos vigentes.",
                            "fuente": "INUMET", "fecha": f"{ahora:%d/%m %H:%M}", "link": "https://www.inumet.gub.uy/aviso"})
        else:
            txt = re.sub(r"<[^>]+>", " ", av); txt = re.sub(r"\s+", " ", txt)
            m = re.search(r"(Advertencia|Aviso)[^.]{0,200}\.", txt)
            alertas.append({"nivel": "amarillo", "titulo": "INUMET: aviso vigente", "texto": (m.group(0) if m else "Hay un aviso vigente; ver detalle en INUMET.")[:300],
                            "fuente": "INUMET", "fecha": f"{ahora:%d/%m %H:%M}", "link": "https://www.inumet.gub.uy/aviso"})
    except Exception as e:
        errores.append(f"aviso inumet: {e}")
    if s and s["ultimo"].get("nivel") is not None:
        h = s["ultimo"]["nivel"]
        niv = "rojo" if h >= 12 else "naranja" if h >= 11.5 else "amarillo" if h >= 11 else None
        if niv:
            alertas.append({"nivel": niv, "titulo": f"Río Uruguay en Salto: {c2(h)} m", "texto": f"Altura medida en el puerto a las {s['ultimo']['t'][11:16]}. A los 12 m empiezan las evacuaciones.",
                            "fuente": "Telemetría CTM", "fecha": f"{ahora:%d/%m %H:%M}"})
    if lluvia_cuenca and max(lluvia_cuenca.values()) >= 50:
        k, v = max(lluvia_cuenca.items(), key=lambda x: x[1])
        alertas.append({"nivel": "naranja", "titulo": "Lluvias importantes previstas en la cuenca alta", "texto": f"ECMWF prevé unos {v} mm en {k} en los próximos 7 días. Esa agua llega a Salto Grande unos días después.",
                        "fuente": "ECMWF (MET Norway)", "fecha": f"{ahora:%d/%m}"})
    for z in ("salto", "montevideo", "este"):
        sy = [f for f in med["zonas"].get(z, {}).get("synop") or [] if f.get("hPa") is not None]
        if len(sy) >= 2:
            ult = sy[-1]; tu = dt.datetime.fromisoformat(ult["t"])
            prev = next((f for f in reversed(sy[:-1]) if abs((tu - dt.datetime.fromisoformat(f["t"])).total_seconds() - 3 * 3600) <= 1800), None)
            if prev:
                caida = prev["hPa"] - ult["hPa"]
                if caida >= 3:
                    alertas.append({"nivel": "rojo" if caida > 6 else "amarillo", "titulo": f"Presión en caída rápida en {NOMBRES[z]}",
                                    "texto": f"Bajó {str(round(caida,1)).replace('.',',')} hPa en 3 horas: suele anunciar un cambio de tiempo brusco (viento fuerte o tormentas).",
                                    "fuente": "SYNOP INUMET", "fecha": f"{tu:%d/%m %H:%M}"})
    # ranking a partir de la verificación
    tabla = []
    for z, vz in (ver or {}).items():
        fuentes = set(vz.get("tmax", {})) & set(vz.get("tmin", {}))
        for f in fuentes:
            a, b = vz["tmax"][f], vz["tmin"][f]
            if a.get("mae") is None or b.get("mae") is None: continue
            tabla.append({"fuente": f, "zona": z, "errorTmax": a["mae"], "errorTmin": b["mae"], "errorMedio": round((a["mae"] + b["mae"]) / 2, 2),
                          "sesgoTmax": a.get("sesgo"), "sesgoTmin": b.get("sesgo"), "n": min(a.get("n", 0), b.get("n", 0))})
    tabla.sort(key=lambda x: x["errorMedio"])
    return {
        "actualizado": ahora.isoformat(timespec="minutes"),
        "generadoPor": "recolector",
        "motor": "Nuestro pronóstico: promedio ponderado por variable según el acierto de cada fuente en los últimos 30 días, corregido por sesgo (calculado en el recolector)",
        "zonas": zonas, "rio": rio, "alertasAuto": alertas, **({"enso": docs["enso"]} if docs.get("enso") else {}), "verificacion": ver or {},
        "ranking": {"tabla": tabla, "diasHistorial": max([t["n"] for t in tabla] or [0])},
        "fuentesAct": {"Recolector propio (GitHub)": f"{ahora:%d/%m %H:%M}", "Estaciones (medido en aeropuertos)": (med["zonas"]["salto"].get("actual") or {}).get("hora", ""),
                       "CTM · Telemetría": (s or {}).get("ultimo", {}).get("t", "")[11:16], "CTM Salto Grande": rio.get("represa", {}).get("fecha", ""),
                       "ECMWF (vía MET Norway y recolector)": f"{ahora:%d/%m %H:%M}", "INUMET": (inu and "ok") or "",
                       "CTM · Datos hidrológicos": (docs.get("ctm") or {}).get("fecha", ""), "Serviço Geológico do Brasil": (docs.get("sgb") or {}).get("fecha", ""),
                       "NOAA CPC": (docs.get("enso") or {}).get("fecha", ""), "CARU": ""},
    }
