"""Arma la carpeta _site para GitHub Pages a partir de web/tablero.html (la misma página del tablero de Claude)."""
import os, shutil
os.makedirs("_site/data", exist_ok=True)
cuerpo = open("web/tablero.html", encoding="utf-8").read()
html = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>html,body{margin:0;padding:0}</style></head><body>' + cuerpo + '</body></html>')
open("_site/index.html", "w", encoding="utf-8").write(html)
for f in ("completo.json", "verificacion.json"):
    if os.path.exists("data/" + f): shutil.copy("data/" + f, "_site/data/" + f)
shutil.copytree("data/historial", "_site/data/historial", dirs_exist_ok=True)
print("sitio listo")
