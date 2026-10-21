mkdir -p probe/out
O="Origin: https://patricioferreira.github.io"
for u in "https://aviationweather.gov/api/data/metar?ids=SUSO&format=json&hours=2" "https://api.open-meteo.com/v1/forecast?latitude=-31.4&longitude=-57.97&current=temperature_2m" "https://www.saltogrande.org/datos_estacion.php?estacion=A501258E" "https://www.ogimet.com/cgi-bin/getsynop?block=86360&begin=202610210000" "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=-31.4&lon=-57.97" "https://www.saltogrande.org/datos_horarios.php"; do
  echo "== $u" >> probe/out/cors.txt
  curl -s -D - -o /dev/null -H "$O" "$u" | grep -i -E "^HTTP|access-control" >> probe/out/cors.txt
done
