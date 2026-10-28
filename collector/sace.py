"""Niveles del río Uruguay en Brasil desde el visor SACE del Serviço Geológico do Brasil (sace.sgb.gov.br/uruguai).

Desde fines de octubre de 2026 el boletín en PDF (www.sgb.gov.br/sace/uruguai/ultimo_boletim.php) dejó de estar
accesible desde afuera por una manutenção de segurança cibernética; los boletines se mandan por mail.
El visor público sigue mostrando la telemetría cada 15 min. Este módulo hace la misma consulta que el botón
"Ver dados" del visor (RelatorioService.gerarRelatorioVerDados, últimas 24 h) para unas pocas estaciones.
Sin navegador: llamadas DWR "plaincall" por HTTP, una sesión por corrida.
"""
import re, html, random, string, datetime as dt, urllib.request, urllib.parse, http.cookiejar

BASE = "https://sace.sgb.gov.br/uruguai"
UA = "Mozilla/5.0 (predictor-noesis; github.com/PatricioFerreira/Predictor-Noesis)"
# nombre en el tablero -> id del punto de monitoreo en el SACE
ESTACIONES = [("Iraí", 37), ("Itapiranga", 36), ("Alto Uruguai", 57), ("Porto Mauá", 56), ("Porto Lucena", 35),
              ("Garruchos", 34), ("São Borja", 33), ("Itaqui", 32), ("Uruguaiana", 29)]
UTC3 = dt.timezone(dt.timedelta(hours=-3))


def _js_str(s):
    """Decodifica un literal de string de JavaScript (sin las comillas)."""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "u":
                out.append(chr(int(s[i + 2:i + 6], 16))); i += 6; continue
            if n == "x":
                out.append(chr(int(s[i + 2:i + 4], 16))); i += 4; continue
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(n, n)); i += 2; continue
        out.append(c); i += 1
    return "".join(out)


class _Sesion:
    def __init__(self, timeout=60):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.timeout = timeout
        self.batch = 0
        self.http_id = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        self.script_id = ""
        self.op.open(urllib.request.Request(BASE + "/", headers={"User-Agent": UA}), timeout=timeout).read()
        jid = next((c.value for c in self.cj if c.name == "JSESSIONID"), None)
        if jid: self.http_id = jid
        r = self._post("__System", "pageLoaded", [])
        m = re.search(r'handleNewScriptSession\("([^"]+)"\)', r)
        if m: self.script_id = m.group(1)
        self._post("LoginService", "setTimeZone", ["string:GMT%2B0"])  # horas de la tabla en UTC

    def _post(self, svc, met, params):
        lineas = ["callCount=1", "windowName=", f"c0-scriptName={svc}", f"c0-methodName={met}", "c0-id=0"]
        lineas += [f"c0-param{i}={p}" for i, p in enumerate(params)]
        lineas += [f"batchId={self.batch}", "page=%2Furuguai%2F", f"httpSessionId={self.http_id}", f"scriptSessionId={self.script_id}", ""]
        self.batch += 1
        req = urllib.request.Request(f"{BASE}/dwr/call/plaincall/{svc}.{met}.dwr", data="\n".join(lineas).encode(),
                                     headers={"User-Agent": UA, "Content-Type": "text/plain", "Cookie": f"DWRSESSIONID={self.http_id}"})
        return self.op.open(req, timeout=self.timeout).read().decode("utf-8", "replace")

    def ver_dados(self, id_pm, horas=24):
        r = self._post("RelatorioService", "gerarRelatorioVerDados", ["string:t", f"number:{horas}", f"number:{id_pm}"])
        if "handleException" in r or "handleBatchException" in r:
            raise RuntimeError(re.sub(r"\s+", " ", r)[:200])
        m = re.search(r'handleCallback\("[^"]*","[^"]*","(.*)"\);', r, re.S)
        if not m: raise RuntimeError("respuesta inesperada: " + r[:160])
        return _js_str(m.group(1))


def _num(x):
    x = x.strip().replace(".", "").replace(",", ".")
    return float(x) if re.fullmatch(r"-?\d+(\.\d+)?", x) else None


def _tabla(h):
    """Devuelve ([(datetime UTC, nivel cm)], {atencion, alerta, inundacion}) de la tabla de 'Ver dados'."""
    filas = []
    for tr in re.findall(r"<tr>(.*?)</tr>", h, re.S):
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(c) >= 4 and re.fullmatch(r"\d\d/\d\d/\d{4}", c[0]) and re.fullmatch(r"\d\d:\d\d", c[1]):
            v = _num(c[-1])
            if v is not None:
                t = dt.datetime.strptime(c[0] + " " + c[1], "%d/%m/%Y %H:%M").replace(tzinfo=dt.timezone.utc)
                filas.append((t, v))
    texto = html.unescape(re.sub(r"<[^>]+>", " ", h))
    cotas = {}
    for clave, pat in (("atencion", r"Cota de aten\S*o\s*>=\s*([\d.]+)"), ("alerta", r"Cota de alerta\s*>=\s*([\d.]+)"),
                       ("inundacion", r"Cota de inunda\S*o\s*>=\s*([\d.]+)")):
        m = re.search(pat, texto)
        if m: cotas[clave] = float(m.group(1))
    return sorted(filas), cotas


def niveles(errores=None):
    s = _Sesion()
    est, ultima = [], None
    for nombre, pid in ESTACIONES:
        try:
            filas, cotas = _tabla(s.ver_dados(pid))
        except Exception as e:
            if errores is not None: errores.append(f"sace {nombre}: {e}")
            continue
        if not filas: continue
        t, v = filas[-1]
        e = {"n": nombre, "nivel": int(round(v)), "t": t.astimezone(UTC3).strftime("%Y-%m-%dT%H:%M")}
        if cotas.get("inundacion"): e["inund"] = int(cotas["inundacion"])
        if cotas.get("alerta"): e["alerta"] = int(cotas["alerta"])
        if cotas.get("atencion"): e["atencion"] = int(cotas["atencion"])
        antes = [x for x in filas if x[0] <= t - dt.timedelta(hours=23)]
        if antes:
            e["d24"] = int(round(v - antes[-1][1]))
            e["tend"] = "sube" if e["d24"] >= 5 else "baja" if e["d24"] <= -5 else "estable"
        if nombre == "Iraí": e["km"] = 0
        est.append(e)
        ultima = max(ultima, t) if ultima else t
    if not est:
        raise RuntimeError("el SACE no devolvió niveles")
    return {"fuente": "SGB · SACE (telemetría cada 15 min)", "fecha": ultima.astimezone(UTC3).strftime("%d/%m %H:%M"),
            "estaciones": est, "link": BASE + "/"}


if __name__ == "__main__":
    import json
    err = []
    print(json.dumps(niveles(err), ensure_ascii=False, indent=1)); print("errores:", err)
