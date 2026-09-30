'use strict';
// ================= Einstellungen =================
    // Alle Looks kommen ohne Bilddateien aus: Die Kugel ist eine Farbfläche, die Länder werden aus der geojson gezeichnet.
    const LOOKS = {
        'neon':          { name: 'Neon-Umrisse',    kugel: '#000a06', land: 'umrisse', landFarbe: '#39ff88', atm: '#39ff88' },
        'cyber-gruen':   { name: 'Cyber · Grün',    kugel: '#031a0c', land: 'hex',     landFarbe: '#1f7d4f', atm: '#39ff88' },
        'cyber-blau':    { name: 'Cyber · Blau',    kugel: '#020b1f', land: 'hex',     landFarbe: '#1b5bd6', atm: '#00b7ff' },
        'cyber-violett': { name: 'Cyber · Violett', kugel: '#12031f', land: 'hex',     landFarbe: '#7a3ad6', atm: '#b44dff' },
        'cyber-amber':   { name: 'Cyber · Amber',   kugel: '#1a0f00', land: 'hex',     landFarbe: '#b87400', atm: '#ffb000' },
    };

    // Standard für jeden neuen Besucher (wer etwas ändert, behält seine Wahl im eigenen Browser)
    const STANDARD = {
        look: 'neon', hintergrund: 'schwarz', atmosphaere: true, gitter: true,
        rotation: true, rotTempo: 0.4,
        leben: 10, staerke: 1, hoehe: 0.4, ringe: true,
        scanlines: true, scanStaerke: 0.8,
        legende: 'kompakt',
    };

    const MENUE = [
        { titel: 'Erde' },
        { key: 'look',        art: 'auswahl', label: 'Look', optionen: Object.entries(LOOKS).map(([k, v]) => [k, v.name]) },
        { key: 'hintergrund', art: 'auswahl', label: 'Hintergrund', optionen: [['schwarz', 'Schwarz'], ['sterne', 'Sternenhimmel']] },
        { key: 'atmosphaere', art: 'schalter', label: 'Leuchtrand' },
        { key: 'gitter',      art: 'schalter', label: 'Gitternetz' },
        { key: 'rotation',    art: 'schalter', label: 'Automatisch drehen' },
        { key: 'rotTempo',    art: 'regler', label: 'Drehtempo', min: 0.1, max: 2, schritt: 0.1 },
        { titel: 'Linien' },
        { key: 'leben',   art: 'regler', label: 'Sichtbar (Min.)', min: 1, max: 10, schritt: 1 },
        { key: 'staerke', art: 'regler', label: 'Stärke', min: 0.5, max: 3, schritt: 0.1 },
        { key: 'hoehe',   art: 'regler', label: 'Bogenhöhe', min: 0.1, max: 0.9, schritt: 0.05 },
        { key: 'ringe',   art: 'schalter', label: 'Einschlag-Ringe' },
        { titel: 'Effekte' },
        { key: 'scanlines',   art: 'schalter', label: 'Scanlines (CRT)' },
        { key: 'scanStaerke', art: 'regler', label: 'Scanlines-Stärke', min: 0.2, max: 1, schritt: 0.05 },
        { titel: 'Anzeige' },
        { key: 'legende', art: 'auswahl', label: 'Legende', optionen: [['kompakt', 'Kompakt'], ['voll', 'Ausführlich'], ['aus', 'Aus']] },
    ];

    const SPEICHER = 'trafficglobe-einstellungen';
    const S = Object.assign({}, STANDARD);
    try {                                   // gespeicherte Einstellungen laden (Browser kann das blockieren: dann Standard)
        const alt = JSON.parse(localStorage.getItem(SPEICHER) || '{}');
        for (const k in STANDARD) if (typeof alt[k] === typeof STANDARD[k]) S[k] = alt[k];
        if (!LOOKS[S.look]) S.look = STANDARD.look;
        if (!['kompakt', 'voll', 'aus'].includes(S.legende)) S.legende = STANDARD.legende;
    } catch (err) { /* Standard */ }

    function speichern() {
        try { localStorage.setItem(SPEICHER, JSON.stringify(S)); } catch (err) { /* egal */ }
    }

    // ================= Globus =================
    const globus = Globe()(document.getElementById('globe'))
        .backgroundColor('#000000');

    let laender = [];                 // Länder-Features aus der geojson

    // Einfarbige Kugel als winzige Textur. Die Kugelfarbe direkt zu ändern geht schief, wenn vorher ein Foto lag
    // (die Bibliothek übernimmt Änderungen erst im nächsten Bild und hat die Farbe dann kurz nicht).
    const farbBilder = {};
    function farbBild(hex) {
        if (!farbBilder[hex]) {
            const c = document.createElement('canvas');
            c.width = c.height = 2;
            const g = c.getContext('2d');
            g.fillStyle = hex;
            g.fillRect(0, 0, 2, 2);
            farbBilder[hex] = c.toDataURL('image/png');
        }
        return farbBilder[hex];
    }

    // Sternenhimmel selbst gezeichnet (fester Zufall: bei jedem Besuch derselbe Himmel), keine Bilddatei nötig
    let sterneUrl = null;
    function sternenBild() {
        if (sterneUrl) return sterneUrl;
        const c = document.createElement('canvas');
        c.width = 2048; c.height = 1024;
        const g = c.getContext('2d');
        g.fillStyle = '#000';
        g.fillRect(0, 0, c.width, c.height);
        let z = 12345;
        const zufall = () => (z = (z * 1664525 + 1013904223) >>> 0) / 4294967296;
        for (let i = 0; i < 1500; i++) {
            const groß = zufall() < 0.06;
            g.fillStyle = `rgba(200, 225, 255, ${(0.25 + zufall() * 0.75).toFixed(2)})`;
            g.beginPath();
            g.arc(zufall() * c.width, zufall() * c.height, groß ? 1.5 : 0.6 + zufall() * 0.5, 0, 6.2832);
            g.fill();
        }
        sterneUrl = c.toDataURL('image/png');
        return sterneUrl;
    }

    function erdeAnwenden() {
        const l = LOOKS[S.look];
        globus.globeImageUrl(farbBild(l.kugel));
        globus.backgroundImageUrl(S.hintergrund === 'sterne' ? sternenBild() : null);
        globus.showAtmosphere(S.atmosphaere).atmosphereColor(l.atm).atmosphereAltitude(0.2);
        globus.showGraticules(S.gitter);

        // Länder: als leuchtende Sechsecke, als Umrisse oder gar nicht (dann trägt das Foto die Erde)
        globus.hexPolygonsData(l.land === 'hex' ? laender : [])
            .hexPolygonResolution(3).hexPolygonMargin(0.4).hexPolygonColor(() => l.landFarbe);
        globus.polygonsData(l.land === 'umrisse' ? laender : [])
            .polygonCapColor(() => 'rgba(0, 0, 0, 0)').polygonSideColor(() => 'rgba(0, 0, 0, 0)')
            .polygonStrokeColor(() => l.landFarbe).polygonAltitude(0.004);

        const c = globus.controls();
        c.autoRotate = S.rotation;
        c.autoRotateSpeed = S.rotTempo * 2;
        document.body.classList.toggle('scanlines', S.scanlines);
        document.body.style.setProperty('--scan', S.scanStaerke);
    }

    // Ziel aller Linien
    // Zielpunkt aller Linien. Setze hier DEINEN Wert (Beispielwert). Bewusst NICHT den echten Serverstandort wählen.
    const ZIEL = { lat: 48.2, lng: 16.3 };

    // ---------- Farben nach Art ----------
    // Warme Farben = schlechter Verkehr, kühle Farben = guter Verkehr / erfolgreich abgewehrt
    // Reihenfolge wie in der Datendatei: Der Server liefert nur die Nummer der Art, keine Namen.
    const ART_NACH_INDEX = ['abgewiesen', 'login', 'sperre', 'scanner', 'besucher'];
    const GRUPPEN = { boese: 'Fehlgeschlagene Angriffe', abwehr: 'Abwehr', gut: 'Normale Besucher' };
    const ARTEN = {                    // Reihenfolge = Reihenfolge in der Legende
        abgewiesen: { gruppe: 'boese', farbe: '#ff2d2d', name: 'Port-Scan',
                      text: 'Verbindungsversuch auf einen geschlossenen Port, abgewiesen' },                       // rot
        login:      { gruppe: 'boese', farbe: '#ff8c00', name: 'Passwort-Raten',
                      text: 'Automatisierte Login-Versuche mit erratenen Zugangsdaten, gescheitert (Brute-Force)' },  // orange
        scanner:    { gruppe: 'boese', farbe: '#ffe600', name: 'Schwachstellen-Suche',
                      text: 'Bots prüfen die Website auf bekannte Lücken, Anfrage mit HTTP-Fehler 4xx beantwortet' }, // gelb
        sperre:     { gruppe: 'abwehr', farbe: '#1e90ff', name: 'IP gebannt',
                      text: 'Reaktion des Servers: Absender nach wiederholten Fehlversuchen automatisch gebannt (ausgesperrt)' }, // blau
        besucher:   { gruppe: 'gut',   farbe: '#2bff6a', name: 'Besucher',
                      text: 'Normaler Seitenaufruf, erfolgreich beantwortet (HTTP 2xx/3xx)' },                       // grün
    };

    const FADE_MS = 1000;              // wie oft die Deckkraft neu berechnet wird
    const MIN_ALPHA = 0.06;            // Deckkraft kurz vor dem Verschwinden
    const POLL_MS = 3000;              // wie oft nach neuen Daten geschaut wird
    const FRISCH_S = 15;               // Ereignisse jünger als das werden "geschossen", ältere liegen gleich da
    const MAX_BOEGEN = 3000;
    const RING_RADIUS = 15;
    const RING_SPEED = 5;
    const RING_LEBEN = RING_RADIUS / RING_SPEED * 1000;
    const lebenMs = () => S.leben * 60 * 1000;   // so lange bleibt eine Linie (live-public.json reicht 10 Min zurück)

    function hexZuRgba(hex, alpha) {
        const n = parseInt(hex.slice(1), 16);
        return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
    }

    // ---------- Zustand ----------
    let aktive = [];          // alle Linien, die es gerade gibt
    let ringe = [];
    const verborgen = new Set();   // in der Legende weggeklickte Arten

    let hoverBogen = null;
    let hoverVeraltet = true;
    function anzeigen() {
        hoverVeraltet = true;
        globus.arcsData(aktive.filter(b => !verborgen.has(b.kat)));
    }

    function ringSpawnen(lat, lng, farbe) {
        if (!S.ringe) return;
        const ring = { lat, lng, farbe };
        ringe.push(ring);
        globus.ringsData(ringe);
        setTimeout(() => {
            ringe = ringe.filter(r => r !== ring);
            globus.ringsData(ringe);
        }, RING_LEBEN);
    }

    // Bogenhöhe (Anteil des Erdradius) richtet sich nach der Entfernung zum Ziel: nahe Herkunft = flacher Bogen, weite = hoher.
    // Gleich hohe Bögen wären genau verkehrt herum: Nahe würden zu Nadeln, weite schleifen fast an der Oberfläche entlang.
    // S.hoehe (Menü "Bogenhöhe") ist der Grundwert, der alles gemeinsam skaliert.
    function winkelZumZiel(la, lo) {                                  // Großkreis-Winkel in Radiant, 0 (nah) bis π (Gegenseite der Erde)
        const r = Math.PI / 180, a = la * r, b = ZIEL.lat * r, dl = (lo - ZIEL.lng) * r;
        return Math.acos(Math.min(1, Math.max(-1, Math.sin(a) * Math.sin(b) + Math.cos(a) * Math.cos(b) * Math.cos(dl))));
    }
    function bogenHoehe(d) {
        return S.hoehe * (0.25 + 1.5 * d.winkel / Math.PI);
    }

    const linien = new Map();       // Ursprung + Art -> Linie, solange sie besteht
    const linienSchluessel = ev => `${ev.la}|${ev.lo}|${ev.k}`;
    const ARTEN_LISTE = Object.keys(ARTEN);

    /**
     * Neues Ereignis. Gibt es vom selben Ort und derselben Art schon eine Linie, wird keine neue gezeichnet:
     * Ein kleines Paket fährt die bestehende Linie entlang, und die Linie wird wieder frisch.
     * Sonst: neue Linie, vom Start zum Ziel "geschossen", danach bleibt sie stehen.
     * statisch=true: liegt sofort fertig da (ältere Ereignisse beim ersten Laden).
     */
    function neuerBogen(ev, statisch = false, alterMs = 0) {
        const key = linienSchluessel(ev);
        const vorhanden = linien.get(key);
        if (vorhanden) {
            vorhanden.zeiten.push(Date.now() - alterMs);
            if (vorhanden.zeiten.length > 500) vorhanden.zeiten.shift();
            if (statisch) vorhanden.geboren = Math.max(vorhanden.geboren, Date.now() - alterMs);
            else paketAufLinie(vorhanden);
            return;
        }
        const dauer = 1500 + Math.random() * 500;
        const bogen = {
            startLat: ev.la, startLng: ev.lo, dauer: dauer,
            kat: ev.k,
            farbe: (ARTEN[ev.k] || { farbe: '#ffffff' }).farbe,
            winkel: winkelZumZiel(ev.la, ev.lo),                            // Entfernung zum Ziel als Winkel (0 bis π)
            zusatzHoehe: Math.max(0, ARTEN_LISTE.indexOf(ev.k)) * 0.012,   // Linien gleicher Strecke, aber anderer Art, liegen nicht ineinander (Flackern)
            geboren: Date.now() - alterMs,
            bereitAb: statisch ? 0 : Date.now() + dauer * 1.2,             // ab dann ist die Linie fertig gezeichnet
            alpha: 1,
            statisch: statisch,
            zeiten: [Date.now() - alterMs],     // Zeitpunkt jeder Anfrage auf dieser Linie (für Zähler und Tooltip)
            land: undefined,
        };
        aktive.push(bogen);
        linien.set(key, bogen);
        if (aktive.length > MAX_BOEGEN) {
            const raus = aktive.shift();
            linien.delete(linienSchluessel({ la: raus.startLat, lo: raus.startLng, k: raus.kat }));
        }

        if (!statisch) {
            ringSpawnen(bogen.startLat, bogen.startLng, bogen.farbe);                 // Abschuss
            setTimeout(() => ringSpawnen(ZIEL.lat, ZIEL.lng, bogen.farbe), dauer);    // Einschlag
            // Wenn der Puls angekommen ist, wird die Linie zur festen Linie. Bis dahin war sie animiert.
            setTimeout(() => { bogen.statisch = true; anzeigen(); }, dauer * 1.2);
        }
        anzeigen();
    }

    // ---------- Pakete: kleine Kugeln, die auf einer bestehenden Linie entlangfahren ----------
    const pakete = [];
    let paketLaeuft = false;
    let klassen = null;                       // three.js-Klassen, aus vorhandenen Objekten der Bibliothek geholt

    function threeKlassen(bogenGruppe) {
        if (klassen) return klassen;
        let kugel = null;
        globus.scene().traverse(o => {
            if (!kugel && o.isMesh && o.geometry && o.geometry.type === 'SphereGeometry') kugel = o;
        });
        if (!kugel) return null;
        klassen = { Mesh: kugel.constructor, Kugel: kugel.geometry.constructor,
                    Material: globus.globeMaterial().constructor, Gruppe: bogenGruppe.constructor };
        return klassen;
    }

    function pfadFinden(bogen) {              // die echte Kurve der Linie (Kurve = Weg des Pakets)
        let gefunden = null;
        globus.scene().traverse(o => {
            if (!gefunden && o.__globeObjType === 'arc' && o.__data === bogen) gefunden = o;
        });
        const mesh = gefunden && gefunden.children[0];
        const pfad = mesh && mesh.geometry && mesh.geometry.parameters && mesh.geometry.parameters.path;
        return pfad ? { gruppe: gefunden, pfad } : null;
    }

    function paketAufLinie(bogen) {
        if (verborgen.has(bogen.kat)) return;
        const warte = Math.max(0, bogen.bereitAb - Date.now());   // Linie noch im Aufbau: Paket startet, wenn sie fertig ist
        setTimeout(() => paketStarten(bogen), warte);
        bogen.geboren = Date.now();                                // wer oft anklopft, hält seine Linie hell
    }

    function paketStarten(bogen) {
        if (!linien.has(linienSchluessel({ la: bogen.startLat, lo: bogen.startLng, k: bogen.kat })) || verborgen.has(bogen.kat)) return;
        const f = pfadFinden(bogen);
        if (!f) return;
        const K = threeKlassen(f.gruppe);
        if (!K) return;
        const farbe = parseInt(bogen.farbe.slice(1), 16);
        const geo = new K.Kugel(1, 14, 14);
        const kernMat = new K.Material({ color: farbe, emissive: farbe, emissiveIntensity: 1 });
        const hofMat = new K.Material({ color: farbe, emissive: farbe, emissiveIntensity: 1, transparent: true, opacity: 0.28 });
        const radius = 0.9 * Math.sqrt(S.staerke);
        const kern = new K.Mesh(geo, kernMat), hof = new K.Mesh(geo, hofMat);
        kern.scale.setScalar(radius);
        hof.scale.setScalar(radius * 2.4);
        const gruppe = new K.Gruppe();
        gruppe.add(hof, kern);
        f.gruppe.parent.add(gruppe);          // im selben Koordinatensystem wie die Linie
        pakete.push({ gruppe, pfad: f.pfad, start: performance.now(), dauer: bogen.dauer, farbe: bogen.farbe,
                      aufraeumen: () => { geo.dispose(); kernMat.dispose(); hofMat.dispose(); } });
        if (!paketLaeuft) { paketLaeuft = true; requestAnimationFrame(paketSchritt); }
    }

    function paketSchritt() {
        const jetzt = performance.now();
        for (let i = pakete.length - 1; i >= 0; i--) {
            const p = pakete[i], t = (jetzt - p.start) / p.dauer;
            if (t >= 1) {                     // angekommen: Paket entfernen, Ring am Ziel
                if (p.gruppe.parent) p.gruppe.parent.remove(p.gruppe);
                p.aufraeumen();
                pakete.splice(i, 1);
                ringSpawnen(ZIEL.lat, ZIEL.lng, p.farbe);
                continue;
            }
            const v = p.pfad.getPointAt(t);
            p.gruppe.position.set(v.x, v.y, v.z);
        }
        if (pakete.length) requestAnimationFrame(paketSchritt);
        else paketLaeuft = false;
    }

    // Deckkraft: neu = 1, mit dem Alter linear bis MIN_ALPHA, danach weg
    function altern() {
        const jetzt = Date.now(), leben = lebenMs();
        aktive = aktive.filter(b => jetzt - b.geboren < leben);
        aktive.forEach(b => { b.zeiten = b.zeiten.filter(t => jetzt - t < leben); });   // nur Anfragen im Zeitfenster zählen
        const lebt = new Set(aktive);
        for (const [key, b] of linien) if (!lebt.has(b)) linien.delete(key);
        aktive.forEach(b => {
            b.alpha = MIN_ALPHA + (1 - MIN_ALPHA) * (1 - (jetzt - b.geboren) / leben);
        });
        anzeigen();
        legendeAktualisieren();
    }
    setInterval(altern, FADE_MS);

    // ---------- Darstellung der Linien ----------
    globus
        .arcsTransitionDuration(0)
        .arcStartLat(d => d.startLat)
        .arcStartLng(d => d.startLng)
        .arcEndLat(() => ZIEL.lat)
        .arcEndLng(() => ZIEL.lng)
        .arcAltitude(d => bogenHoehe(d) + d.zusatzHoehe)
        .arcColor(d => hexZuRgba(d.farbe, d.alpha.toFixed(3)))
        .arcStroke(d => (d.kat === 'sperre' ? 0.7 : 0.4) * S.staerke * (d === hoverBogen ? 2.4 : 1))   // Sperren sind dicker (zweites Merkmal neben der Farbe), die überfahrene Linie hebt sich ab
        // Schuss: ein Strich, länger als der Bogen, wächst vom Start zum Ziel und bleibt dann stehen.
        // Statisch: durchgehende Linie ohne Animation.
        .arcDashLength(d => d.statisch ? 1 : 2)
        .arcDashGap(d => d.statisch ? 0 : 10)
        .arcDashInitialGap(d => d.statisch ? 0 : 1)
        .arcDashAnimateTime(d => d.statisch ? 0 : d.dauer)
        .ringLat(d => d.lat)
        .ringLng(d => d.lng)
        .ringColor(d => t => hexZuRgba(d.farbe, 1 - t))
        .ringMaxRadius(RING_RADIUS)
        .ringPropagationSpeed(RING_SPEED)
        .ringRepeatPeriod(0);

    // Länder-Index: aus der geojson, die ohnehin geladen wird. Für "aus welchem Land kommt diese Linie?" im Tooltip.
    const landIndex = [];
    let regionNamen = null;
    try { regionNamen = new Intl.DisplayNames(['de'], { type: 'region' }); } catch (err) { /* ältere Browser: englische Namen */ }

    // Natural Earth 5.x nennt Kosovo "KV" und Taiwan "CN-TW"; für die Ländernamen (Intl) braucht es die üblichen Codes
    const CC_KORREKTUR = { 'KV': 'XK', 'CN-TW': 'TW' };

    function landIndexBauen(features) {
        for (const f of features) {
            const p = f.properties;
            const roh = p.ISO_A2 !== '-99' ? p.ISO_A2 : (p.ADM0_A3 === 'NOR' ? 'NO' : p.WB_A2);   // Natural Earth: FR/NO fehlen
            const cc = CC_KORREKTUR[roh] || roh;
            const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
            const eintrag = { cc: cc && cc !== '-99' ? cc : null, name: p.NAME, polys: [], la: 0, lo: 0 };
            let beste = -1;
            for (const poly of polys) {
                const ring = poly[0];
                let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
                for (const [lo, la] of ring) {
                    minLa = Math.min(minLa, la); maxLa = Math.max(maxLa, la);
                    minLo = Math.min(minLo, lo); maxLo = Math.max(maxLo, lo);
                }
                eintrag.polys.push({ minLa, maxLa, minLo, maxLo, ring });
                const flaeche = (maxLa - minLa) * (maxLo - minLo);
                if (flaeche > beste) { beste = flaeche; eintrag.la = (minLa + maxLa) / 2; eintrag.lo = (minLo + maxLo) / 2; }
            }
            landIndex.push(eintrag);
        }
    }

    function imRing(ring, lo, la) {                       // Strahlverfahren
        let innen = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const [xi, yi] = ring[i], [xj, yj] = ring[j];
            if ((yi > la) !== (yj > la) && lo < (xj - xi) * (la - yi) / (yj - yi) + xi) innen = !innen;
        }
        return innen;
    }

    function landName(e) {
        try { if (regionNamen && e.cc) return regionNamen.of(e.cc); } catch (err) { /* englischer Name */ }
        return e.name;
    }

    // Kleine Staaten, die in der groben Karte fehlen (sonst würden sie dem Nachbarland zugeordnet)
    const KLEINSTAATEN = { SG: [1.35, 103.82], HK: [22.32, 114.17], MO: [22.2, 113.55], MT: [35.9, 14.4], MC: [43.74, 7.42],
                           LI: [47.16, 9.55], AD: [42.5, 1.52], BH: [26.07, 50.55], MV: [3.2, 73.22], MU: [-20.3, 57.55],
                           SC: [-4.68, 55.49], GI: [36.14, -5.35], JE: [49.21, -2.13], GG: [49.46, -2.58], IM: [54.24, -4.55] };

    function landZu(la, lo) {
        for (const cc in KLEINSTAATEN) {
            const [kla, klo] = KLEINSTAATEN[cc];
            if (Math.abs(la - kla) < 1 && Math.abs(lo - klo) < 1) { try { return regionNamen ? regionNamen.of(cc) : cc; } catch (err) { return cc; } }
        }
        for (const e of landIndex) {
            for (const p of e.polys) {
                if (la >= p.minLa && la <= p.maxLa && lo >= p.minLo && lo <= p.maxLo && imRing(p.ring, lo, la)) return landName(e);
            }
        }
        // Küstennahe, gerundete Koordinate (in der groben Karte liegt sie im Meer): Land mit dem nächsten Küstenpunkt
        let bester = null, d2min = 36;                    // höchstens ~6 Grad entfernt
        const kl = Math.cos(la * Math.PI / 180);
        for (const e of landIndex) {
            for (const p of e.polys) {
                if (la < p.minLa - 6 || la > p.maxLa + 6 || lo < p.minLo - 6 / Math.max(kl, 0.2) || lo > p.maxLo + 6 / Math.max(kl, 0.2)) continue;
                for (const [x, y] of p.ring) {
                    const d2 = (y - la) ** 2 + ((x - lo) * kl) ** 2;
                    if (d2 < d2min) { d2min = d2; bester = e; }
                }
            }
        }
        return bester ? landName(bester) : null;
    }

    fetch('countries.geojson?v=5.1.1')      // Version in der URL: neue Karte statt einer alten aus dem Zwischenspeicher
        .then(r => r.json())
        .then(land => { laender = land.features; landIndexBauen(land.features); erdeAnwenden(); });
    erdeAnwenden();
    globus.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));   // Handys mit 3-facher Auflösung schonen

    // ================= Legende =================
    // Kompakt: drei große Zahlen, die jeder versteht. Aufgeklappt: jede Art mit Erklärung für alle, die es genau wissen wollen.
    const legendeEl = document.getElementById('legende');
    const zahlEls = {};
    const statEls = {};
    const titelEl = document.createElement('h1');
    const pfeilEl = document.createElement('span');
    const laenderEl = document.createElement('div');
    const statusEl = document.createElement('div');           // Live / Daten veraltet / keine Verbindung
    function statusSetzen(zustand, text) {
        statusEl.className = 'status ' + zustand;
        statusEl.textContent = text;
    }
    statusSetzen('aus', 'Verbinde …');

    function legendeModus() {
        legendeEl.classList.toggle('voll', S.legende === 'voll');
        legendeEl.classList.toggle('versteckt', S.legende === 'aus');
        pfeilEl.textContent = S.legende === 'voll' ? '▴' : '▾';
    }

    (function legendeBauen() {
        const kopf = document.createElement('div');
        kopf.className = 'kopf';
        pfeilEl.className = 'pfeil';
        kopf.append(titelEl, pfeilEl);
        kopf.addEventListener('click', () => {
            S.legende = S.legende === 'voll' ? 'kompakt' : 'voll';
            speichern(); legendeModus();
        });

        const ueberblick = document.createElement('div');
        ueberblick.className = 'ueberblick';
        for (const [id, text] of [['angriffe', 'Angriffe'], ['sperren', 'Gebannt'], ['besucher', 'Besucher']]) {
            const box = document.createElement('div');
            box.className = 'stat ' + id;
            const wert = document.createElement('b');
            wert.textContent = '0';
            const label = document.createElement('span');
            label.className = 'l';
            const punkt = document.createElement('i');
            punkt.className = 'punkt';
            label.append(punkt, text);
            box.append(wert, label);
            ueberblick.appendChild(box);
            statEls[id] = wert;
        }
        laenderEl.className = 'laender';

        const details = document.createElement('div');
        details.className = 'details';
        let letzteGruppe = null;
        for (const [kat, art] of Object.entries(ARTEN)) {
            if (art.gruppe !== letzteGruppe) {
                letzteGruppe = art.gruppe;
                const gk = document.createElement('div');
                gk.className = 'gruppe';
                gk.textContent = GRUPPEN[art.gruppe];
                details.appendChild(gk);
            }
            const zeile = document.createElement('div');
            zeile.className = 'zeile';
            const punkt = document.createElement('span');
            punkt.className = 'punkt';
            punkt.style.background = art.farbe;
            punkt.style.boxShadow = `0 0 6px ${art.farbe}`;
            const name = document.createElement('span');
            name.className = 'name';
            name.textContent = art.name;
            const zahl = document.createElement('span');
            zahl.className = 'zahl';
            zahl.textContent = '0';
            zeile.append(punkt, name, zahl);
            zeile.addEventListener('click', () => {
                verborgen.has(kat) ? verborgen.delete(kat) : verborgen.add(kat);
                zeile.classList.toggle('aus', verborgen.has(kat));
                anzeigen();
            });
            const beschr = document.createElement('div');
            beschr.className = 'beschr';
            beschr.textContent = art.text;
            details.append(zeile, beschr);
            zahlEls[kat] = zahl;
        }
        const hinweis = document.createElement('div');
        hinweis.className = 'hinweis';
        hinweis.textContent = 'Klick auf eine Zeile blendet die Art aus. Fahr mit der Maus über eine Linie für Details.';
        details.appendChild(hinweis);

        legendeEl.append(kopf, ueberblick, laenderEl, details, statusEl);
        legendeModus();
    })();

    function legendeAktualisieren() {
        titelEl.textContent = `Live · letzte ${S.leben} Min`;
        // Anfragen zählen (nicht Linien): jede Linie führt die Zeitpunkte ihrer Anfragen im Zeitfenster
        const n = {};
        aktive.forEach(b => n[b.kat] = (n[b.kat] || 0) + b.zeiten.length);
        for (const kat in zahlEls) zahlEls[kat].textContent = n[kat] || 0;
        statEls.angriffe.textContent = (n.abgewiesen || 0) + (n.login || 0) + (n.scanner || 0);
        statEls.sperren.textContent = n.sperre || 0;
        statEls.besucher.textContent = n.besucher || 0;

        // Herkunft der Angriffe: wie viele Länder, welches am häufigsten
        if (landIndex.length) {
            const summe = {};
            for (const b of aktive) {
                if (b.kat === 'besucher') continue;
                if (b.land === undefined) b.land = landZu(b.startLat, b.startLng);
                if (b.land) summe[b.land] = (summe[b.land] || 0) + b.zeiten.length;
            }
            const namen = Object.keys(summe);
            laenderEl.textContent = namen.length
                ? `aus ${namen.length} ${namen.length === 1 ? 'Land' : 'Ländern'} · meiste: ${namen.reduce((a, c) => summe[c] > summe[a] ? c : a)}`
                : '';
        }
    }
    legendeAktualisieren();

    // ================= Tooltip beim Überfahren einer Linie =================
    // Die Linien sind sehr dünn. Deshalb wird nicht auf die Linie selbst gezielt, sondern die nächste Linie im Umkreis
    // von ein paar Pixeln gesucht (Punkte der Kurve auf den Bildschirm projiziert, Rückseite der Erde ausgeblendet).
    const tipEl = document.getElementById('tip');
    const tipTitel = document.createElement('div'), tipHerkunft = document.createElement('div'),
          tipAnfragen = document.createElement('div'), tipZuletzt = document.createElement('div'),
          tipText = document.createElement('div');
    tipTitel.className = 'tip-titel';
    tipText.className = 'tip-text';
    tipEl.append(tipTitel, tipHerkunft, tipAnfragen, tipZuletzt, tipText);
    const HOVER_PX = 14;
    let hoverListe = [];
    let hoverStand = 0;
    let maus = { x: 0, y: 0, ueberGlobus: false, gedrueckt: false };
    let hoverGeplant = false;

    function hoverListeAufbauen() {
        const liste = [];
        globus.scene().traverse(o => {
            if (o.__globeObjType !== 'arc' || !o.__data) return;
            const m = o.children[0];
            const pfad = m && m.geometry && m.geometry.parameters && m.geometry.parameters.path;
            if (pfad) liste.push({ bogen: o.__data, pts: pfad.getSpacedPoints(24) });
        });
        hoverListe = liste;
        hoverStand = performance.now();
        hoverVeraltet = false;
    }

    function naechsteLinie(mx, my) {
        const cam = globus.camera(), r = globus.renderer().domElement.getBoundingClientRect(), c = cam.position;
        let beste = null, besteD = HOVER_PX * HOVER_PX, tmp = null;
        for (const item of hoverListe) {
            for (const p of item.pts) {
                // Verdeckt die Erde diesen Punkt? (Strecke Kamera -> Punkt kommt der Kugel zu nahe)
                const dx = p.x - c.x, dy = p.y - c.y, dz = p.z - c.z;
                const t = Math.max(0, Math.min(1, -(c.x * dx + c.y * dy + c.z * dz) / (dx * dx + dy * dy + dz * dz)));
                const qx = c.x + t * dx, qy = c.y + t * dy, qz = c.z + t * dz;
                if (qx * qx + qy * qy + qz * qz < 9900) continue;
                tmp = tmp || new p.constructor();
                tmp.copy(p).project(cam);
                const sx = r.left + (tmp.x + 1) / 2 * r.width, sy = r.top + (1 - tmp.y) / 2 * r.height;
                const d2 = (sx - mx) ** 2 + (sy - my) ** 2;
                if (d2 < besteD) { besteD = d2; beste = item.bogen; }
            }
        }
        return beste;
    }

    const zahl = (v) => v.toLocaleString('de-DE', { maximumFractionDigits: 1 });
    const koordText = (la, lo) => `${zahl(Math.abs(la))}° ${la >= 0 ? 'N' : 'S'}, ${zahl(Math.abs(lo))}° ${lo >= 0 ? 'O' : 'W'}`;
    function vor(ms) {
        const s = Math.max(0, Math.round(ms / 1000));
        if (s < 60) return `vor ${s} s`;
        const m = Math.round(s / 60);
        return m < 60 ? `vor ${m} Min` : `vor ${Math.round(m / 60)} Std`;
    }

    function tooltipFuellen(b) {
        if (b.land === undefined) b.land = landZu(b.startLat, b.startLng);
        const art = ARTEN[b.kat];
        tipTitel.textContent = art.name;
        tipTitel.style.color = art.farbe;
        tipHerkunft.textContent = `Herkunft: ${b.land || 'unbekannt'} (ca. ${koordText(b.startLat, b.startLng)})`;
        const n = b.zeiten.length;
        tipAnfragen.textContent = `${n} ${n === 1 ? 'Anfrage' : 'Anfragen'} in den letzten ${S.leben} Min`;
        tipZuletzt.textContent = `zuletzt ${vor(Date.now() - Math.max(...b.zeiten))}`;
        tipText.textContent = art.text;
    }

    function hoverSetzen(b) {
        if (b !== hoverBogen) {
            hoverBogen = b;
            globus.renderer().domElement.style.cursor = b ? 'pointer' : '';
            anzeigen();                                   // die überfahrene Linie wird dicker
        }
        if (!b) { tipEl.style.display = 'none'; return; }
        tooltipFuellen(b);
        tipEl.style.display = 'block';
        const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
        tipEl.style.left = Math.max(8, Math.min(maus.x + 16, innerWidth - w - 8)) + 'px';
        tipEl.style.top = Math.max(8, Math.min(maus.y + 16, innerHeight - h - 8)) + 'px';
    }

    function hoverPruefen() {
        hoverGeplant = false;
        if (!maus.ueberGlobus || maus.gedrueckt) { hoverSetzen(null); return; }   // beim Drehen kein Tooltip
        if (hoverVeraltet && performance.now() - hoverStand > 400) hoverListeAufbauen();
        hoverSetzen(naechsteLinie(maus.x, maus.y));
    }

    function hoverPlanen() {
        if (!hoverGeplant) { hoverGeplant = true; requestAnimationFrame(hoverPruefen); }
    }

    window.addEventListener('pointermove', e => {
        maus = { x: e.clientX, y: e.clientY, ueberGlobus: e.target === globus.renderer().domElement, gedrueckt: e.buttons !== 0 };
        hoverPlanen();
    });
    window.addEventListener('pointerdown', e => {           // Handy: Antippen zeigt den Tooltip kurz an
        maus = { x: e.clientX, y: e.clientY, ueberGlobus: e.target === globus.renderer().domElement, gedrueckt: false };
        hoverPlanen();
        if (e.pointerType === 'touch') setTimeout(() => { maus.ueberGlobus = false; hoverPlanen(); }, 3500);
    });
    document.addEventListener('pointerleave', () => { maus.ueberGlobus = false; hoverPlanen(); });

    // ================= Einstellungsmenü =================
    (function menueBauen() {
        const menue = document.getElementById('menue');
        const zahnrad = document.getElementById('zahnrad');
        zahnrad.addEventListener('click', () => menue.classList.toggle('offen'));

        const eingaben = {};
        const uebernehmen = (key, wert) => {
            S[key] = wert;
            speichern();
            if (key === 'look' || key === 'hintergrund' || key === 'atmosphaere' || key === 'gitter' ||
                key === 'rotation' || key === 'rotTempo' || key === 'scanlines' || key === 'scanStaerke') erdeAnwenden();
            if (key === 'leben') altern();
            if (key === 'legende') legendeModus();
            if (key === 'staerke' || key === 'hoehe') anzeigen();
        };

        for (const p of MENUE) {
            if (p.titel) {
                const h = document.createElement('h2');
                h.textContent = p.titel;
                menue.appendChild(h);
                continue;
            }
            const zeile = document.createElement('label');
            const text = document.createElement('span');
            text.textContent = p.label;
            let eingabe, wertEl = null;
            if (p.art === 'auswahl') {
                eingabe = document.createElement('select');
                for (const [wert, name] of p.optionen) {
                    const o = document.createElement('option');
                    o.value = wert; o.textContent = name;
                    eingabe.appendChild(o);
                }
                eingabe.addEventListener('change', () => uebernehmen(p.key, eingabe.value));
            } else if (p.art === 'schalter') {
                eingabe = document.createElement('input');
                eingabe.type = 'checkbox';
                eingabe.addEventListener('change', () => uebernehmen(p.key, eingabe.checked));
            } else {
                eingabe = document.createElement('input');
                eingabe.type = 'range';
                eingabe.min = p.min; eingabe.max = p.max; eingabe.step = p.schritt;
                wertEl = document.createElement('span');
                wertEl.className = 'wert';
                eingabe.addEventListener('input', () => {
                    const v = parseFloat(eingabe.value);
                    wertEl.textContent = v;
                    uebernehmen(p.key, v);
                });
            }
            eingaben[p.key] = { eingabe, wertEl, art: p.art };
            const rechts = document.createElement('span');
            rechts.style.display = 'flex'; rechts.style.alignItems = 'center'; rechts.style.gap = '6px';
            rechts.append(eingabe);
            if (wertEl) rechts.append(wertEl);
            zeile.append(text, rechts);
            menue.appendChild(zeile);
        }

        function werteZeigen() {
            for (const key in eingaben) {
                const { eingabe, wertEl, art } = eingaben[key];
                if (art === 'schalter') eingabe.checked = S[key];
                else eingabe.value = S[key];
                if (wertEl) wertEl.textContent = S[key];
            }
        }
        werteZeigen();

        const zurueck = document.createElement('button');
        zurueck.textContent = 'Zurücksetzen';
        zurueck.addEventListener('click', () => {
            Object.assign(S, STANDARD);
            speichern(); werteZeigen(); erdeAnwenden(); altern(); anzeigen(); legendeModus();
        });
        menue.appendChild(zurueck);
    })();

    // ================= Live-Daten =================
    let gesehen = new Set();
    let erstesMal = true;
    const schluessel = e => `${e.t}|${e.k}|${e.la}|${e.lo}`;

    // Ereignisse gleichmäßig über das Abfrage-Intervall verteilen, damit nicht alle im selben Moment starten
    function abspielen(liste) {
        const abstand = Math.min(300, POLL_MS / Math.max(liste.length, 1));
        liste.forEach((e, i) => setTimeout(() => neuerBogen(e), i * abstand));
    }

    let fehlversuche = 0;
    async function nachladen() {
        if (document.hidden) return;                          // Tab im Hintergrund: nichts laden
        try {
            const r = await fetch('data/live-public.json?' + Date.now(), { cache: 'no-store' });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const d = await r.json();
            fehlversuche = 0;

            // Wie alt sind die Daten? Serverzeit aus dem Date-Header, damit eine falsche Uhr am Gerät nicht täuscht.
            const serverJetzt = Date.parse(r.headers.get('date') || '') / 1000 || Date.now() / 1000;
            const alter = serverJetzt - d.generated;
            if (alter > 120) statusSetzen('alt', `Daten veraltet (${Math.round(alter / 60)} Min)`);
            else statusSetzen('live', 'Live');

            // Format: events = [[Zeit, Art-Nummer, Breite, Länge], ...]
            const ereignisse = d.events
                .map(([t, ki, la, lo]) => ({ t, k: ART_NACH_INDEX[ki], la, lo }))
                .filter(e => ARTEN[e.k]);
            const neu = ereignisse.filter(e => !gesehen.has(schluessel(e))).sort((a, b) => a.t - b.t);
            gesehen = new Set(ereignisse.map(schluessel));

            if (erstesMal) {
                erstesMal = false;
                const frisch = [];
                neu.forEach(e => {
                    const alterMs = Math.max(0, d.generated - e.t) * 1000;
                    if (alterMs >= lebenMs()) return;
                    if (alterMs < FRISCH_S * 1000) frisch.push(e);
                    else neuerBogen(e, true, alterMs);      // liegt gleich fertig und schon leicht verblasst da
                });
                abspielen(frisch);
            } else {
                abspielen(neu);
            }
        } catch (err) {
            if (++fehlversuche >= 3) statusSetzen('aus', 'Keine Verbindung');
            console.warn('Nachladen fehlgeschlagen', err);
        }
    }

    // Kommt der Tab nach längerer Pause zurück: wie beim ersten Laden aufholen, nicht alles auf einmal abspielen
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) { erstesMal = true; nachladen(); }
    });

    nachladen();
    setInterval(nachladen, POLL_MS);
