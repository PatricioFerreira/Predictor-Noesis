import urllib.request, urllib.parse, os
os.makedirs("probe/out", exist_ok=True)
H={"User-Agent":"Mozilla/5.0"}
for n,i in [("est_salto","A501258E"),("est_saltogrande","A5002774"),("est_concordia","A50012EE")]:
    u="https://www.saltogrande.org/datos_estacion.php?"+urllib.parse.urlencode({"estacion":i,"desde":"18/10/2026","hasta":"19/10/2026"})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=60).read(); open(f"probe/out/{n}.html","wb").write(r); print(n,len(r))
    except Exception as e: print(n,e)
for n in ["Salto","Puerto Concordia"]:
    try:
        r=urllib.request.urlopen(urllib.request.Request("https://www.saltogrande.org/iwweb.php",data=urllib.parse.urlencode({"nombreestacion":n}).encode(),headers=H),timeout=60).read()
        open(f"probe/out/iw_{n.replace(' ','_')}.html","wb").write(r); print(n,len(r))
    except Exception as e: print(n,e)
