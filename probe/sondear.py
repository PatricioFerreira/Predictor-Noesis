import urllib.request, os
os.makedirs("probe/out", exist_ok=True)
for n,u in [("datos_estacion","https://www.saltogrande.org/datos_estacion.php"),("mapa_estacion","https://www.saltogrande.org/mapa_estacion.php"),("horarios","https://www.saltogrande.org/datos_horarios.php")]:
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60).read()
        open(f"probe/out/{n}.html","wb").write(r); print(n,len(r))
    except Exception as e: print(n,e)
