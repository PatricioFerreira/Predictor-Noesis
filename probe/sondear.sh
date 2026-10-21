mkdir -p probe/out
O="Origin: https://patricioferreira.github.io"
: > probe/out/cors2.txt
for u in "https://tgftp.nws.noaa.gov/data/observations/metar/stations/SUSO.TXT" "https://aviationweather.gov/cgi-bin/data/metar.php?ids=SUSO" "https://aviationweather.gov/api/data/metar?ids=SUSO" "https://www.inumet.gub.uy/reportes/estadoActual/datos_inumet_ui_publica.mch" "https://www.inumet.gub.uy/reportes/estadoActual/estadoActualDatosHorarios.mch" "https://www.inumet.gub.uy/reportes/pronosticos/pronosticoV4.json" "https://api.open-meteo.com/v1/forecast?latitude=-31.4&longitude=-57.97&current=temperature_2m&models=metar"; do
  echo "== $u" >> probe/out/cors2.txt
  curl -s -D - -o /tmp/b -H "$O" "$u" | grep -i -E "^HTTP|access-control|content-type" >> probe/out/cors2.txt
  head -c 300 /tmp/b >> probe/out/cors2.txt; echo >> probe/out/cors2.txt
done
