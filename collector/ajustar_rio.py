"""Ajusta el modelo de previsión del río en el puerto de Salto con la historia horaria de CTM.

Uso: python collector/ajustar_rio.py   (lee data/historial/ctm-niveles-horario.csv, escribe data/modelo-rio.json)

Modelo: para cada día D+k (k = 1..6) se predice el promedio diario de la altura en el puerto como
  promedio de las últimas 24 h  +  regresión ridge sobre cambios de las medias de 24 h aguas arriba:
  Santo Tomé, Yapeyú/Paso de los Libres (promediadas), Monte Caseros y el embalse de Salto Grande,
  en el último día y en el día anterior, más el cambio reciente del propio puerto.
El rango probable sale de los percentiles 10 y 90 de los errores en validación cruzada por bloques de meses.
"""
import csv, json, datetime as dt
import numpy as np

ENTRADA = "data/historial/ctm-niveles-horario.csv"
ENTRADA_BR = "data/historial/ana-niveles-horario.csv"  # telemetría ANA (cm), ver collector/historia_ana.py
# Estaciones de Brasil que suman (probado contra el modelo sin Brasil): cambio de la media de 24 h en cuatro ventanas
BR = ["Manoel Viana", "Quaraí", "Iraí", "Porto Mauá", "Garruchos BR", "Itaqui"]
BR_LAGS = (0, 24, 48, 72)
LAM_BR = {1: 3000.0}  # el resto 800
LAM_BR_DEF = 800.0
SALIDA = "data/modelo-rio.json"
FEAT = ["dS24", "dST24", "dST48", "dPLY24", "dPLY48", "dMC24", "dMC48", "dSG24", "dSG48"]
LAM = 50.0
HORAS_EMISION = (1, 7, 13, 19)
K_MAX = 6


def cargar():
    rows = list(csv.DictReader(open(ENTRADA)))
    cols = [c for c in rows[0] if c != "t"]
    T = [dt.datetime.fromisoformat(r["t"]) for r in rows]
    t0 = T[0]; n = int((T[-1] - t0).total_seconds() // 3600) + 1
    X = {c: np.full(n, np.nan) for c in cols}
    for r, t in zip(rows, T):
        k = int((t - t0).total_seconds() // 3600)
        for c in cols:
            if r[c] not in ("", None): X[c][k] = float(r[c])
    for c in cols:
        a = X[c]; d = np.abs(np.diff(a, prepend=np.nan)); a[d > 1.0] = np.nan
        good = ~np.isnan(a)
        if good.sum() < 10: continue
        ii = np.arange(n); itp = np.interp(ii, ii[good], a[good]); i = 0
        while i < n:
            if not good[i]:
                j = i
                while j < n and not good[j]: j += 1
                if j - i <= 6: a[i:j] = itp[i:j]
                i = j
            else:
                i += 1
    grid = [t0 + dt.timedelta(hours=k) for k in range(n)]
    return grid, X


def media24(a):
    out = np.full_like(a, np.nan)
    for i in range(23, len(a)):
        w = a[i - 23:i + 1]
        if np.isnan(w).sum() <= 4: out[i] = np.nanmean(w)
    return out


def rasgos(R, i):
    """Rasgos en la hora i a partir de las medias de 24 h R[estación]. Misma definición que en tablero.py."""
    ply = lambda j: (R["Yapeyú"][j] + R["Paso de los Libres"][j]) / 2
    return {"dS24": R["Salto"][i] - R["Salto"][i - 24],
            "dST24": R["Santo Tomé"][i] - R["Santo Tomé"][i - 24], "dST48": R["Santo Tomé"][i - 24] - R["Santo Tomé"][i - 48],
            "dPLY24": ply(i) - ply(i - 24), "dPLY48": ply(i - 24) - ply(i - 48),
            "dMC24": R["Monte Caseros"][i] - R["Monte Caseros"][i - 24], "dMC48": R["Monte Caseros"][i - 24] - R["Monte Caseros"][i - 48],
            "dSG24": R["Salto Grande"][i] - R["Salto Grande"][i - 24], "dSG48": R["Salto Grande"][i - 24] - R["Salto Grande"][i - 48]}


def cargar_brasil(grid):
    """Series horarias de Brasil (m) alineadas con la grilla de CTM, con la misma limpieza."""
    import os
    n = len(grid); t0 = grid[0]
    B = {c: np.full(n, np.nan) for c in BR}
    if not os.path.exists(ENTRADA_BR): return B
    for r in csv.DictReader(open(ENTRADA_BR)):
        k = int((dt.datetime.fromisoformat(r["t"]) - t0).total_seconds() // 3600)
        if 0 <= k < n:
            for c in BR:
                if r.get(c) not in ("", None): B[c][k] = float(r[c]) / 100.0
    for c in BR:
        a = B[c]; d = np.abs(np.diff(a, prepend=np.nan)); a[d > 1.0] = np.nan
        good = ~np.isnan(a)
        if good.sum() < 10: continue
        ii = np.arange(n); itp = np.interp(ii, ii[good], a[good]); i = 0
        while i < n:
            if not good[i]:
                j = i
                while j < n and not good[j]: j += 1
                if j - i <= 6: a[i:j] = itp[i:j]
                i = j
            else:
                i += 1
    return B


def rasgos_br(RB, i):
    """Cambio de la media de 24 h de cada estación de Brasil, en las ventanas que terminan en i, i-24, i-48, i-72. En metros."""
    return [RB[c][i - L] - RB[c][i - L - 24] for c in BR for L in BR_LAGS]


def nombres_br():
    return [f"br:{c}:{L}" for c in BR for L in BR_LAGS]


def ajustar(A, y, lam=LAM):
    mu, sd = A.mean(0), A.std(0) + 1e-9
    Z = np.column_stack([np.ones(len(A)), (A - mu) / sd])
    w = np.linalg.solve(Z.T @ Z + lam * np.diag([0] + [1] * A.shape[1]), Z.T @ y)
    return mu, sd, w


def predecir(m, A):
    mu, sd, w = m
    return np.column_stack([np.ones(len(A)), (A - mu) / sd]) @ w


def main():
    grid, X = cargar()
    S = X["Salto"]
    R = {c: media24(X[c]) for c in ("Salto", "Santo Tomé", "Yapeyú", "Paso de los Libres", "Monte Caseros", "Salto Grande")}
    dias = {}
    for i, t in enumerate(grid):
        if not np.isnan(S[i]): dias.setdefault(t.date(), []).append(S[i])
    media_dia = {d: float(np.mean(v)) for d, v in dias.items() if len(v) >= 20}
    B = cargar_brasil(grid)
    RB = {c: media24(B[c]) for c in BR}
    filas = []
    for i, t in enumerate(grid):
        if t.hour not in HORAS_EMISION or i < 130: continue
        f = rasgos(R, i)
        base = R["Salto"][i]
        ys = [media_dia.get(t.date() + dt.timedelta(days=k)) for k in range(1, K_MAX + 1)]
        if np.isnan(base) or any(np.isnan(v) for v in f.values()): continue
        filas.append((t, base, [f[k] for k in FEAT], ys, S[i], S[i - 72], rasgos_br(RB, i)))
    print("emisiones válidas:", len(filas), filas[0][0].date(), "a", filas[-1][0].date())
    A = np.array([f[2] for f in filas]); base = np.array([f[1] for f in filas])
    EB = np.array([f[6] for f in filas]); hay_br = ~np.isnan(EB).any(1)
    AB = np.column_stack([A, np.nan_to_num(EB, nan=0.0)])  # para entrenar, Brasil faltante = sin cambio (dio mejor que descartar filas)
    print(f"con Brasil completo: {hay_br.sum()} de {len(filas)}")
    # bloques por fecha (6), con margen de 3 días para no mezclar entrenamiento y prueba
    fechas = np.array([f[0] for f in filas])
    cortes = np.array_split(np.arange(len(filas)), 6)
    salida = {"ajustado": dt.datetime.now().strftime("%Y-%m-%d"), "datos": f"{filas[0][0]:%d/%m/%Y} a {filas[-1][0]:%d/%m/%Y}",
              "rasgos": FEAT, "lambda": LAM, "horizontes": {},
              "brasil": {"estaciones": BR, "ventanas": list(BR_LAGS), "rasgos": FEAT + nombres_br(),
                         "fuente": "telemetría ANA (respaldo: visor SACE del SGB)", "horizontes": {}}}
    for k in range(1, K_MAX + 1):
        y = np.array([f[3][k - 1] if f[3][k - 1] is not None else np.nan for f in filas])
        ok = ~np.isnan(y)
        e = np.full(len(y), np.nan); e_act = np.full(len(y), np.nan)
        for b in cortes:
            lo, hi = fechas[b[0]] - dt.timedelta(days=3 + k), fechas[b[-1]] + dt.timedelta(days=3)
            tr = np.where(ok & ((fechas < lo) | (fechas > hi)))[0]
            bb = b[ok[b]]
            m = ajustar(A[tr], y[tr] - base[tr])
            e[bb] = base[bb] + predecir(m, A[bb]) - y[bb]
        # fórmula anterior, para comparar
        for j, f in enumerate(filas):
            if not ok[j]: continue
            h, h72 = f[4], f[5]
            pend = np.clip((h - h72) / 3, -0.25, 0.25) if not np.isnan(h72) else 0
            c = h
            for q in range(1, k + 1): c += pend * 0.8 ** q
            e_act[j] = c - y[j]
        m = ajustar(A[ok], y[ok] - base[ok])
        ee = e[ok]
        salida["horizontes"][str(k)] = {
            "mu": [round(float(v), 6) for v in m[0]], "sd": [round(float(v), 6) for v in m[1]], "w": [round(float(v), 6) for v in m[2]],
            "p10": round(float(np.percentile(ee, 10)), 3), "p90": round(float(np.percentile(ee, 90)), 3),
            "mae_cv": round(float(np.mean(np.abs(ee))), 3), "mae_anterior": round(float(np.nanmean(np.abs(e_act[ok]))), 3), "n": int(ok.sum())}
        print(f"D+{k}: error medio {np.mean(np.abs(ee))*100:.1f} cm (fórmula anterior {np.nanmean(np.abs(e_act[ok]))*100:.1f}) · "
              f"rango 80 %: {np.percentile(ee,10)*100:+.0f} a {np.percentile(ee,90)*100:+.0f} cm · n={ok.sum()}")
        # modelo con Brasil: se evalúa en las filas con Brasil completo, contra el modelo sin Brasil en esas mismas filas
        lam_b = LAM_BR.get(k, LAM_BR_DEF)
        eb = np.full(len(y), np.nan)
        for b in cortes:
            lo, hi = fechas[b[0]] - dt.timedelta(days=3 + k), fechas[b[-1]] + dt.timedelta(days=3)
            tr = np.where(ok & ((fechas < lo) | (fechas > hi)))[0]
            bb = b[ok[b]]
            mb = ajustar(AB[tr], y[tr] - base[tr], lam_b)
            eb[bb] = base[bb] + predecir(mb, AB[bb]) - y[bb]
        okb = ok & hay_br
        mb = ajustar(AB[ok], y[ok] - base[ok], lam_b)
        eeb = eb[okb]
        salida["brasil"]["horizontes"][str(k)] = {
            "mu": [round(float(v), 6) for v in mb[0]], "sd": [round(float(v), 6) for v in mb[1]], "w": [round(float(v), 6) for v in mb[2]],
            "p10": round(float(np.percentile(eeb, 10)), 3), "p90": round(float(np.percentile(eeb, 90)), 3), "lambda": lam_b,
            "mae_cv": round(float(np.mean(np.abs(eeb))), 3), "mae_sin_brasil": round(float(np.mean(np.abs(e[okb]))), 3), "n": int(okb.sum())}
        print(f"     con Brasil: {np.mean(np.abs(eeb))*100:.1f} cm (sin Brasil, mismas filas: {np.mean(np.abs(e[okb]))*100:.1f}) · "
              f"rango 80 %: {np.percentile(eeb,10)*100:+.0f} a {np.percentile(eeb,90)*100:+.0f} cm · n={okb.sum()}")
    json.dump(salida, open(SALIDA, "w"), ensure_ascii=False, indent=1)
    print("guardado", SALIDA)


if __name__ == "__main__":
    main()
