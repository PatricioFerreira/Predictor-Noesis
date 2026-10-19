"""Recolector del Predictor del Litoral.
Corre en GitHub Actions cada 3 horas y deja data/latest.json con:
- modelos: pronóstico diario y presión horaria de varios modelos (vía Open-Meteo) para Salto, Montevideo y el Este
- observado: METAR de los aeropuertos (SUSO, SUMU, SULS) → data/medido.json
- SMN Argentina WRF 4 km (AWS Open Data) → data/smn.json
El tablero (https://claude.ai/artifact/NmUMC1ftYmnFYfr9grZAFw) lo lee en cada actualización.
"""
import json, datetime as dt, urllib.request, urllib.parse, csv, io, sys, traceback

TZ = "America/Montevideo"
DIAG = []
ZONAS = {
    "salto":      {"lat": -31.383, "lon": -57.967, "isd": ["86360099999"], "icao": "SUSO", "aero": (-31.438, -57.985)},  # Salto (Nueva Hespérides)
    "montevideo": {"lat": -34.880, "lon": -56.180, "isd": ["86580099999", "86585099999"], "icao": "SUMU", "aero": (-34.838, -56.031)},  # Carrasco
    "este":       {"lat": -34.940, "lon": -54.960, "isd": ["86586099999"], "icao": "SULS", "aero": (-34.856, -55.094)},  # Laguna del Sauce
}
MODELOS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", "jma_seamless", "meteofrance_seamless", "ukmo_seamless"]
NOMBRE = {"ecmwf_ifs025": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON", "gem_seamless": "GEM",
          "jma_seamless": "JMA", "meteofrance_seamless": "ARPEGE", "ukmo_seamless": "UKMO"}

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "predictor-litoral (uso personal)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def modelos(z):
    q = {"latitude": z["lat"], "longitude": z["lon"], "timezone": TZ, "forecast_days": 8,
         "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant",
         "hourly": "pressure_msl", "past_days": 1, "models": ",".join(MODELOS)}
    d = json.loads(get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)))
    out = {}
    for m in MODELOS:
        sfx = "_" + m
        dd = d["daily"]
        if ("temperature_2m_max" + sfx) not in dd:
            continue
        dias = []
        for i, f in enumerate(dd["time"]):
            dias.append({"fecha": f,
                         "tmax": dd["temperature_2m_max" + sfx][i], "tmin": dd["temperature_2m_min" + sfx][i],
                         "mm": dd["precipitation_sum" + sfx][i], "vientoKmh": dd["wind_speed_10m_max" + sfx][i],
                         "vientoDir": dd["wind_direction_10m_dominant" + sfx][i]})
        hh = d["hourly"]
        out[NOMBRE[m]] = {"dias": dias}
        if m == "ecmwf_ifs025":
            out[NOMBRE[m]]["presionHoraria"] = [{"t": t, "hPa": p} for t, p in zip(hh["time"], hh.get("pressure_msl" + sfx, [])) if p is not None][:72]
    return out

def observado(estaciones, dias=5):
    """Máx/mín/lluvia diarios (hora local) desde NOAA ISD global-hourly."""
    fin = dt.date.today(); ini = fin - dt.timedelta(days=dias)
    for st in estaciones:
        q = {"dataset": "global-hourly", "stations": st, "startDate": ini.isoformat(), "endDate": fin.isoformat(),
             "dataTypes": "TMP,SLP,AA1", "format": "csv", "units": "metric"}
        try:
            txt = get("https://www.ncei.noaa.gov/access/services/data/v1?" + urllib.parse.urlencode(q), timeout=90)
        except Exception as e:
            print("ISD", st, e); DIAG.append(f"ISD {st}: {e}"); continue
        DIAG.append(f"ISD {st}: {len(txt.splitlines())} filas")
        por_dia = {}
        horaria = []
        for row in csv.DictReader(io.StringIO(txt)):
            try:
                t = dt.datetime.fromisoformat(row["DATE"]).replace(tzinfo=dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-3)))
            except Exception:
                continue
            d = por_dia.setdefault(t.date().isoformat(), {"t": [], "lluvia": 0.0})
            tmp = row.get("TMP", "")
            if tmp and not tmp.startswith("+9999"):
                v = int(tmp.split(",")[0]) / 10; d["t"].append(v)
            slp = row.get("SLP", "")
            if slp and not slp.startswith("99999"):
                horaria.append({"t": t.isoformat(), "hPa": int(slp.split(",")[0]) / 10})
            aa = row.get("AA1", "")
            if aa:
                try:
                    p = aa.split(","); hrs, mm = int(p[0]), int(p[1]) / 10
                    if hrs in (6, 12, 24) and mm < 999: d["lluvia"] = max(d["lluvia"], mm) if hrs == 24 else d["lluvia"] + (mm if hrs == 6 else 0)
                except Exception:
                    pass
        res = [{"fecha": f, "tmax": max(v["t"]), "tmin": min(v["t"]), "lluvia": round(v["lluvia"], 1), "n": len(v["t"])}
               for f, v in sorted(por_dia.items()) if len(v["t"]) >= 6]
        if res:
            return {"estacion": st, "fuente": "NOAA ISD (SYNOP)", "dias": res, "presionHoraria": horaria[-48:]}
    return None

def metar(icao, horas=96):
    """Observaciones horarias (METAR) del aeropuerto: temperatura, presión (QNH) y viento."""
    txt = get("https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode({"ids": icao, "hours": horas, "format": "json"}))
    obs = json.loads(txt) if txt.strip() else []
    DIAG.append(f"METAR {icao}: {len(obs)} obs")
    loc = dt.timezone(dt.timedelta(hours=-3))
    filas = []
    for o in obs:
        try:
            t = dt.datetime.fromtimestamp(o["obsTime"], dt.timezone.utc).astimezone(loc)
        except Exception:
            continue
        tmp, dew = o.get("temp"), o.get("dewp")
        hr = None
        if isinstance(tmp, (int, float)) and isinstance(dew, (int, float)):
            import math
            a, b = 17.625, 243.04
            hr = round(100 * math.exp(a * dew / (b + dew) - a * tmp / (b + tmp)))
        capas = o.get("clouds") or []
        cob = max([{"FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4, "OVX": 4}.get(c.get("cover"), 0) for c in capas] or [0])
        filas.append({"t": t.isoformat(), "temp": tmp, "hPa": o.get("altim"), "humedad": hr,
                      "vientoKmh": round(o["wspd"] * 1.852) if isinstance(o.get("wspd"), (int, float)) else None,
                      "vientoDir": o.get("wdir") if isinstance(o.get("wdir"), (int, float)) else None,
                      "nubosidad": cob, "fenomeno": o.get("wxString") or "", "visib": o.get("visib"), "metar": o.get("rawOb", "")})
    filas.sort(key=lambda f: f["t"])
    por = {}
    for f in filas:
        if f["temp"] is None: continue
        por.setdefault(f["t"][:10], []).append(f["temp"])
    hoy = dt.datetime.now(loc).date().isoformat()
    dias = [{"fecha": d, "tmax": max(v), "tmin": min(v), "n": len(v), "completo": d < hoy and len(v) >= 12} for d, v in sorted(por.items())]
    return {"estacion": icao, "fuente": "METAR (aviationweather.gov)", "dias": dias, "horario": filas[-30:]}


SMN_BUCKET = "https://smn-ar-wrf.s3.amazonaws.com"

def _cielo(f, hora):
    fen = (f.get("fenomeno") or "").upper()
    noche = hora < 7 or hora >= 20
    if "TS" in fen: return "tormenta"
    if "SH" in fen: return "chaparron"
    if "RA" in fen: return "lluvia"
    if "DZ" in fen: return "llovizna"
    if "FG" in fen or "BR" in fen: return "niebla"
    n = f.get("nubosidad") or 0
    if n <= 1: return "luna" if noche else "sol"
    if n == 2: return "lunanube" if noche else "solnube"
    return "nube" if n == 3 else "cubierto"

def actual_de(obs):
    """Último dato medido del aeropuerto, listo para mostrar."""
    h = (obs or {}).get("horario") or []
    if not h: return None
    f = h[-1]
    t = dt.datetime.fromisoformat(f["t"])
    return {"t": f["t"], "hora": t.strftime("%H:%M"), "temp": f["temp"], "presion": f["hPa"], "humedad": f["humedad"],
            "vientoKmh": f["vientoKmh"], "vientoDir": f["vientoDir"], "nubosidad": f["nubosidad"],
            "fenomeno": f["fenomeno"] or None, "cielo": _cielo(f, t.hour),
            "fuente": f"METAR {obs['estacion']} (aeropuerto)"}

def _s3_list(prefix):
    import re
    txt = get(f"{SMN_BUCKET}/?list-type=2&max-keys=1000&prefix=" + urllib.parse.quote(prefix))
    return re.findall(r"<Key>([^<]+)</Key>", txt)

def smn_wrf(previo):
    """SMN Argentina WRF determinístico 4 km (AWS Open Data, bucket smn-ar-wrf).
    Baja la corrida más reciente completa (00 o 12 UTC), lee el punto más cercano a cada zona
    y arma máximas, mínimas, lluvia y viento por día local. Solo trabaja si hay una corrida nueva."""
    import concurrent.futures as cf
    import numpy as np, netCDF4
    ahora = dt.datetime.now(dt.timezone.utc)
    elegida = None
    for horas_atras in range(0, 60, 6):
        c = ahora - dt.timedelta(hours=horas_atras)
        if c.hour not in (0, 12) and horas_atras: 
            pass
        for hh in (12, 0):
            ini = c.replace(hour=hh, minute=0, second=0, microsecond=0)
            if ini > ahora: continue
            pref = f"DATA/WRF/DET/{ini:%Y/%m/%d/%H}/"
            claves = sorted(k for k in _s3_list(pref) if "_01H_" in k and k.endswith(".nc"))
            if len(claves) >= 49:
                elegida = (ini, claves); break
        if elegida: break
    if not elegida:
        DIAG.append("SMN WRF: no hay corrida completa"); return previo
    ini, claves = elegida
    if previo and previo.get("init") == ini.isoformat():
        DIAG.append(f"SMN WRF: sin corrida nueva ({ini:%d/%m %HZ})"); return previo
    claves = claves[:73]
    idx = {}
    nombres = {}
    def bajar(k):
        req = urllib.request.Request(f"{SMN_BUCKET}/{k}", headers={"User-Agent": "predictor-litoral"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return k, r.read()
    filas = {z: [] for z in ZONAS}
    def var(ds, cands):
        for c in cands:
            if c in ds.variables: return c
        low = {v.lower(): v for v in ds.variables}
        for c in cands:
            if c.lower() in low: return low[c.lower()]
        return None
    with cf.ThreadPoolExecutor(8) as ex:
        for k, b in ex.map(bajar, claves):
            ds = netCDF4.Dataset("m.nc", memory=b)
            if not nombres:
                nombres = {"lat": var(ds, ["lat", "XLAT", "latitude"]), "lon": var(ds, ["lon", "XLONG", "longitude"]),
                           "t": var(ds, ["T2", "t2", "T2m"]), "pp": var(ds, ["PP", "pp", "PPn", "RAINNC"]),
                           "ws": var(ds, ["magViento10", "WSPD10", "ws10"]), "wd": var(ds, ["dirViento10", "WDIR10", "wd10"]),
                           "u": var(ds, ["U10", "u10"]), "v": var(ds, ["V10", "v10"]),
                           "p": var(ds, ["SLP", "slp", "PSFC", "psfc"])}
                DIAG.append("SMN WRF variables: " + ",".join(list(ds.variables)[:40]))
                la = np.squeeze(ds.variables[nombres["lat"]][:]); lo = np.squeeze(ds.variables[nombres["lon"]][:])
                if la.ndim == 1: la, lo = np.meshgrid(la, lo, indexing="ij")
                for z, zz in ZONAS.items():
                    plat, plon = zz.get("aero", (zz["lat"], zz["lon"]))  # punto del aeropuerto: el mismo lugar que se mide
                    d2 = (la - plat) ** 2 + ((lo - plon) * np.cos(np.radians(plat))) ** 2
                    idx[z] = np.unravel_index(int(np.argmin(d2)), la.shape)
            fff = int(k.rsplit("_", 1)[1][:3])
            t = ini + dt.timedelta(hours=fff)
            if fff == 1:
                DIAG.append("SMN WRF variables h1: " + ",".join(list(ds.variables)[:40]))
            def val(n, i):
                if not n or n not in ds.variables: return None
                a = np.squeeze(ds.variables[n][:])
                x = a[i] if a.ndim == 2 else a[(0,) * (a.ndim - 2) + i]
                return float(x)
            for z in ZONAS:
                i = idx[z]
                tmp = val(nombres["t"], i)
                if tmp is not None and tmp > 150: tmp -= 273.15
                ws = val(nombres["ws"], i); wd = val(nombres["wd"], i)
                if ws is None and nombres["u"]:
                    u, v = val(nombres["u"], i), val(nombres["v"], i)
                    ws = (u * u + v * v) ** 0.5; wd = (270 - np.degrees(np.arctan2(v, u))) % 360
                filas[z].append({"t": t, "temp": tmp, "pp": val(nombres["pp"], i), "ws": ws, "wd": wd})
            ds.close()
    loc = dt.timezone(dt.timedelta(hours=-3))
    out = {"init": ini.isoformat(), "fuente": "SMN Argentina WRF 4 km (AWS smn-ar-wrf)", "zonas": {}}
    for z, ff in filas.items():
        ff.sort(key=lambda f: f["t"])
        pps = [f["pp"] for f in ff if f["pp"] is not None]
        acumulada = len(pps) > 3 and all(b >= a - 1e-6 for a, b in zip(pps, pps[1:])) and pps[-1] > pps[1] * 3
        prev = 0.0
        por = {}
        for f in ff:
            pp = f["pp"]
            if pp is not None and acumulada: pp, prev = max(0.0, pp - prev), pp
            d = f["t"].astimezone(loc).date().isoformat()
            por.setdefault(d, []).append((f["temp"], pp or 0.0, f["ws"], f["wd"]))
        dias = []
        for d, v in sorted(por.items()):
            ts = [x[0] for x in v if x[0] is not None]
            if len(ts) < 18: continue
            ws = [(x[2] or 0, x[3]) for x in v]
            wmax = max(ws, key=lambda w: w[0])
            kmh = wmax[0] * 3.6 if wmax[0] < 60 else wmax[0]
            dias.append({"fecha": d, "tmax": round(max(ts), 1), "tmin": round(min(ts), 1), "mm": round(sum(x[1] for x in v), 1),
                         "vientoKmh": round(kmh), "vientoDir": round(wmax[1]) if wmax[1] is not None else None})
        out["zonas"][z] = dias
    DIAG.append(f"SMN WRF: corrida {ini:%d/%m %HZ}, {len(claves)} horas")
    return out

CTM_EST = {"Salto": "A501258E", "Puerto Concordia": "A50012EE", "Salto Grande": "A5002774", "Federación": "A5004C40",
           "Belén": "A50B9752", "Monte Caseros": "A50C9566", "Bonpland": "A50CD66C", "Paso de los Libres": "A5004292",
           "Yapeyú": "A5001C3C", "Santo Tomé": "A500F11C", "Garruchos": "A500E26A", "El Soberbio": "A5011014"}

def ctm_estaciones(dias=8):
    """Telemetría de CTM Salto Grande (datos cada 15 min, sin validar): nivel del río y lluvia por estación."""
    import re, html as H
    loc = dt.timezone(dt.timedelta(hours=-3))
    hoy = dt.datetime.now(loc)
    out = {}
    for nom, cod in CTM_EST.items():
        try:
            q = {"estacion": cod, "desde": (hoy - dt.timedelta(days=dias)).strftime("%d/%m/%Y"), "hasta": hoy.strftime("%d/%m/%Y")}
            txt = get("https://www.saltogrande.org/datos_estacion.php?" + urllib.parse.urlencode(q))
            filas = []
            for r in re.findall(r"<tr.*?</tr>", txt, flags=re.S):
                c = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td.*?</td>", r, flags=re.S)]
                if len(c) < 2 or not re.match(r"\d\d/\d\d/\d{4} \d\d:\d\d", c[0]): continue
                t = dt.datetime.strptime(c[0], "%d/%m/%Y %H:%M").replace(tzinfo=loc)
                def num(x):
                    try: return float(x.replace(",", "."))
                    except Exception: return None
                filas.append((t, num(c[1]), num(c[2]) if len(c) > 2 else None))
            filas.sort()
            if not filas:
                DIAG.append(f"CTM {nom}: sin filas"); continue
            ult = filas[-1]
            def nivel_en(horas):
                obj = ult[0] - dt.timedelta(hours=horas)
                cand = [f for f in filas if f[1] is not None and abs((f[0] - obj).total_seconds()) <= 1800]
                return cand[0][1] if cand else None
            def lluvia(horas):
                v = [f[2] for f in filas if f[2] is not None and f[0] > ult[0] - dt.timedelta(hours=horas)]
                return round(sum(v), 1) if v else None
            horario = [{"t": f[0].isoformat(), "nivel": f[1]} for f in filas if f[0].minute == 0 and f[1] is not None][-72:]
            diario = {}
            for f in filas:
                if f[1] is None: continue
                d = f[0].date().isoformat()
                diario.setdefault(d, []).append(f[1])
            out[nom] = {"id": cod, "ultimo": {"t": ult[0].isoformat(), "nivel": ult[1], "lluvia": ult[2]},
                        "nivelHace24h": nivel_en(24), "nivelHace72h": nivel_en(72),
                        "lluvia24h": lluvia(24), "lluvia72h": lluvia(72),
                        "dias": [{"fecha": d, "max": max(v), "min": min(v), "ultimo": v[-1]} for d, v in sorted(diario.items())],
                        "horario": horario}
            DIAG.append(f"CTM {nom}: {len(filas)} datos")
        except Exception as e:
            DIAG.append(f"CTM {nom}: {e}")
    return {"generado": dt.datetime.now(dt.timezone.utc).isoformat(), "fuente": "Telemetría CTM Salto Grande (datos_estacion.php, sin validar)", "estaciones": out}

def main():
    salida = {"generado": dt.datetime.now(dt.timezone.utc).isoformat(), "zonas": {}, "errores": []}
    for nombre, z in ZONAS.items():
        zz = {}
        try:
            zz["modelos"] = modelos(z)
        except Exception as e:
            salida["errores"].append(f"modelos {nombre}: {e}"); traceback.print_exc()
        try:
            zz["observado"] = metar(z["icao"])
        except Exception as e:
            salida["errores"].append(f"metar {nombre}: {e}"); traceback.print_exc()
        zz["actual"] = actual_de(zz.get("observado"))
        salida["zonas"][nombre] = zz
    import os
    previo = None
    try:
        previo = json.load(open("data/smn.json"))
    except Exception:
        pass
    try:
        smn = smn_wrf(previo)
        if smn:
            with open("data/smn.json", "w") as f:
                json.dump(smn, f, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        smn = previo
        salida["errores"].append(f"smn: {e}"); traceback.print_exc()
    try:
        ctm = ctm_estaciones()
        with open("data/ctm.json", "w") as f:
            json.dump(ctm, f, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        ctm = None
        salida["errores"].append(f"ctm: {e}"); traceback.print_exc()
    salida["diagnostico"] = DIAG
    with open("data/latest.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
    # resumen chico para leer rápido (sin series horarias)
    res = {"generado": salida["generado"], "errores": salida["errores"], "diagnostico": DIAG, "zonas": {}}
    for z, v in salida["zonas"].items():
        mods = {k: m["dias"] for k, m in v.get("modelos", {}).items()}
        if smn and smn.get("zonas", {}).get(z):
            mods["SMN"] = smn["zonas"][z]
        res["zonas"][z] = {"modelos": mods, "observado": v.get("observado"), "actual": v.get("actual")}
    if smn: res["smnInit"] = smn.get("init")
    with open("data/resumen.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    # lo medido, en un archivo chico: último dato y máximas/mínimas por día
    med = {"generado": salida["generado"], "zonas": {}}
    for z, v in salida["zonas"].items():
        o = v.get("observado") or {}
        med["zonas"][z] = {"estacion": o.get("estacion"), "actual": v.get("actual"), "dias": o.get("dias", [])}
    if ctm:
        med["rio"] = {k: {kk: v[kk] for kk in ("ultimo", "nivelHace24h", "nivelHace72h", "lluvia24h", "lluvia72h", "dias")}
                      for k, v in ctm["estaciones"].items()}
        med["rioFuente"] = ctm["fuente"]
    with open("data/medido.json", "w") as f:
        json.dump(med, f, ensure_ascii=False, indent=1)
    print("ok", {k: list(v.get("modelos", {}).keys()) for k, v in salida["zonas"].items()}, salida["errores"])

if __name__ == "__main__":
    main()
