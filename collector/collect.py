"""Recolector del Predictor del Litoral.
Corre en GitHub Actions cada 3 horas y deja data/latest.json con:
- modelos: pronóstico diario y presión horaria de varios modelos (vía Open-Meteo) para Salto, Montevideo y el Este
- observado: máximas, mínimas y lluvia de los últimos días en estaciones sinópticas (NOAA ISD)
El tablero (https://claude.ai/artifact/NmUMC1ftYmnFYfr9grZAFw) lo lee en cada actualización.
"""
import json, datetime as dt, urllib.request, urllib.parse, csv, io, sys, traceback

TZ = "America/Montevideo"
DIAG = []
ZONAS = {
    "salto":      {"lat": -31.383, "lon": -57.967, "isd": ["86360099999"], "icao": "SUSO"},  # Salto (Nueva Hespérides)
    "montevideo": {"lat": -34.880, "lon": -56.180, "isd": ["86580099999", "86585099999"], "icao": "SUMU"},  # Carrasco
    "este":       {"lat": -34.940, "lon": -54.960, "isd": ["86586099999"], "icao": "SULS"},  # Laguna del Sauce
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
        filas.append({"t": t.isoformat(), "temp": o.get("temp"), "hPa": o.get("altim"), "vientoKmh": round(o["wspd"] * 1.852) if isinstance(o.get("wspd"), (int, float)) else None,
                      "vientoDir": o.get("wdir") if isinstance(o.get("wdir"), (int, float)) else None})
    filas.sort(key=lambda f: f["t"])
    por = {}
    for f in filas:
        if f["temp"] is None: continue
        por.setdefault(f["t"][:10], []).append(f["temp"])
    hoy = dt.datetime.now(loc).date().isoformat()
    dias = [{"fecha": d, "tmax": max(v), "tmin": min(v), "n": len(v), "completo": d < hoy and len(v) >= 12} for d, v in sorted(por.items())]
    return {"estacion": icao, "fuente": "METAR (aviationweather.gov)", "dias": dias, "horario": filas[-30:]}

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
        try:
            zz["synop"] = observado(z["isd"])
        except Exception as e:
            salida["errores"].append(f"synop {nombre}: {e}")
        salida["zonas"][nombre] = zz
    salida["diagnostico"] = DIAG
    with open("data/latest.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
    # resumen chico para leer rápido (sin series horarias)
    res = {"generado": salida["generado"], "errores": salida["errores"], "diagnostico": DIAG, "zonas": {}}
    for z, v in salida["zonas"].items():
        res["zonas"][z] = {"modelos": {k: m["dias"] for k, m in v.get("modelos", {}).items()},
                           "observado": v.get("observado"), "synop": v.get("synop")}
    with open("data/resumen.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    print("ok", {k: list(v.get("modelos", {}).keys()) for k, v in salida["zonas"].items()}, salida["errores"])

if __name__ == "__main__":
    main()
