# Predictor del Litoral · recolector de datos

Programa que corre solo en GitHub cada 3 horas y deja `data/latest.json` con:

- **Modelos** (vía Open-Meteo): ECMWF, GFS, ICON, GEM, JMA, ARPEGE y UKMO, para Salto, Montevideo y el Este. Temperatura máxima y mínima, lluvia, viento y presión horaria.
- **Observado** (NOAA ISD, mensajes SYNOP de las estaciones de INUMET): máximas, mínimas, lluvia y presión de los últimos días, para medir qué fuente acierta.

El tablero *Predictor del Litoral* lee este archivo en cada actualización. Solo contiene datos meteorológicos públicos.
