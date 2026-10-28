"""Lectura automática (sin IA) de los documentos que antes leía Claude:
- CTM Salto Grande: Comunicado.pdf y CaudalesNiveles.pdf
- Serviço Geológico do Brasil: boletín de alerta de la cuenca del río Uruguay (PDF)
- NOAA CPC: El Niño (índices semanales de temperatura del Pacífico, ONI, SOI y discusión mensual)
"""
import io, re, html, datetime as dt, urllib.request

H = {"User-Agent": "Mozilla/5.0 (predictor-noesis; github.com/PatricioFerreira/Predictor-Noesis)"}
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _bytes(url, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as r:
        return r.read()


def _pdf_texto(b, paginas=None):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(b)) as p:
        pags = p.pages if paginas is None else p.pages[:paginas]
        return "\n".join((pg.extract_text() or "") for pg in pags)


def _num(x):
    return float(x.replace(".", "").replace(",", ".")) if re.search(r"\d,\d", x) else float(x)


# ---------- CTM ----------
def comunicado():
    t = _pdf_texto(_bytes("https://www.saltogrande.org/docs/hidrologia/Comunicado.pdf"))
    out = {}
    m = re.search(r"COMUNICADO FECHA:\s*(\d\d)/(\d\d)/(\d{4})", t)
    fecha = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    g = lambda pat: (re.search(pat, t) or [None, None])[1]
    ap = g(r"Aporte últimas 24hs \(m³/s\)\s*([\d.]+)")
    ev = g(r"Evacuado a la hora [\d:]+ \(m³/s\)\s*([\d.]+)")
    emb = g(r"Nivel del embalse hora [\d:]+ \(m\)\s*([\d.,]+)")
    rango = re.search(r"variará entre ([\d.]+) y ([\d.]+) m³/s", t)
    puertos = re.search(r"Concordia y Salto no superarán los valores de ([\d,\.]+) y ([\d,\.]+) metros", t)
    obj = g(r"embalse tenderá a ([\d,\.]+) m")
    hora = g(r"Hasta la hora (\d\d:\d\d) de mañana")
    represa = {}
    if ap: represa["aporte24h"] = int(ap.replace(".", ""))
    if ev: represa["descarga24h"] = int(ev.replace(".", ""))
    if emb: represa["embalseComunicado"] = _num(emb)
    if obj: represa["embalseObjetivo"] = _num(obj)
    if rango:
        a, b = sorted([int(rango.group(1).replace(".", "")), int(rango.group(2).replace(".", ""))])
        represa["descargaPrevista"] = f"{a:,}–{b:,}".replace(",", ".")
    represa["vertedero"] = "abierto" if "Vertedero Abierto" in t else "cerrado" if "Vertedero Cerrado" in t else None
    out["represa"] = represa
    if puertos and fecha:
        man = fecha + dt.timedelta(days=1)
        out["pronostico"] = {"max": _num(puertos.group(2)), "maxConcordia": _num(puertos.group(1)),
                             "hasta": f"{DIAS[man.weekday()]} {man.day} · {hora or '15:00'}", "fuente": "CTM Salto Grande (comunicado del " + fecha.strftime("%d/%m") + ")"}
    return out


def caudales_niveles():
    t = _pdf_texto(_bytes("https://www.saltogrande.org/docs/hidrologia/CaudalesNiveles.pdf"))
    m = re.search(r"observados a las (\d\d:\d\d)hs de día (\d\d/\d\d)/\d{4}", t)
    secciones = re.split(r"\n(?=Volumenes|Caudales Medios|Caudales Hora|Salto Grande - Erogado|Niveles Hora)", t)
    dias, q, niv = [], {}, {}
    for s in secciones:
        lineas = s.splitlines()
        fechas = re.findall(r"(\d\d/\d\d)/\d{4}", lineas[1] if len(lineas) > 1 else "")
        if fechas and not dias: dias = fechas
        destino = q if s.startswith("Caudales Hora") else niv if s.startswith("Niveles Hora") else None
        if destino is None: continue
        for ln in lineas[2:]:
            mm = re.match(r"^([A-Za-zÁÉÍÓÚáéíóúñÑ .]+?)\s+([\d.\s]+)$", ln.strip())
            if not mm: continue
            vals = [float(v) for v in mm.group(2).split()]
            destino[mm.group(1).strip()] = vals
    orden = ["El Soberbio", "San Javier", "Garruchos", "Santo Tomé", "Alvear", "Paso de los Libres", "Concordia"]
    est = []
    for n in orden:
        if n not in niv and n not in q: continue
        e = {"n": "Concordia (puerto)" if n == "Concordia" else n, "niv": niv.get(n, [])}
        if n in q: e["q"] = [int(v) for v in q[n]]
        est.append(e)
    return {"fuente": "CTM Salto Grande · Reporte de caudales y niveles", "fecha": f"{m.group(2)} {m.group(1)}" if m else "",
            "dias": dias, "estaciones": est, "aporte": [int(v) for v in q.get("Aporte", [])]}


# ---------- Serviço Geológico do Brasil ----------
SGB_EST = [("Iraí", "Iraí"), ("Itapiranga", "Itapiranga"), ("Alto Uruguai", "Alto Uruguai"), ("Porto Mauá", "Porto Mauá"),
           ("Porto Lucena", "Porto Lucena"), ("Garruchos", "Garruchos"), ("São Borja", "Passo São Borja"), ("Itaqui", "Itaqui"), ("Uruguaiana", "Uruguaiana")]


def sgb():
    """Primero la telemetría del visor SACE (sace.sgb.gov.br); si falla, el boletín PDF de siempre."""
    errs = []
    try:
        import sace
        return sace.niveles(errs)
    except Exception as e:
        print("sace:", e, errs)
    return sgb_pdf()


def sgb_pdf():
    t = _pdf_texto(_bytes("https://www.sgb.gov.br/sace/uruguai/ultimo_boletim.php"), paginas=1)
    m = re.search(r"Data de referência dos dados neste boletim:\s*(\d\d)/(\d\d)/\d{4} (\d\d:\d\d)", t)
    est = []
    for nombre, clave in SGB_EST:
        ln = next((l for l in t.splitlines() if re.search(r"(^|\s)" + re.escape(clave) + r" Uruguai ", l)), None)
        if not ln: continue
        mm = re.search(r" Uruguai .*?\s(\d+,\d|-)\s+(\d+|#|-)\s+(\d+|#|-)\s*(?:(\d+)\s*([▼▲►]))?", ln)
        if not mm: continue
        e = {"n": nombre}
        if mm.group(2).isdigit(): e["nivel"] = int(mm.group(2))
        if mm.group(3).isdigit(): e["inund"] = int(mm.group(3))
        if mm.group(4):
            e["prev"] = int(mm.group(4)); e["tend"] = {"▼": "baja", "▲": "sube", "►": "estable"}.get(mm.group(5))
        if nombre == "Iraí": e["km"] = 0
        est.append(e)
    return {"fuente": "SGB · Boletín de Alerta Hidrológico", "fecha": f"{m.group(1)}/{m.group(2)} {m.group(3)}" if m else "", "estaciones": est}


# ---------- NOAA: El Niño ----------
MESES = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def enso():
    txt = _bytes("https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for").decode("latin-1")
    filas = []
    for ln in txt.splitlines():
        m = re.match(r"\s*(\d\d)([A-Z]{3})(\d{4})\s+([\d.]+)\s*([-\d.]+)\s+([\d.]+)\s*([-\d.]+)\s+([\d.]+)\s*([-\d.]+)\s+([\d.]+)\s*([-\d.]+)", ln)
        if m:
            f = dt.date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
            filas.append({"f": f.isoformat(), "n12": float(m.group(5)), "n3": float(m.group(7)), "n34": float(m.group(9)), "n4": float(m.group(11))})
    ult = filas[-1]
    oni = None
    try:
        o = _bytes("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt").decode("latin-1").strip().splitlines()[-1].split()
        oni = {"periodo": f"{o[0]} {o[1]}", "valor": float(o[3])}
    except Exception:
        pass
    soi = None
    try:
        s = _bytes("https://www.cpc.ncep.noaa.gov/data/indices/soi").decode("latin-1")
        anios = [l for l in s.splitlines() if re.match(r"^\d{4}", l)]
        for l in reversed(anios):
            vals = [float(x) for x in re.findall(r"-?\d+\.\d", l[4:])]
            buenos = [v for v in vals if v > -99]
            if buenos:
                soi = {"valor": buenos[-1], "mes": len(buenos), "anio": int(l[:4])}; break
    except Exception:
        pass
    disc = {}
    try:
        h = _bytes("https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml").decode("utf-8", "replace")
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
        m = re.search(r"issued by CLIMATE PREDICTION CENTER/NCEP/NWS (\d{1,2} \w+ \d{4})", t)
        if m:
            d_, mo, y_ = m.group(1).split()
            mes_es = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril", "May": "mayo", "June": "junio", "July": "julio",
                      "August": "agosto", "September": "setiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
            disc["fecha"] = f"{d_} de {mes_es.get(mo, mo)} de {y_}"
        m = re.search(r"ENSO Alert System Status: ([^:]+?) Synopsis: (.+?)(?= El Niño strengthened| La Niña| ENSO-neutral is| \S+ (?:strengthened|weakened))", t)
        if m: disc["estado"], disc["sinopsis"] = m.group(1).strip(), m.group(2).strip()
        pc = re.findall(r"(\d+)% (?:chance )?for ([A-Z][a-z]+-[A-Z][a-z]+)", t)
        if pc: disc["probabilidades"] = [{"p": int(a), "periodo": b} for a, b in pc[:4]]
        mes = {"January": "ene", "February": "feb", "March": "mar", "April": "abr", "May": "may", "June": "jun", "July": "jul", "August": "ago",
               "September": "set", "October": "oct", "November": "nov", "December": "dic"}
        def per(x): return "–".join(mes.get(w, w) for w in x.split("-"))
        for pr in disc.get("probabilidades", []): pr["periodo"] = per(pr["periodo"])
        m1 = re.search(r"likely through ([A-Z][a-z]+-[A-Z][a-z]+ \d{4})", disc.get("sinopsis", ""))
        m2 = re.search(r"(\d+)% chance", disc.get("sinopsis", ""))
        fuerte = "fuerte a muy fuerte" if "strong-to-very strong" in disc.get("sinopsis", "") else "fuerte" if "strong" in disc.get("sinopsis", "") else ""
        if m1:
            p_ = m1.group(1).split(); disc["resumen"] = (f"NOAA prevé que siga {('un El Niño ' + fuerte) if fuerte else 'el fenómeno'} hasta {per(p_[0])} {p_[1]}"
                                                        + (f" (probabilidad mayor al {m2.group(1)} %)." if m2 else "."))
        disc["estadoEs"] = {"El Niño Advisory": "Aviso de El Niño", "La Niña Advisory": "Aviso de La Niña", "El Niño Watch": "Vigilancia de El Niño",
                            "La Niña Watch": "Vigilancia de La Niña", "Not Active": "Sin alerta", "Final El Niño Advisory": "Fin de El Niño",
                            "Final La Niña Advisory": "Fin de La Niña"}.get(disc.get("estado", ""), disc.get("estado", ""))
    except Exception:
        pass
    n34 = ult["n34"]
    estado = "El Niño" if n34 >= 0.5 else "La Niña" if n34 <= -0.5 else "Neutral"
    fuerza = "muy fuerte" if abs(n34) >= 2 else "fuerte" if abs(n34) >= 1.5 else "moderado" if abs(n34) >= 1 else "débil" if abs(n34) >= 0.5 else ""
    sem = dt.date.fromisoformat(ult["f"])
    def c1(v): return f"{v:+.1f}".replace(".", ",")
    out = {"fuente": "NOAA (Centro de Predicción Climática)", "estado": estado, "fuerza": fuerza,
           "fecha": sem.strftime("%d/%m/%Y"), "nino34": n34, "nino12": ult["n12"], "nino3": ult["n3"], "nino4": ult["n4"],
           "serie34": [{"f": r["f"], "v": r["n34"], "v12": r["n12"]} for r in filas[-26:]],
           "oni": oni, "soi": soi, "discusion": disc,
           "explica": (f"El Niño es el calentamiento del océano Pacífico ecuatorial. En el centro del Pacífico (región Niño 3.4, la que se usa para declararlo) "
                       f"el agua está {c1(n34)} °C respecto de lo normal, y frente a Perú y Ecuador (Niño 1+2) {c1(ult['n12'])} °C. Dato de la semana del {sem:%d/%m}.")}
    if estado == "El Niño":
        out["efecto"] = ("Para Uruguay y el sur de Brasil, El Niño suele traer más lluvia de lo normal en primavera y verano, y por eso más riesgo de crecidas del río Uruguay."
                         + (" Con un evento de esta intensidad, la probabilidad de esos efectos es alta, aunque no segura." if abs(n34) >= 1.5 else ""))
    elif estado == "La Niña":
        out["efecto"] = "Para Uruguay, La Niña suele traer menos lluvia de lo normal en primavera y verano, con riesgo de sequía y río bajo."
    else:
        out["efecto"] = "Sin El Niño ni La Niña, el clima de la temporada depende más de otros factores; no hay un sesgo claro hacia más o menos lluvia."
    return out


BR_SACE_ID = {"Manoel Viana": 30, "Quaraí": 27, "Iraí": 37, "Porto Mauá": 56, "Garruchos BR": 34, "Itaqui": 32}
BR_CACHE = "data/brasil-reciente.json"


def brasil_serie():
    """Últimos 6-7 días de las estaciones de Brasil que usa el modelo del río, promedio por hora (cm, hora local).
    Primero la telemetría de la ANA; para las estaciones que falten, el visor SACE del SGB (mismos sensores).
    Se guarda en data/brasil-reciente.json para las corridas livianas."""
    import json, historia_ana as HA, ajustar_rio as AR
    series, fuente = {}, {}
    try:
        crudo = HA.niveles_recientes(7, {k: HA.ESTACIONES[k] for k in AR.BR})
    except Exception as e:
        print("brasil ANA:", e); crudo = {}
    for k in AR.BR:
        if len(crudo.get(k, [])) >= 300: series[k] = crudo[k]; fuente[k] = "ANA"
    faltan = [k for k in AR.BR if k not in series]
    if faltan:
        try:
            import sace
            ses = sace._Sesion()
            for k in faltan:
                try:
                    filas, _ = sace._tabla(ses.ver_dados(BR_SACE_ID[k], 168))
                    loc = [(t.astimezone(sace.UTC3).replace(tzinfo=None), v) for t, v in filas]
                    if len(loc) >= 300: series[k] = loc; fuente[k] = "SGB"
                except Exception as e:
                    print("brasil SACE", k, e)
        except Exception as e:
            print("brasil SACE:", e)
    horario = {}
    for k, filas in series.items():
        h = {}
        for t, v in filas: h.setdefault(t.strftime("%Y-%m-%dT%H"), []).append(v)
        horario[k] = {x: round(sum(v) / len(v), 1) for x, v in h.items()}
    out = {"generado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="minutes"), "fuente": fuente, "horario": horario}
    json.dump(out, open(BR_CACHE, "w"), ensure_ascii=False)
    return out


def todos(errores):
    res = {}
    for nombre, fn in (("comunicado", comunicado), ("ctm", caudales_niveles), ("sgb", sgb), ("enso", enso), ("brasil", brasil_serie)):
        try:
            res[nombre] = fn()
        except Exception as e:
            errores.append(f"{nombre}: {e}"); print(f"documentos {nombre}: {e}")
    return res
