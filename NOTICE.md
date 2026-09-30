# Drittanbieter

| Komponente | Lizenz | Hinweis |
|---|---|---|
| [DB-IP Lite (IP-to-City)](https://db-ip.com/db/lite.php) | CC BY 4.0 | **Nicht im Repo.** Wird heruntergeladen. Auf jeder Seite, die Ergebnisse daraus anzeigt, muss ein Link auf DB-IP stehen („IP Geolocation by DB-IP“, siehe Fußzeile in `frontend/index.html`). |
| [globe.gl](https://github.com/vasturiano/globe.gl), [three-globe](https://github.com/vasturiano/three-globe) | MIT | Nicht im Repo, kommt per `npm run vendor` nach `frontend/vendor/`. |
| [three.js](https://threejs.org) | MIT | In `globe.gl` enthalten. |
| [Natural Earth](https://www.naturalearthdata.com) Ländergrenzen (`frontend/countries.geojson`, 1:110m, `ne_110m_admin_0_countries`, Version 5.1.1) | Public Domain ([Nutzungsbedingungen](https://www.naturalearthdata.com/about/terms-of-use/)) | Nutzung, Änderung und Weitergabe ohne Erlaubnis, auch kommerziell. Nennung nicht nötig, hier trotzdem. Die Datei wird mit `tools/build_countries.py` aus dem Original ([natural-earth-vector](https://github.com/nvkelso/natural-earth-vector), fester Commit) gebaut und dabei auf die benötigten Spalten gekürzt, Koordinaten auf 3 Nachkommastellen gerundet und winzige Inseln ohne Fläche entfernt. |
| maxminddb (Python) | Apache-2.0 | Wird im Docker-Build installiert. |
