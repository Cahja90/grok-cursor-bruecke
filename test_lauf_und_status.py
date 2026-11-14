#tests fuer lauf, status.json, haenger, fensterpruefung, register-uebersicht
#kein echtes cursor-fenster, nichts senden, nichts pushen
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import loop
import tipper

from test_senden_und_branch import git, schreib, finde_zentrale_ordner


def reset_hooks():
    loop.warten_fn = None
    loop.pruefen_fn = None
    loop.senden_fn = None
    loop.stopp_fn = None
    loop.vorbereiten_fn = None
    loop.bild_fn = None


class TitelCheck(unittest.TestCase):
    def test_kern(self):
        self.assertEqual(tipper.titel_kern("hallo.txt - demo - Cursor"), "demo")
        self.assertEqual(tipper.titel_kern("demo - Cursor"), "demo")

    def test_passt_gleich(self):
        self.assertTrue(tipper.titel_passt("t4.txt - demo - Cursor", "demo - Cursor"))

    def test_passt_kern(self):
        self.assertTrue(tipper.titel_passt("andere datei - zentrale-test - Cursor", "hallo.txt - zentrale-test - Cursor"))

    def test_passt_nicht(self):
        self.assertFalse(tipper.titel_passt("ganz anderes - Cursor", "zentrale-test - Cursor"))

    def test_kein_erwartet(self):
        self.assertTrue(tipper.titel_passt("irgendwas", None))
        self.assertTrue(tipper.titel_passt("irgendwas", ""))


class LaufTests(unittest.TestCase):
    def setUp(self):
        reset_hooks()
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = Path(self.tmp.name) / "hub"
        self.lane = self.hub / "_zentrale-test"
        self.lane.mkdir(parents=True)
        schreib(
            self.hub / "projekte" / "register.json",
            json.dumps({
                "projekte": [{
                    "id": "zentrale-test",
                    "name": "zentrale-test",
                    "pfad": str(self.lane),
                    "aktiv": True,
                }]
            }, indent=2),
        )
        git(self.lane, "init")
        git(self.lane, "checkout", "-b", "main")
        git(self.lane, "config", "user.name", "dev")
        git(self.lane, "config", "user.email", "dev@example.com")
        schreib(self.lane / "README.md", "anfang\n")
        git(self.lane, "add", "README.md")
        git(self.lane, "commit", "-m", "anfang auf main")
        git(self.lane, "checkout", "-b", "arbeit/t1")
        schreib(self.lane / "readme-t1.txt", "nur t1\n")
        git(self.lane, "add", "readme-t1.txt")
        git(self.lane, "commit", "-m", "arbeit t1")

    def tearDown(self):
        reset_hooks()
        self.tmp.cleanup()

    def _init(self, modus="autonom"):
        loop.cmd_init(loop.ns(lane=str(self.lane), modus=modus, projekt="zentrale-test"))

    def _aufgabe(self, aid, ziel, hwnd="1"):
        loop.cmd_aufgabe(loop.ns(
            lane=str(self.lane), id=aid, ziel=ziel, fenster=hwnd, dateien="", fertig_wenn="datei liegt im ordner"
        ))

    def test_status_nach_init_und_aufgabe(self):
        self._init("schrittweise")
        self._aufgabe("t4", "t4.txt anlegen")
        st = loop.lies_status(str(self.lane))
        self.assertIn("t4", st["offen"])
        self.assertEqual(st["fertig"], [])
        self.assertEqual(st.get("projekt"), "zentrale-test")
        self.assertTrue((self.lane / ".loop" / "status.json").is_file())

    def test_schrittweise_lauf_stoppt_vor_senden(self):
        self._init("schrittweise")
        self._aufgabe("t4", "t4.txt anlegen")
        loop.cmd_lauf(loop.ns(lane=str(self.lane), ja=False, trocken=True, max_min=5))
        plan, _ = loop.lade_plan(str(self.lane))
        aufg = plan["aufgaben"][0]
        self.assertEqual(aufg["status"], "laeuft")
        self.assertEqual(aufg["phase"], "warte_auf_senden")
        self.assertEqual(int(aufg.get("versuche") or 0), 0)
        #kein commit
        commits = [l for l in git(self.lane, "log", "--all", "--oneline").stdout.splitlines() if l.strip()]
        self.assertEqual(len(commits), 2)
        st = loop.lies_status(str(self.lane))
        self.assertEqual(st.get("phase"), "warte_auf_senden")
        self.assertEqual(st.get("aktuell"), "t4")

    def test_autonom_ohne_ja_ohne_trocken_scheitert(self):
        self._init("autonom")
        self._aufgabe("t4", "t4.txt anlegen")
        with self.assertRaises(Exception) as ctx:
            loop.cmd_lauf(loop.ns(lane=str(self.lane), ja=False, trocken=False, max_min=5))
        self.assertIn("--ja", str(ctx.exception))

    def test_autonom_trocken_arbeitet_alle_aufgaben(self):
        self._init("autonom")
        self._aufgabe("t4", "t4.txt mit einer zeile anlegen")
        self._aufgabe("t5", "t5.txt mit einer zeile anlegen")
        #antwort schon da, als haette der worker geschrieben
        for aid in ("t4", "t5"):
            schreib(
                self.lane / ".loop" / "antwort" / ("%s.json" % aid),
                json.dumps({
                    "id": aid, "status": "fertig", "geaenderte_dateien": [aid + ".txt"],
                    "tests": "ok", "offene_fragen": [], "kurz": aid + " angelegt",
                }, ensure_ascii=False),
            )
            schreib(self.lane / ("%s.txt" % aid), aid + " ok\n")
        loop.cmd_lauf(loop.ns(lane=str(self.lane), ja=True, trocken=True, max_min=5))
        plan, _ = loop.lade_plan(str(self.lane))
        stati = {a["id"]: a["status"] for a in plan["aufgaben"]}
        self.assertEqual(stati.get("t4"), "fertig")
        self.assertEqual(stati.get("t5"), "fertig")
        st = loop.lies_status(str(self.lane))
        self.assertIn("t4", st["fertig"])
        self.assertIn("t5", st["fertig"])
        self.assertEqual(st["offen"], [])
        #trocken committet nicht
        branches = git(self.lane, "branch").stdout
        #arbeit-branches duerfen angelegt sein, aber kein neuer commit auf ihnen noetig
        log = git(self.lane, "log", "--all", "--oneline").stdout
        self.assertNotIn("t4.txt", log)
        self.assertNotIn("t5.txt", log)

    def test_korrektur_dann_fertig(self):
        self._init("schrittweise")
        self._aufgabe("t4", "t4.txt anlegen")
        antwort_pfad = self.lane / ".loop" / "antwort" / "t4.json"
        schreib(antwort_pfad, json.dumps({
            "id": "t4", "status": "korrektur_noetig", "geaenderte_dateien": [],
            "tests": "", "offene_fragen": [], "kurz": "noch unfertig",
        }))
        loop.cmd_schritt(loop.ns(lane=str(self.lane), trocken=True))
        loop.cmd_senden(loop.ns(lane=str(self.lane), ja=True, trocken=True, max_min=5))
        plan, _ = loop.lade_plan(str(self.lane))
        self.assertEqual(plan["aufgaben"][0]["status"], "korrektur")
        loop.cmd_schritt(loop.ns(lane=str(self.lane), trocken=True))
        auftrag = json.loads((self.lane / ".loop" / "auftrag" / "t4.json").read_text(encoding="utf-8"))
        self.assertEqual(auftrag.get("art"), "korrektur")
        self.assertIn("noch unfertig", auftrag.get("hinweis") or "")
        schreib(self.lane / "t4.txt", "t4 ok\n")
        schreib(antwort_pfad, json.dumps({
            "id": "t4", "status": "fertig", "geaenderte_dateien": ["t4.txt"],
            "tests": "ok", "offene_fragen": [], "kurz": "ok",
        }))
        loop.cmd_senden(loop.ns(lane=str(self.lane), ja=True, trocken=True, max_min=5))
        plan, _ = loop.lade_plan(str(self.lane))
        self.assertEqual(plan["aufgaben"][0]["status"], "fertig")

    def test_haenger_nach_drei_versuchen_frage(self):
        self._init("autonom")
        self._aufgabe("t4", "t4.txt anlegen")
        loop.cmd_schritt(loop.ns(lane=str(self.lane), trocken=True))
        plan, p = loop.lade_plan(str(self.lane))
        aufg = plan["aufgaben"][0]
        aufg["versuche"] = 1
        loop.speichere_plan(p, plan)
        aufrufe = {"warten": 0, "stopp": 0, "senden": 0}

        def warten(fenster, max_min, titel=None):
            aufrufe["warten"] += 1
            return {"timeout": True, "lief": True, "sekunden": 1}

        def stopp(fenster, titel=None):
            aufrufe["stopp"] += 1

        def senden(fenster, titel=None):
            aufrufe["senden"] += 1

        loop.warten_fn = warten
        loop.stopp_fn = stopp
        loop.senden_fn = senden
        loop.vorbereiten_fn = lambda *a, **k: None
        loop.pruefen_fn = lambda hwnd, titel=None: {"hwnd": int(hwnd), "titel": "demo - Cursor"}
        erg = loop.warte_mit_haenger(str(self.lane), plan, p, aufg, "1", max_min=1, trocken=False)
        self.assertEqual(erg, "haenger")
        self.assertEqual(aufg["status"], "frage")
        fragen = (self.lane / ".loop" / "fragen.md").read_text(encoding="utf-8")
        self.assertIn("haenger", fragen)
        self.assertGreaterEqual(aufrufe["warten"], 3)
        st = loop.lies_status(str(self.lane))
        self.assertEqual(st.get("letzter_fehler"), "haenger")

    def test_fenster_mismatch_bricht_aufgabe_ab(self):
        self._init("autonom")
        self._aufgabe("t4", "t4.txt anlegen")

        def schlecht(hwnd, titel=None):
            raise loop.wo.FensterFehler("fenster stimmt nicht: hwnd %s titel 'anders', erwartet 'demo'" % hwnd)

        loop.pruefen_fn = schlecht
        loop.vorbereiten_fn = lambda *a, **k: None
        loop.senden_fn = lambda *a, **k: None
        loop.warten_fn = lambda *a, **k: {"timeout": False}
        loop.bild_fn = lambda *a, **k: None
        loop.cmd_lauf(loop.ns(lane=str(self.lane), ja=True, trocken=False, max_min=5))
        plan, _ = loop.lade_plan(str(self.lane))
        self.assertEqual(plan["aufgaben"][0]["status"], "frage")
        fragen = (self.lane / ".loop" / "fragen.md").read_text(encoding="utf-8")
        self.assertIn("fenster stimmt nicht", fragen)
        st = loop.lies_status(str(self.lane))
        self.assertIn("fenster stimmt nicht", st.get("letzter_fehler") or "")

    def test_status_alle_zwei_projekte(self):
        anderes = self.hub / "anderes-projekt"
        anderes.mkdir()
        git(anderes, "init")
        git(anderes, "config", "user.email", "dev@example.com")
        git(anderes, "config", "user.name", "dev")
        schreib(anderes / "README.md", "x\n")
        git(anderes, "add", "README.md")
        git(anderes, "commit", "-m", "init")
        reg = json.loads((self.hub / "projekte" / "register.json").read_text(encoding="utf-8"))
        reg["projekte"].append({"id": "anderes", "name": "anderes", "pfad": str(anderes), "aktiv": True})
        schreib(self.hub / "projekte" / "register.json", json.dumps(reg))
        self._init("autonom")
        self._aufgabe("t4", "t4")
        loop.cmd_init(loop.ns(lane=str(anderes), modus="schrittweise", projekt="anderes"))
        daten = loop.status_uebersicht(register=str(self.hub / "projekte" / "register.json"))
        ids = [p["id"] for p in daten["projekte"]]
        self.assertIn("zentrale-test", ids)
        self.assertIn("anderes", ids)
        #kein underscored folder name als id
        self.assertNotIn("_zentrale-test", ids)

    def test_modus_wechseln(self):
        self._init("schrittweise")
        loop.cmd_modus(loop.ns(lane=str(self.lane), modus="autonom"))
        plan, _ = loop.lade_plan(str(self.lane))
        self.assertEqual(plan["modus"], "autonom")

    def test_zentrale_loop_stand_liest_status(self):
        zentrale_ordner = finde_zentrale_ordner()
        if not zentrale_ordner:
            self.skipTest("zentrale.py nicht gefunden")
        sys.path.insert(0, str(zentrale_ordner))
        import zentrale
        self._init("autonom")
        self._aufgabe("t4", "t4")
        stand = zentrale.loop_stand(str(self.lane))
        self.assertEqual(stand["modus"], "autonom")
        self.assertIn("t4", stand["status"]["offen"])
        self.assertEqual(stand["status"]["aktuell"], None)


if __name__ == "__main__":
    reset_hooks()
    unittest.main(verbosity=2)
