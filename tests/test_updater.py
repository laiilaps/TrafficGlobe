import datetime, gzip, io, os, sys, tempfile, unittest, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "updater"))
import update as up

JETZT = datetime.datetime(2026, 10, 3, tzinfo=datetime.timezone.utc)


class Antwort:
    def __init__(self, daten, url):
        self._io, self._url = io.BytesIO(daten), url
    def read(self, n=-1): return self._io.read(n)
    def geturl(self): return self._url
    def __enter__(self): return self
    def __exit__(self, *a): return False


def opener_mit(daten):
    return lambda url: Antwort(daten, url)


class Updater(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, up.DB_NAME)
        with open(self.db, "wb") as f: f.write(b"ALT")
        with open(os.path.join(self.dir, up.VERSION_FILE), "w") as f: f.write("2026-09\n")
        self.alte_min = up.MIN_GZ
        up.MIN_GZ = 10                                   # Testdaten sind klein
        self.gz = gzip.compress(b"NEUE-DATENBANK" * 100)

    def tearDown(self):
        up.MIN_GZ = self.alte_min

    def lese(self, name):
        with open(os.path.join(self.dir, name), "rb") as f: return f.read()

    def temps(self):
        return [n for n in os.listdir(self.dir) if n.startswith(".neu")]

    def test_month(self):
        self.assertEqual(up.aktueller_monat(JETZT), "2026-10")
        self.assertEqual(up.aktueller_monat(datetime.datetime(2026, 12, 31, 23, tzinfo=datetime.timezone.utc)), "2026-12")

    def test_success_replaces_atomically_and_cleans_up(self):
        erg, _ = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz), pruefer=lambda p: {"knoten": 1})
        self.assertEqual(erg, "erneuert")
        self.assertEqual(self.lese(up.DB_NAME), b"NEUE-DATENBANK" * 100)
        self.assertEqual(self.lese(up.VERSION_FILE), b"2026-10\n")
        self.assertEqual(self.temps(), [])

    def test_already_current_makes_no_request(self):
        def darf_nicht(url): raise AssertionError("Netzzugriff trotz aktueller Version")
        erg, _ = up.erneuere(self.dir, datetime.datetime(2026, 9, 20, tzinfo=datetime.timezone.utc), opener=darf_nicht)
        self.assertEqual(erg, "aktuell")

    def test_validation_failure_keeps_old_database(self):
        def schlecht(p): raise up.Fehler("Kontrollabfrage falsch")
        erg, text = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz), pruefer=schlecht)
        self.assertEqual(erg, "fehler")
        self.assertEqual(self.lese(up.DB_NAME), b"ALT")               # unverändert
        self.assertEqual(self.lese(up.VERSION_FILE), b"2026-09\n")    # Version nicht hochgezählt
        self.assertEqual(self.temps(), [])

    def test_not_yet_published_is_not_an_error(self):
        def n404(url): raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        erg, _ = up.erneuere(self.dir, JETZT, opener=n404)
        self.assertEqual(erg, "noch-nicht")
        self.assertEqual(self.lese(up.DB_NAME), b"ALT")

    def test_server_error_and_network_error(self):
        def n500(url): raise urllib.error.HTTPError(url, 500, "x", {}, None)
        self.assertEqual(up.erneuere(self.dir, JETZT, opener=n500)[0], "fehler")
        def netz(url): raise urllib.error.URLError("weg")
        self.assertEqual(up.erneuere(self.dir, JETZT, opener=netz)[0], "fehler")
        self.assertEqual(self.lese(up.DB_NAME), b"ALT"); self.assertEqual(self.temps(), [])

    def test_corrupt_archive(self):
        erg, _ = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz[:-20]), pruefer=lambda p: {})
        self.assertEqual(erg, "fehler"); self.assertEqual(self.lese(up.DB_NAME), b"ALT"); self.assertEqual(self.temps(), [])

    def test_too_small_download_rejected(self):
        up.MIN_GZ = 10 ** 6
        erg, text = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz), pruefer=lambda p: {})
        self.assertEqual(erg, "fehler"); self.assertIn("zu klein", text); self.assertEqual(self.lese(up.DB_NAME), b"ALT")

    def test_too_large_download_rejected(self):
        alt = up.MAX_GZ; up.MAX_GZ = 20
        try:
            erg, text = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz), pruefer=lambda p: {})
        finally:
            up.MAX_GZ = alt
        self.assertEqual(erg, "fehler"); self.assertIn("größer", text); self.assertEqual(self.temps(), [])

    def test_decompression_bomb_rejected(self):
        alt = up.MAX_DB; up.MAX_DB = 50
        try:
            erg, text = up.erneuere(self.dir, JETZT, opener=opener_mit(self.gz), pruefer=lambda p: {})
        finally:
            up.MAX_DB = alt
        self.assertEqual(erg, "fehler"); self.assertEqual(self.lese(up.DB_NAME), b"ALT"); self.assertEqual(self.temps(), [])

    def test_foreign_host_rejected(self):
        with self.assertRaises(up.Fehler): up.lade("https://evil.example/x.gz", os.path.join(self.dir, "x"), opener_mit(b""))
        with self.assertRaises(up.Fehler): up.lade("http://download.db-ip.com/x.gz", os.path.join(self.dir, "x"), opener_mit(b""))
        # Antwort kam von woanders (Weiterleitung): ebenfalls ablehnen
        umgeleitet = lambda url: Antwort(self.gz, "https://evil.example/boese.gz")
        erg, _ = up.erneuere(self.dir, JETZT, opener=umgeleitet, pruefer=lambda p: {})
        self.assertEqual(erg, "fehler"); self.assertEqual(self.lese(up.DB_NAME), b"ALT")

    def test_redirect_handler_only_to_same_host(self):
        h = up.NurDbIp()
        with self.assertRaises(up.Fehler):
            h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x")
        with self.assertRaises(up.Fehler):
            h.redirect_request(None, None, 302, "Found", {}, "http://download.db-ip.com/x")

    def test_dry_run_replaces_nothing(self):
        erg, _ = up.erneuere(self.dir, JETZT, dry_run=True, opener=opener_mit(self.gz), pruefer=lambda p: {"knoten": 1})
        self.assertEqual(erg, "geprüft")
        self.assertEqual(self.lese(up.DB_NAME), b"ALT"); self.assertEqual(self.lese(up.VERSION_FILE), b"2026-09\n"); self.assertEqual(self.temps(), [])

    def test_force_reinstalls_current_month(self):
        erg, _ = up.erneuere(self.dir, datetime.datetime(2026, 9, 20, tzinfo=datetime.timezone.utc), force=True,
                             opener=opener_mit(self.gz), pruefer=lambda p: {})
        self.assertEqual(erg, "erneuert")


if __name__ == "__main__":
    unittest.main()
