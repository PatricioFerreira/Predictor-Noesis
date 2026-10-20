"""Fusiona data/tablero.json (lo que arma el recolector) con el documento actual de la base del tablero.

Uso: python3 fusionar.py actual.json tablero.json salida.json
- Pisa todo lo numérico que trae el recolector.
- Conserva lo que solo escribe la tarea (PDFs de CTM, boletín de Brasil, ENSO, ciudades extra, umbrales, calles).
- Alertas: reemplaza las automáticas y conserva las de CARU / Brasil / CTM que haya cargado la tarea.
"""
import json, sys

AUTO = {"INUMET", "Telemetría CTM", "ECMWF (MET Norway)", "SYNOP INUMET"}


def merge(base, parche):
    for k, v in parche.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def main(a, t, out):
    doc = json.load(open(a))
    doc = doc.get("data", doc) if "zonas" not in doc else doc
    p = json.load(open(t))
    for k in ("actualizado", "motor", "verificacion", "ranking"):
        if k in p: doc[k] = p[k]
    doc.setdefault("zonas", {})
    for z, v in p.get("zonas", {}).items():
        doc["zonas"].setdefault(z, {})
        for k, val in v.items():
            doc["zonas"][z][k] = val
    doc.setdefault("rio", {})
    for k, v in p.get("rio", {}).items():
        if k in ("puerto", "represa") and isinstance(doc["rio"].get(k), dict):
            merge(doc["rio"][k], v)
        elif k == "prevision" and isinstance(doc["rio"].get(k), dict):
            despues = doc["rio"][k].get("despues")
            doc["rio"][k] = v
            if despues: doc["rio"][k]["despues"] = despues
        else:
            doc["rio"][k] = v
    viejas = [x for x in doc.get("alertas", []) if x.get("fuente") not in AUTO and not str(x.get("fuente", "")).startswith("ECMWF")]
    orden = {"rojo": 0, "naranja": 1, "amarillo": 2, "verde": 3}
    doc["alertas"] = sorted(p.get("alertasAuto", []) + viejas, key=lambda x: orden.get(x.get("nivel"), 4))
    for f in doc.get("fuentes", []):
        act = p.get("fuentesAct", {}).get(f.get("n"))
        if act:
            f["estado"] = "activa"
            if act != "ok": f["act"] = act
    if p.get("generadoPor") == "recolector":
        for f in doc.get("fuentes", []):
            if f.get("n") in ("ICON (Alemania)", "GEM (Canadá)", "JMA (Japón)", "ARPEGE (Francia)", "UKMO (Reino Unido)", "GFS (NOAA, vía recolector)", "SMN Argentina (WRF 4 km)"):
                f["estado"] = "activa"; f["act"] = p["fuentesAct"]["Recolector propio (GitHub)"]
    json.dump(doc, open(out, "w"), ensure_ascii=False)
    print("ok", doc["actualizado"], len(doc["alertas"]), "alertas")


if __name__ == "__main__":
    main(*sys.argv[1:4])
