import urllib.request, os
os.makedirs("probe/out", exist_ok=True)
H={"User-Agent":"Mozilla/5.0 (predictor-noesis)"}
for n,u in [("comunicado.pdf","https://www.saltogrande.org/docs/hidrologia/Comunicado.pdf"),
            ("caudales.pdf","https://www.saltogrande.org/docs/hidrologia/CaudalesNiveles.pdf"),
            ("precip.pdf","https://www.saltogrande.org/docs/hidrologia/Precipitaciones.pdf"),
            ("sgb.html","https://www.sgb.gov.br/sace/uruguai/ultimo_boletim.php"),
            ("ensodisc.html","https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"),
            ("wksst.txt","https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"),
            ("oni.txt","https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"),
            ("soi.txt","https://www.cpc.ncep.noaa.gov/data/indices/soi")]:
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=60).read(); open("probe/out/"+n,"wb").write(r); print(n,len(r))
    except Exception as e: print(n,e)
