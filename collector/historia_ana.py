"""Historia de niveles de estaciones brasileñas de la cuenca del Uruguay desde la telemetría de la ANA.

Uso: python collector/historia_ana.py [meses]   (por defecto 12)
Salida: data/historial/ana-niveles-horario.csv (t local UTC-3, nivel en cm, promedio por hora)
Un pedido por estación y por mes, con pausas.
"""
import os, sys, csv, re, time, datetime as dt, urllib.request, urllib.parse

UA = {"User-Agent": "Mozilla/5.0 (predictor-noesis; github.com/PatricioFerreira/Predictor-Noesis)"}
SALIDA = "data/historial/ana-niveles-horario.csv"
LOG = "data/historial/ana-historia-log.txt"
# nombre -> código de telemetría ANA (código de la estación + "0")
ESTACIONES = {"Iraí": "74100000", "Itapiranga": "74329000", "Alto Uruguai": "74500000", "Porto Mauá": "74720000",
              "Porto Lucena": "74800000", "Garruchos BR": "75550000", "São Borja": "75780000", "Itaqui": "75900000",
              "Manoel Viana": "76560000", "Passo Mariano Pinto": "76800000", "Uruguaiana": "77150000", "Quaraí": "77500000"}


def bajar(cod, ini, fin):
    q = {"codEstacao": cod, "dataInicio": ini.strftime("%d/%m/%Y"), "dataFim": fin.strftime("%d/%m/%Y")}
    url = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?" + urllib.parse.urlencode(q)
    for intento in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                t = r.read().decode("utf-8", "replace")
            break
        except Exception as e:
            print("  reintento", cod, intento, e, flush=True); time.sleep(15)
    else:
        return []
    filas = []
    for dh, resto in re.findall(r"<DataHora>([^<]*)</DataHora>(.*?)(?=<DataHora>|$)", t, re.S):
        nv = re.search(r"<Nivel>([^<]*)</Nivel>", resto)
        if not nv or not nv.group(1).strip(): continue
        try:
            filas.append((dt.datetime.strptime(dh.strip()[:16], "%Y-%m-%d %H:%M"), float(nv.group(1))))
        except ValueError:
            continue
    return filas


def niveles_recientes(dias=6, estaciones=None):
    """Últimos días por estación: {nombre: [(datetime local, cm), ...]} (para el recolector)."""
    hoy = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    out = {}
    for nom, cod in (estaciones or ESTACIONES).items():
        out[nom] = sorted(bajar(cod, hoy - dt.timedelta(days=dias), hoy + dt.timedelta(days=1)))
    return out


def main(meses=12):
    log = open(LOG, "w")
    def p(*x):
        print(*x, flush=True); print(*x, file=log, flush=True)
    hoy = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    serie = {}
    for nom, cod in ESTACIONES.items():
        n, fin = 0, hoy + dt.timedelta(days=1)
        for m in range(meses):
            ini = fin - dt.timedelta(days=30)
            f = bajar(cod, ini, fin)
            n += len(f)
            for t, v in f:
                serie.setdefault(t.replace(minute=0), {}).setdefault(nom, []).append(v)
            fin = ini
            time.sleep(1.5)
        p(f"{nom} ({cod}): {n} datos")
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    cols = list(ESTACIONES)
    with open(SALIDA, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t"] + cols)
        for t in sorted(serie):
            d = serie[t]
            w.writerow([t.strftime("%Y-%m-%dT%H:00")] + [round(sum(d[k]) / len(d[k]), 1) if k in d else "" for k in cols])
    p("filas", len(serie), "desde", min(serie) if serie else None)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
