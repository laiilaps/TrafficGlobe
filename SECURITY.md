# Sicherheit

## Ziel und Bedrohungsmodell

Die öffentliche Seite darf weder IP-Adressen noch Informationen über die eingesetzte Technik preisgeben, und Angreifer dürfen
über manipulierte Logzeilen weder falsche Daten einschleusen noch den Collector lahmlegen.

## Entwurfsentscheidungen

| Bereich | Maßnahme |
|---|---|
| Datenfluss | Logs → Collector → **eine** JSON-Datei → statischer Webserver. Kein Backend, keine API, keine Datenbank. |
| Container | Nicht-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`, Speicher-/CPU-/PID-Limits, **kein Netz** (Collector), kein Docker-Socket. |
| Updater | Nur HTTPS zu einem festen Host (auch bei Weiterleitungen), Größenlimits, Prüfung der Datei vor dem Austausch, atomarer Austausch, bei Fehlern bleibt die alte Datei. |
| Öffentliche Daten | Nur `[Zeit, Art-Nummer, Breite, Länge]`. Ereignisse sind beim Erzeugen vergröbert, es gibt intern keine feinere Version. Keine Artennamen (verrät sonst die Technik). |
| Log-Injection | Benutzernamen, User-Agents und Pfade kommen vom Angreifer. Die IP steht bei allen Meldungen mit Namen am festen Ende der Zeile (letztes Vorkommen gewinnt). Zeilen mit mehr als einer Adresse im Weiterleitungs-Header werden verworfen. |
| Robustheit | Zeilenlängenlimit, Lesefenster mit Überspringen von Zeilen ohne Umbruch, Limit pro Durchlauf, Ausgabedeckel, atomares Schreiben, fehlende Rechte werden toleriert. Getestet mit Angriffszeilen und Zufalls-Fuzz. |
| Webserver | Nur bekannte Dateien, alles andere 404. Nur GET/HEAD. Rate-Limit pro Besucher. |
| Header | Strenge CSP (`default-src 'none'`, kein Inline-Code, keine fremden Ziele), `nosniff`, Framing verboten, `Referrer-Policy: no-referrer`. |
| Frontend | Kein `innerHTML`/`eval`. Daten nur über `textContent`. Keine externen Skripte, Schriften oder Bilder. Kein Tracking, keine Cookies. |

## Bekannte Grenzen

- Der Collector bekommt `/var/log` schreibgeschützt (einzelne Dateien würden bei Log-Rotation ungültig). Er hat kein Netz und kann nichts
  schreiben außer in sein `out/`-Verzeichnis.
- Ohne Verzögerung und Mindestanzahl (`PUBLIC_DELAY=0`, `PUBLIC_K_MIN=1`) kann ein Besucher seine eigene Linie erkennen.
- Wer denselben VPN-Ausgang nutzt wie ein Angreifer, erscheint am selben Ort. Die Orte sind nur so genau wie die Geo-Datenbank.
- Die Geo-Zuordnung von IPs ist ungenau und gehört zu einem Rechenzentrum oder Provider, nicht zwingend zu einer Person.

## Schwachstellen melden

Bitte über GitHub „Security → Report a vulnerability“ (falls aktiviert), sonst als Issue ohne Exploit-Details, IP-Adressen und echte Logzeilen.
