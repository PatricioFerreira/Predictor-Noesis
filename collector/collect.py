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
         "hourly": "pressure_msl,temperature_2m,relative_humidity_2m", "past_days": 1, "models": ",".join(MODELOS)}
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
        por = {}
        for t, hr, pr in zip(hh["time"], hh.get("relative_humidity_2m" + sfx, []), hh.get("pressure_msl" + sfx, [])):
            e = por.setdefault(t[:10], {"hr": [], "p": []})
            if hr is not None: e["hr"].append(hr)
            if pr is not None: e["p"].append(pr)
        for dd_ in dias:
            e = por.get(dd_["fecha"], {})
            dd_["humedad"] = round(sum(e["hr"]) / len(e["hr"])) if e.get("hr") and len(e["hr"]) >= 18 else None
            dd_["presionMin"] = round(min(e["p"]), 1) if e.get("p") and len(e["p"]) >= 18 else None
        out[NOMBRE[m]] = {"dias": dias}
        if m == "ecmwf_ifs025":
            out[NOMBRE[m]]["presionHoraria"] = [{"t": t, "hPa": p} for t, p in zip(hh["time"], hh.get("pressure_msl" + sfx, [])) if p is not None][:72]
    # nuestra temperatura hora a hora: promedio de los modelos disponibles en cada hora
    hh = d["hourly"]; mezcla = []
    for i, t in enumerate(hh["time"]):
        v = [hh["temperature_2m_" + m][i] for m in MODELOS if ("temperature_2m_" + m) in hh and hh["temperature_2m_" + m][i] is not None]
        pv = [hh["pressure_msl_" + m][i] for m in MODELOS if ("pressure_msl_" + m) in hh and hh["pressure_msl_" + m][i] is not None]
        if v: mezcla.append({"t": t, "temp": round(sum(v) / len(v), 1), "hPa": round(sum(pv) / len(pv), 1) if pv else None, "n": len(v)})
    out["_mezclaHoraria"] = mezcla
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
    return {"estacion": icao, "fuente": "METAR (aviationweather.gov)", "dias": dias, "horario": filas[-30:], "horario_completo": filas}


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

def ctm_estaciones(dias=8, estaciones=None, horario=True):
    """Telemetría de CTM Salto Grande (datos cada 15 min, sin validar): nivel del río y lluvia por estación."""
    import re, html as H
    loc = dt.timezone(dt.timedelta(hours=-3))
    hoy = dt.datetime.now(loc)
    out = {}
    for nom, cod in (estaciones or CTM_EST).items():
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
            horario_l = [{"t": f[0].isoformat(), "nivel": f[1]} for f in filas if f[0].minute == 0 and f[1] is not None][-72:]
            diario = {}; lluvia_d = {}
            for f in filas:
                if f[2] is not None: lluvia_d[f[0].date().isoformat()] = lluvia_d.get(f[0].date().isoformat(), 0) + f[2]
                if f[1] is None: continue
                d = f[0].date().isoformat()
                diario.setdefault(d, []).append(f[1])
            out[nom] = {"id": cod, "ultimo": {"t": ult[0].isoformat(), "nivel": ult[1], "lluvia": ult[2]},
                        "nivelHace24h": nivel_en(24), "nivelHace72h": nivel_en(72),
                        "lluvia24h": lluvia(24), "lluvia72h": lluvia(72),
                        "dias": [{"fecha": d, "max": max(v), "min": min(v), "ultimo": v[-1], "media": round(sum(v) / len(v), 2), "lluvia": round(lluvia_d.get(d, 0), 1)} for d, v in sorted(diario.items())],
                        "horario": horario_l if horario else []}
            if horario: DIAG.append(f"CTM {nom}: {len(filas)} datos")
        except Exception as e:
            DIAG.append(f"CTM {nom}: {e}")
    return {"generado": dt.datetime.now(dt.timezone.utc).isoformat(), "fuente": "Telemetría CTM Salto Grande (datos_estacion.php, sin validar)", "estaciones": out}

SYNOP = {"salto": "86360", "montevideo": "86580", "este": "86586"}

def synop(bloque, horas=54):
    """Partes SYNOP de INUMET (vía Ogimet): presión con décimas, temperatura, viento, cada 3 h, también de noche."""
    loc = dt.timezone(dt.timedelta(hours=-3))
    fin = dt.datetime.now(dt.timezone.utc); ini = fin - dt.timedelta(hours=horas)
    txt = get("https://www.ogimet.com/cgi-bin/getsynop?" + urllib.parse.urlencode(
        {"block": bloque, "begin": ini.strftime("%Y%m%d%H%M"), "end": fin.strftime("%Y%m%d%H%M")}))
    out = []
    for lin in txt.splitlines():
        c = lin.split(",")
        if len(c) < 7 or not c[1].isdigit(): continue
        t = dt.datetime(int(c[1]), int(c[2]), int(c[3]), int(c[4]), int(c[5]), tzinfo=dt.timezone.utc).astimezone(loc)
        g = c[6].replace("=", "").split()
        try:
            k = g.index(bloque)
        except ValueError:
            continue
        yyggi = g[k - 1] if k >= 1 else ""
        iw = yyggi[-1:] if yyggi else "1"
        sec = g[k + 1:]
        if "333" in sec: sec = sec[:sec.index("333")]
        f = {"t": t.isoformat()}
        if len(sec) >= 2 and len(sec[1]) == 5 and sec[1][1:3].isdigit() and sec[1][3:].isdigit():
            dd, ff = int(sec[1][1:3]) * 10, int(sec[1][3:])
            f["vientoDir"] = dd if dd <= 360 else None
            f["vientoKmh"] = round(ff * (1.852 if iw in ("3", "4") else 3.6))
        for x in sec[2:]:
            if len(x) != 5 or not x[1:].replace("/", "").isdigit() or "/" in x[1:]: continue
            if x[0] == "1" and x[1] in "01": f["temp"] = (-1 if x[1] == "1" else 1) * int(x[2:]) / 10
            elif x[0] == "2" and x[1] in "01": f["rocio"] = (-1 if x[1] == "1" else 1) * int(x[2:]) / 10
            elif x[0] == "6" and "lluvia" not in f:
                rrr, tr = int(x[1:4]), x[4]
                f["lluvia"] = 0.0 if rrr == 990 else (rrr - 990) / 10 if rrr > 990 else float(rrr)
                f["lluviaHoras"] = {"1": 6, "2": 12, "3": 18, "4": 24, "5": 1, "6": 2, "7": 3, "8": 9, "9": 15}.get(tr)
            elif x[0] == "4":
                v = int(x[1:]); f["hPa"] = round((v / 10 + 1000) if v < 5000 else v / 10, 1)
            elif x[0] == "3" and "hPa" not in f:
                v = int(x[1:]); f["hPaEstacion"] = round((v / 10 + 1000) if v < 5000 else v / 10, 1)
        if f.get("temp") is not None and f.get("rocio") is not None:
            import math
            a_, b_ = 17.625, 243.04
            f["humedad"] = round(100 * math.exp(a_ * f["rocio"] / (b_ + f["rocio"]) - a_ * f["temp"] / (b_ + f["temp"])))
        out.append(f)
    out.sort(key=lambda f: f["t"])
    DIAG.append(f"SYNOP {bloque}: {len(out)} partes")
    return out

def ctm_horario(horas=24):
    """Datos horarios de CTM: temperatura ambiente en la represa (y cota/caudales), últimas horas."""
    import re
    loc = dt.timezone(dt.timedelta(hours=-3))
    ahora = dt.datetime.now(loc).replace(minute=0, second=0, microsecond=0)
    vistos = {}
    def num(x):
        try: return float(x.replace(".", "").replace(",", ".")) if x.count(",") else float(x)
        except Exception: return None
    for h in range(horas, -1, -1):
        t = ahora - dt.timedelta(hours=h)
        try:
            s = get("https://www.saltogrande.org/datos_horarios.php?" + urllib.parse.urlencode({"fh": t.strftime("%Y-%m-%d %H:00:00")}))
        except Exception as e:
            DIAG.append(f"CTM horario {t:%H}: {e}"); continue
        m = re.search(r"(\d\d)/(\d\d)/(\d{4})\s*Hora:\s*(\d\d):(\d\d)", s)
        if not m: continue
        tt = dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=loc)
        txt = re.sub(r"<[^>]+>", "|", s)
        def campo(nombre):
            mm = re.search(nombre + r"[|\s]*([-\d.,]+)", txt)
            return num(mm.group(1)) if mm else None
        vistos[tt.isoformat()] = {"t": tt.isoformat(), "temp": campo("Temperatura Ambiente"), "embalse": campo(r"Cota del Embalse \(Promedio\)"),
                                   "restitucion": campo(r"Cota de Restituci.n \(Promedio\)"), "turbinado": campo("Caudal Turbinado"), "vertido": campo("Caudal Vertido")}
    filas = sorted(vistos.values(), key=lambda f: f["t"])
    DIAG.append(f"CTM horario: {len(filas)} horas distintas")
    return filas

def ctm_mapa():
    """Lista de estaciones de la telemetría de CTM con coordenadas."""
    import re
    s = get("https://www.saltogrande.org/mapxmlweb.php")
    est = []
    for m in re.finditer(r"<marker\s([^>]*)/?>", s):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        est.append(a)
    DIAG.append(f"CTM mapa: {len(est)} estaciones; campos {sorted(est[0].keys()) if est else []}")
    return est

def sesgos(dias=7):
    """Sesgo medio (pronosticado − medido) de los últimos días, por zona, leído del historial."""
    import csv, glob
    loc = dt.timezone(dt.timedelta(hours=-3))
    lim = (dt.datetime.now(loc) - dt.timedelta(days=dias)).strftime("%Y-%m-%d %H:%M")
    acc = {}; vistos = set()
    for ruta in sorted(glob.glob("data/historial/registro-*.csv"))[-2:]:
        for r in csv.DictReader(open(ruta)):
            if r["corrida"] < lim: continue
            clave = (r["zona"], r["corrida"][:10], r["hora_dato"])
            if clave in vistos: continue
            vistos.add(clave)
            a = acc.setdefault(r["zona"], {"t": [], "p": []})
            try: a["t"].append(float(r["temp_pronosticada"]) - float(r["temp_medida"]))
            except Exception: pass
            try: a["p"].append(float(r.get("presion_pronosticada") or "") - float(r["presion_hPa"]))
            except Exception: pass
    out = {}
    for z, a in acc.items():
        out[z] = {"temp": round(sum(a["t"]) / len(a["t"]), 2) if len(a["t"]) >= 8 else 0.0, "nTemp": len(a["t"]),
                  "presion": round(sum(a["p"]) / len(a["p"]), 2) if len(a["p"]) >= 8 else 0.0, "nPresion": len(a["p"]), "dias": dias}
    return out

def main(ligero=False):
    """ligero=True: corrida rápida (cada 15 min) que no repite lo pesado (lluvia de 77 estaciones, documentos, 24 h de la represa)."""
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
        mez = (zz.get("modelos") or {}).pop("_mezclaHoraria", [])
        zz["mezclaHoraria"] = mez
        a = zz["actual"]
        if a and a.get("temp") is not None:
            clave = a["t"][:13] + ":00"
            hit = next((m for m in mez if m["t"] == clave), None)
            if hit:
                a["previsto"] = hit["temp"]
                a["desvio"] = round(a["temp"] - hit["temp"], 1)
                a["presionPrevista"] = hit.get("hPa")
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

    loc = dt.timezone(dt.timedelta(hours=-3))
    ahora_loc = dt.datetime.now(loc)
    # --- SYNOP (presión con décimas y temperatura también de noche)
    for nombre, zz in salida["zonas"].items():
        try:
            zz["synop"] = synop(SYNOP[nombre])
        except Exception as e:
            zz["synop"] = []; salida["errores"].append(f"synop {nombre}: {e}")
        # máximas y mínimas diarias combinando METAR + SYNOP (misma estación del aeropuerto)
        o = zz.get("observado") or {}
        obs = {}
        for f in zz["synop"] + (o.get("horario_completo") or o.get("horario") or []):
            obs.setdefault(f["t"][:16], {}).update({k: v for k, v in f.items() if v is not None and k not in obs.get(f["t"][:16], {})})
        if obs:
            import math
            por = {}
            for t, f in obs.items(): por.setdefault(t[:10], []).append((t, f))
            hoy = ahora_loc.date().isoformat()
            dias_m = []
            for d, lst in sorted(por.items()):
                tv = [f["temp"] for _, f in lst if f.get("temp") is not None]
                if not tv: continue
                ws = [f["vientoKmh"] for _, f in lst if f.get("vientoKmh") is not None]
                vx = [(f["vientoKmh"], f["vientoDir"]) for _, f in lst if f.get("vientoKmh") and f.get("vientoDir") is not None]
                hr = [f["humedad"] for _, f in lst if f.get("humedad") is not None]
                pr = [f["hPa"] for _, f in lst if f.get("hPa") is not None]
                ll = {}
                for _, f in lst:
                    if f.get("lluvia") is not None and f.get("lluviaHoras"): ll.setdefault(f["lluviaHoras"], []).append(f["lluvia"])
                mm = round(sum(ll[6]), 1) if len(ll.get(6, [])) >= 4 else round(sum(ll[12]), 1) if len(ll.get(12, [])) >= 2 else (ll[24][-1] if ll.get(24) else None)
                if vx:
                    u = sum(w * math.sin(math.radians(a)) for w, a in vx); v = sum(w * math.cos(math.radians(a)) for w, a in vx)
                    dmean = round(math.degrees(math.atan2(u, v)) % 360)
                else: dmean = None
                noche = any(t[11:13] in ("03", "04", "05", "06", "07") for t, _ in lst)
                dias_m.append({"fecha": d, "tmax": max(tv), "tmin": min(tv), "n": len(tv), "completo": d < hoy and len(tv) >= 12 and noche,
                               "mm": mm, "vientoKmh": max(ws) if ws else None, "vientoDir": dmean,
                               "humedad": round(sum(hr) / len(hr)) if len(hr) >= 6 else None, "presionMin": min(pr) if len(pr) >= 4 else None})
            if nombre == "salto" and ctm:
                pl = {x["fecha"]: x.get("lluvia") for x in ctm["estaciones"].get("Salto", {}).get("dias", [])}
                for x in dias_m:
                    if x["fecha"] in pl and pl[x["fecha"]] is not None: x["mm"] = pl[x["fecha"]]; x["mmFuente"] = "pluviómetro CTM Salto"
            o["dias"] = dias_m
        # dato actual: si el METAR es viejo, completar con el SYNOP más nuevo
        a = zz.get("actual")
        sy = [f for f in zz["synop"] if f.get("hPa") is not None]
        if a and sy:
            ult = sy[-1]
            if ult["t"] >= a["t"]:
                a["presion"] = ult["hPa"]
                if ult.get("temp") is not None and ult["t"] > a["t"]:
                    a.update({"t": ult["t"], "hora": ult["t"][11:16], "temp": ult["temp"], "fuente": f"SYNOP {SYNOP[nombre]} (INUMET)"})
            elif abs((dt.datetime.fromisoformat(a["t"]) - dt.datetime.fromisoformat(ult["t"])).total_seconds()) <= 3 * 3600:
                a["presionSynop"] = ult["hPa"]
        o.pop("horario_completo", None)
        if a and a.get("presionPrevista") is not None and a.get("presion") is not None:
            a["desvioPresion"] = round(a["presion"] - a["presionPrevista"], 1)
    # --- corrección por sesgo (aprendida del historial) y pronóstico horario corregido
    SES = sesgos()
    for nombre, zz in salida["zonas"].items():
        b = SES.get(nombre, {"temp": 0.0, "presion": 0.0})
        zz["sesgo"] = b
        fut = [m for m in zz.get("mezclaHoraria", []) if m["t"] >= ahora_loc.strftime("%Y-%m-%dT%H:00")][:48]
        zz["horariaCorregida"] = [{"t": m["t"], "temp": round(m["temp"] - b["temp"], 1),
                                   "hPa": round(m["hPa"] - b["presion"], 1) if m.get("hPa") is not None else None} for m in fut]
        a = zz.get("actual")
        if a and a.get("previsto") is not None:
            a["previstoCorregido"] = round(a["previsto"] - b["temp"], 1)
    # --- represa: temperatura ambiente horaria
    try:
        rep = ctm_horario(3 if ligero else 24)
    except Exception as e:
        rep = []; salida["errores"].append(f"ctm horario: {e}")
    # --- lluvia medida en toda la cuenca (telemetría CTM)
    cuenca = None
    try:
        if ligero: raise RuntimeError("ligero")
        mapa = ctm_mapa()
        otros = {}
        for m in mapa:
            nom = m.get("nombre") or m.get("name"); cod = m.get("address") or m.get("id")
            if nom and cod and nom not in CTM_EST: otros[nom] = cod
        ll = ctm_estaciones(3, otros, horario=False)["estaciones"]
        coords = {(m.get("nombre") or m.get("name")): (m.get("lat"), m.get("lng")) for m in mapa}
        ests = []
        for nom, v in {**(ctm["estaciones"] if ctm else {}), **ll}.items():
            if v.get("lluvia72h") is None: continue
            la, lo = coords.get(nom, (None, None))
            ests.append({"n": nom, "lat": float(la) if la else None, "lon": float(lo) if lo else None,
                         "lluvia24h": v["lluvia24h"], "lluvia72h": v["lluvia72h"], "t": v["ultimo"]["t"]})
        if ests:
            l24 = [e["lluvia24h"] or 0 for e in ests]; l72 = [e["lluvia72h"] or 0 for e in ests]
            cuenca = {"n": len(ests), "promedio24h": round(sum(l24) / len(l24), 1), "promedio72h": round(sum(l72) / len(l72), 1),
                      "max72h": max(ests, key=lambda e: e["lluvia72h"] or 0), "estaciones": sorted(ests, key=lambda e: -(e["lluvia72h"] or 0))}
    except Exception as e:
        if str(e) != "ligero": salida["errores"].append(f"cuenca: {e}"); traceback.print_exc()
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
        med["zonas"][z] = {"estacion": o.get("estacion"), "actual": v.get("actual"), "dias": o.get("dias", []),
                           "synop": [{k: f.get(k) for k in ("t", "temp", "hPa")} for f in v.get("synop", [])],
                           "sesgo": v.get("sesgo"), "horariaCorregida": v.get("horariaCorregida", [])[:24]}
    if rep:
        ur = [f for f in rep if f.get("temp") is not None]
        dd = {}
        for f in ur: dd.setdefault(f["t"][:10], []).append(f["temp"])
        med["zonas"]["salto"]["represa"] = {"fuente": "CTM Salto Grande, temperatura ambiente en la represa",
            "ultimo": ur[-1] if ur else None, "horario": [{"t": f["t"], "temp": f["temp"]} for f in ur],
            "dias": [{"fecha": d, "tmax": max(v), "tmin": min(v), "n": len(v)} for d, v in sorted(dd.items())]}
    if cuenca:
        med["cuencaLluvia"] = {k: cuenca[k] for k in ("n", "promedio24h", "promedio72h", "max72h")}
        med["cuencaLluvia"]["top"] = cuenca["estaciones"][:15]
    if ctm:
        med["rio"] = {k: {kk: v[kk] for kk in ("ultimo", "nivelHace24h", "nivelHace72h", "lluvia24h", "lluvia72h", "dias")}
                      for k, v in ctm["estaciones"].items()}
        med["rioFuente"] = ctm["fuente"]
    with open("data/medido.json", "w") as f:
        json.dump(med, f, ensure_ascii=False, indent=1)

    # --- historial permanente (planillas mensuales, no se borran)
    import csv, os
    os.makedirs("data/historial", exist_ok=True)
    mes = ahora_loc.strftime("%Y-%m")
    def append(nombre, cab, filas):
        ruta = f"data/historial/{nombre}-{mes}.csv"; nuevo = not os.path.exists(ruta)
        with open(ruta, "a", newline="") as f:
            w = csv.writer(f)
            if nuevo: w.writerow(cab)
            w.writerows(filas)
    filas = []
    for z, v in salida["zonas"].items():
        a = v.get("actual") or {}
        rio = ((ctm or {}).get("estaciones", {}).get("Salto", {}).get("ultimo", {}) or {}).get("nivel") if z == "salto" else ""
        rt = (rep[-1].get("temp") if rep else "") if z == "salto" else ""
        filas.append([ahora_loc.strftime("%Y-%m-%d %H:%M"), z, a.get("hora", ""), a.get("temp", ""), a.get("previsto", ""), a.get("desvio", ""),
                      a.get("presion", ""), a.get("presionPrevista", ""), a.get("desvioPresion", ""), a.get("humedad", ""), a.get("vientoKmh", ""), a.get("vientoDir", ""), rio, rt, a.get("fuente", "")])
    append("registro", ["corrida", "zona", "hora_dato", "temp_medida", "temp_pronosticada", "desvio", "presion_hPa", "presion_pronosticada", "desvio_presion", "humedad", "viento_kmh",
                        "viento_dir", "rio_puerto_m", "temp_represa", "fuente"], filas)
    # --- verificación por variable, pronóstico propio ponderado y fotos diarias
    import sys as _s; _s.path.insert(0, os.path.dirname(__file__)); import verif as V
    try:
        inu, inu_pub = V.inumet(get)
    except Exception as e:
        inu, inu_pub = {}, None; salida["errores"].append(f"inumet: {e}")
    V.guardar_medido(ahora_loc, med["zonas"])
    ver = V.verificar(ahora_loc)
    mods = {z: v["modelos"] for z, v in res["zonas"].items()}
    nuestro = V.mezclar(mods, inu, ver, ahora_loc.date().isoformat())
    if 20 <= ahora_loc.hour <= 22:
        V.guardar_foto(ahora_loc, mods, inu, nuestro)
    res["inumet"] = {"publicado": inu_pub, "zonas": inu}
    res["verificacion"] = ver
    res["nuestro"] = nuestro
    with open("data/resumen.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    try:
        import tablero as T, documentos as DOC
        docs = {} if ligero else DOC.todos(salida["errores"])
        parche = T.armar(ahora_loc, ZONAS, res, med, rep, ctm, cuenca, nuestro, ver, inu, salida["errores"], docs)
        with open("data/tablero.json", "w") as f:
            json.dump(parche, f, ensure_ascii=False, separators=(",", ":"))
        # documento completo para la página web (GitHub Pages): base persistente + parche
        import fusionar as FU
        FU.main("data/base.json", "data/tablero.json", "data/completo.json")
        import shutil; shutil.copy("data/completo.json", "data/base.json")
    except Exception as e:
        salida["errores"].append(f"tablero: {e}"); traceback.print_exc()
    with open("data/verificacion.json", "w") as f:
        json.dump({"generado": salida["generado"], "ventanaDias": 30, "minimoN": V.MIN_N, "zonas": ver}, f, ensure_ascii=False, indent=1)
    print("ok", {k: list(v.get("modelos", {}).keys()) for k, v in salida["zonas"].items()}, salida["errores"])

if __name__ == "__main__":
    main()
