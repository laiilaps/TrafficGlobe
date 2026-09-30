import json, os, re, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collector"))
import globe_collector as gc
import daemon

NOW = 1727690000
IPV4 = re.compile(r"(\d{1,3}\.){3}\d{1,3}")
UFW = ("2026-09-30T12:36:00.915126+02:00 server kernel: [UFW BLOCK] IN=eth0 OUT= MAC=aa SRC=8.8.4.4 "
       "DST=1.2.3.4 LEN=40 TOS=0x00 PREC=0x00 TTL=55 ID=0 PROTO=TCP SPT=23399 DPT=61979 WINDOW=65535 RES=0x00 SYN URGP=0")


class Parsers(unittest.TestCase):
    def test_ufw(self):
        ip, kind, port, ts = gc.parse_ufw(UFW)
        self.assertEqual((str(ip), kind, port, ts), ("8.8.4.4", "block", 61979, 1790764560))
        self.assertIsNone(gc.parse_ufw(UFW.replace("OUT=", "OUT=eth1")))
        self.assertIsNone(gc.parse_ufw(UFW.replace("8.8.4.4", "192.168.1.5")))
        self.assertIsNotNone(gc.parse_ufw(UFW.replace("8.8.4.4", "2a09:bac0::1")))

    def test_ssh(self):
        p = "2026-09-30T12:36:00.7+02:00 server sshd[1]: "
        for text in ("Invalid user admin from 8.8.4.4 port 5",
                     "Connection closed by invalid user admin 8.8.4.4 port 5 [preauth]",
                     "User root from 8.8.4.4 not allowed because not listed in AllowUsers",
                     "Failed password for root from 8.8.4.4 port 5 ssh2"):
            self.assertEqual(gc.parse_ssh(p + text)[1], "ssh_fail", text)
        self.assertEqual(gc.parse_ssh(p + "Accepted publickey for me from 8.8.4.4 port 5 ssh2: ED25519 SHA256:x")[1], "ssh_ok")
        self.assertIsNone(gc.parse_ssh(p + "pam_unix(sshd:session): session opened for user me"))

    def test_ssh_log_injection(self):
        """Der Benutzername kommt vom Angreifer. Eine eingeschleuste Fake-IP darf nicht gewinnen."""
        p = "2026-09-30T12:36:00+02:00 s sshd[1]: "
        fake = "x from 1.2.3.4 port 9 ssh2 y"
        faelle = [
            f"Invalid user {fake} from 8.8.4.4 port 5",
            f"Failed password for invalid user {fake} from 8.8.4.4 port 5 ssh2",
            f"User {fake} from 8.8.4.4 not allowed because not listed in AllowUsers",
            f"Connection closed by invalid user {fake} 8.8.4.4 port 5 [preauth]",
            f"maximum authentication attempts exceeded for {fake} from 8.8.4.4 port 5 ssh2 [preauth]",
            f"error: maximum authentication attempts exceeded for invalid user {fake} from 8.8.4.4 port 5 ssh2 [preauth]",
            f"Disconnecting invalid user {fake} 8.8.4.4 port 5: Too many authentication failures [preauth]",
        ]
        for f in faelle:
            r = gc.parse_ssh(p + f)
            self.assertIsNotNone(r, f)
            self.assertEqual(str(r[0]), "8.8.4.4", f)

    def test_ban(self):
        self.assertEqual(gc.parse_ban("2026-09-30 12:34:56,183 fail2ban.actions  [1]: NOTICE  [sshd] Ban 8.8.4.4")[1], "ban")
        self.assertIsNone(gc.parse_ban("2026-09-30 12:34:56,183 fail2ban.actions  [1]: NOTICE  [sshd] Unban 8.8.4.4"))
        self.assertIsNone(gc.parse_ban("2026-09-30 12:34:56,183 fail2ban.filter  [1]: INFO    [sshd] Found 8.8.4.4 - 2026"))

    def test_nginx(self):
        l = '172.19.0.2 - - [30/Sep/2026:09:15:48 +0000] "GET / HTTP/1.1" 200 2860 "-" "Mozilla" "8.8.4.4"'
        self.assertEqual(gc.parse_nginx(l)[1], "http_ok")
        self.assertEqual(gc.parse_nginx(l.replace(" 200 ", " 404 "))[1], "http_scan")
        self.assertIsNone(gc.parse_nginx(l.replace("Mozilla", "Uptime-Kuma/1.2")))
        self.assertIsNone(gc.parse_nginx(l, ignore_ips={"8.8.4.4"}))
        self.assertIsNone(gc.parse_nginx('2026/09/30 10:40:15 [warn] 22#22: *5 upstream sent duplicate header, client: 172.19.0.2'))
        self.assertIsNone(gc.parse_nginx(l.replace('"8.8.4.4"', '"8.8.4.4, 1.1.1.1"')))  # strikt


class Export(unittest.TestCase):
    def events(self):
        ev = [gc.make_event(NOW - 3600 - i * 61, "http_ok", (50.31, 8.77, "DE"), 443) for i in range(3)]
        ev.append(gc.make_event(NOW - 4000, "http_ok", (10.4, 20.6, "XX"), 443))   # k=1
        ev.append(gc.make_event(NOW - 100, "http_ok", (50.3, 8.7, "DE"), 443))     # jünger als 15 min
        ev.append(gc.make_event(NOW - 500, "block", (31.04, 121.4, "CN"), 23))
        return ev

    def test_events_are_coarse_from_the_start(self):
        v = gc.make_event(NOW, "http_ok", (50.31, 8.77, "DE"), 443)
        a = gc.make_event(NOW, "block", (31.04, 121.46, "CN"), 23)
        self.assertEqual((v["la"], v["lo"]), (50.0, 9.0))       # Besucher: ganze Grad
        self.assertEqual((a["la"], a["lo"]), (31.0, 121.5))     # Angriffe: 0,1°
        self.assertEqual(set(v), {"t", "k", "la", "lo", "cc", "p"})   # keine Zusatzfelder

    def test_public_with_defaults(self):
        pub = gc.build_public(self.events(), NOW)
        self.assertEqual(pub["totals"]["http_ok"], 3)     # 15 min Verzögerung und k=3 greifen
        self.assertEqual(pub["totals"]["block"], 1)
        self.assertEqual(pub["ports"], [[23, 1]])
        for m, ki, la, lo, n in pub["events"]:
            self.assertEqual(m % 60, 0)

    def test_public_without_delay_and_k(self):
        pub = gc.build_public(self.events(), NOW, delay=0, k_min=1)
        self.assertEqual(pub["totals"]["http_ok"], 5)

    def test_live_format(self):
        live = gc.build_live(self.events(), NOW, NOW - 600, delay=0, k_min=1)
        self.assertEqual(set(live), {"v", "generated", "window", "events"})     # keine Artennamen, kein Ziel
        for verboten in ("ssh", "ban", "block", "fail2ban", "ufw", "target", "kinds"):
            self.assertNotIn(verboten, json.dumps(live).lower())
        self.assertTrue(all(len(e) == 4 for e in live["events"]))
        self.assertEqual([e[0] for e in live["events"] if e[1] == 0], [NOW - 500] )  # block
        self.assertNotIn("me", live); self.assertNotIn("own", json.dumps(live))
        strict = gc.build_live(self.events(), NOW, NOW - 4500)                        # Standardregeln
        self.assertEqual(sum(1 for e in strict["events"] if e[1] == 4), 3)

    def test_dedupe(self):
        e = gc.make_event(NOW, "block", (1.0, 2.0, "XX"), 1)
        self.assertEqual(len(gc.dedupe([e, dict(e, t=NOW + 5)])), 1)


class FakeGeo:
    def lookup(self, ip):
        return (31.23, 121.47, "CN") if ip.version == 4 else (52.5, 13.4, "DE")


class GeoReload(unittest.TestCase):
    """Die Geo-Datenbank wird monatlich ausgetauscht: Der Collector muss die neue Datei ohne Neustart übernehmen."""

    class Leser:
        def __init__(self, cc): self.cc, self.zu = cc, False
        def get(self, ip): return {"location": {"latitude": 1.0, "longitude": 2.0}, "country": {"iso_code": self.cc}}
        def close(self): self.zu = True

    def setUp(self):
        self.pfad = os.path.join(tempfile.mkdtemp(), "geo.mmdb")

    def schreibe(self, text, mtime):
        with open(self.pfad, "w") as f:
            f.write(text)
        os.utime(self.pfad, (mtime, mtime))

    def opener(self, pfad):
        with open(pfad) as f:
            t = f.read().strip()
        if t == "KAPUTT":
            raise ValueError("keine gueltige Datenbank")
        return self.Leser(t)

    def test_new_file_is_picked_up_and_old_reader_closed(self):
        self.schreibe("AA", 1000)
        g = gc.Geo(self.pfad, opener=self.opener)
        alt = g.reader
        self.assertEqual(g.lookup(__import__("ipaddress").ip_address("8.8.4.4"))[2], "AA")
        self.schreibe("BB", 2000); g._checked = 0
        self.assertEqual(g.lookup(__import__("ipaddress").ip_address("8.8.4.4"))[2], "BB")
        self.assertTrue(alt.zu)
        self.assertEqual(g.reloads, 1)

    def test_broken_file_keeps_old_reader(self):
        self.schreibe("AA", 1000)
        g = gc.Geo(self.pfad, opener=self.opener)
        self.schreibe("KAPUTT", 2000); g._checked = 0
        self.assertEqual(g.lookup(__import__("ipaddress").ip_address("8.8.4.4"))[2], "AA")   # läuft mit der alten weiter
        self.assertEqual(g.reloads, 0)

    def test_missing_file_is_tolerated(self):
        g = gc.Geo(self.pfad + ".gibtsnicht", opener=self.opener)
        self.assertIsNone(g.lookup(__import__("ipaddress").ip_address("8.8.4.4")))


class Daemon(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for d in ("logs", "out", "nginx"):
            os.mkdir(os.path.join(self.tmp, d))
        self.cfg = {"LOG_DIR": f"{self.tmp}/logs", "NGINX_LOG": f"{self.tmp}/nginx/access.log",
                    "OUT_DIR": f"{self.tmp}/out", "IGNORE_IPS": "7.7.7.7", "PUBLIC_DELAY": "0", "PUBLIC_K_MIN": "1"}
        self.now = 1790764600.0

    def write(self, name, text, mode="a"):
        with open(os.path.join(self.tmp, name), mode) as f:
            f.write(text)

    def out(self, name):
        with open(f"{self.tmp}/out/{name}") as f:
            return f.read()

    def collector(self):
        return daemon.Collector(self.cfg, FakeGeo(), now=lambda: self.now)

    def test_end_to_end_no_ip_and_no_successful_logins(self):
        self.write("logs/ufw.log", UFW + "\n")
        self.write("logs/auth.log", "2026-09-30T12:36:10+02:00 s sshd[1]: Accepted publickey for me from 9.9.9.9 port 1 ssh2\n"
                                    "2026-09-30T12:36:12+02:00 s sshd[2]: Invalid user x from 9.9.9.9 port 1\n")
        c = self.collector()
        self.assertEqual(c.step(), 2)                       # Block + SSH-Fehlversuch, Login wird ignoriert
        for name in ("public/live-public.json", "stats-24h.json", "events.jsonl", "state.json", "status.json"):
            txt = self.out(name)
            self.assertIsNone(IPV4.search(txt.replace("50.11", "")), name)
            self.assertNotIn("ssh_ok", txt)
        self.assertEqual(os.listdir(f"{self.tmp}/out/public"), ["live-public.json"])   # nur das wird ausgeliefert
        live = json.loads(self.out("public/live-public.json"))
        self.assertEqual(sorted(e[1] for e in live["events"]), [0, 1])
        self.assertFalse(any(os.path.exists(f"{self.tmp}/out/{n}") for n in
                             ("live-private.json", "events-private.json")))

    def test_missing_and_unreadable_sources_are_tolerated(self):
        c = self.collector()
        self.assertEqual(c.step(), 0)
        os.chmod(self.tmp + "/logs", 0o000)
        try:
            self.assertEqual(c.step(), 0)
        finally:
            os.chmod(self.tmp + "/logs", 0o755)

    def test_incremental_and_partial_line(self):
        c = self.collector()
        self.write("logs/ufw.log", UFW[:50])
        self.assertEqual(c.step(), 0)
        self.write("logs/ufw.log", UFW[50:] + "\n")
        self.assertEqual(c.step(), 1)
        self.assertEqual(c.step(), 0)

    def test_rotation(self):
        c = self.collector()
        self.write("logs/ufw.log", UFW + "\n")
        self.assertEqual(c.step(), 1)
        os.rename(f"{self.tmp}/logs/ufw.log", f"{self.tmp}/logs/ufw.log.1")
        self.write("logs/ufw.log.1", UFW.replace("12:36:00", "12:50:00") + "\n")
        self.write("logs/ufw.log", UFW.replace("12:36:00", "13:00:00").replace("DPT=61979", "DPT=22") + "\n")
        self.now += 4000
        self.assertEqual(c.step(), 2)

    def test_restart_keeps_state(self):
        self.write("logs/ufw.log", UFW + "\n")
        self.assertEqual(self.collector().step(), 1)
        c2 = self.collector()
        self.assertEqual(len(c2.events), 1)
        self.assertEqual(c2.step(), 0)

    def test_old_fine_grained_events_are_sanitized_on_load(self):
        """Altbestand mit feinen Koordinaten, Stadt und Eigen-Flag wird beim Start bereinigt."""
        t = int(self.now) - 100
        alt = [{"t": t, "k": "block", "la": 31.23, "lo": 121.47, "cc": "CN", "p": 22, "ci": "Shanghai"},
               {"t": t, "k": "http_ok", "la": 50.31, "lo": 8.77, "cc": "DE", "p": 443, "ci": "Frankfurt"},
               {"t": t, "k": "http_ok", "la": 48.1, "lo": 11.5, "cc": "DE", "p": 443, "own": True},
               {"t": t, "k": "ssh_ok", "la": 1.0, "lo": 2.0, "cc": "DE", "p": 22}]
        self.write("out/events.jsonl", "".join(json.dumps(e) + "\n" for e in alt))
        c = self.collector()
        self.assertEqual(len(c.events), 2)                  # eigen und ssh_ok fliegen raus
        txt = self.out("events.jsonl")
        for verboten in ("Shanghai", "Frankfurt", "own", "ssh_ok", "31.23", "50.31"):
            self.assertNotIn(verboten, txt)

    def test_ignored_ip_and_uptime_kuma(self):
        l = '172.19.0.2 - - [30/Sep/2026:10:36:20 +0000] "GET / HTTP/1.1" 200 5 "-" "Mozilla" "%s"\n'
        self.write("nginx/access.log", l % "7.7.7.7" + l % "8.8.4.4")
        self.assertEqual(self.collector().step(), 1)

    def test_line_without_newline_does_not_hang(self):
        """Eine riesige "Zeile" ohne Zeilenumbruch darf den Collector nicht in einer Endlosschleife festhalten."""
        import signal

        def zeitueberschreitung(*_):
            raise AssertionError("read_lines haengt (Endlosschleife)")
        alt = signal.signal(signal.SIGALRM, zeitueberschreitung)
        try:
            with open(f"{self.tmp}/logs/ufw.log", "wb") as f:
                f.write(b"a" * (daemon.MAX_READ + 10))
                f.write(b"\n" + UFW.encode() + b"\n")
            c = self.collector()
            signal.alarm(8)
            n = c.step()
            signal.alarm(0)
            self.assertEqual(n, 1)                          # die echte Zeile danach wird trotzdem gelesen
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, alt)


if __name__ == "__main__":
    unittest.main()
