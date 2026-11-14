#tests fuer senden-check, arbeit-branch, projekt-trailer, trocken-senden
#kein cursor-fenster, nichts senden, nichts pushen
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

def finde_zentrale_ordner():
    kandidaten = []
    umg = os.environ.get("GROK_ZENTRALE") or ""
    if umg:
        kandidaten.append(Path(umg) / "bruecke")
    ort = Path(__file__).resolve().parent / "ort.json"
    if ort.is_file():
        try:
            daten = json.loads(ort.read_text(encoding="utf-8"))
            wurzel = (daten or {}).get("wurzel") or ""
            if wurzel:
                kandidaten.append(Path(wurzel) / "bruecke")
        except (OSError, json.JSONDecodeError):
            pass
    for p in kandidaten:
        if (p / "zentrale.py").is_file():
            return p
    return None


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import loop
import tipper


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s%s" % (" ".join(args), r.stdout, r.stderr))
    return r


def schreib(pfad, text):
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    Path(pfad).write_text(text, encoding="utf-8")


class SendenCheck(unittest.TestCase):
    def test_feld_leer(self):
        self.assertTrue(tipper.senden_war_erfolgreich("hallo", "", False, "alt", "alt"))

    def test_stop_knopf(self):
        self.assertTrue(tipper.senden_war_erfolgreich("hallo", "hallo", True, "alt", "alt"))

    def test_chat_gewachsen(self):
        self.assertTrue(tipper.senden_war_erfolgreich("hallo", "hallo", False, "vorher", "vorher\nhallo"))

    def test_neuer_text_im_chat(self):
        self.assertTrue(tipper.senden_war_erfolgreich("bitte mach x", "bitte mach x", False, "system", "system\nbitte mach x"))

    def test_noch_nichts(self):
        self.assertFalse(tipper.senden_war_erfolgreich("hallo", "hallo", False, "gleich", "gleich"))

    def test_altes_verhalten_waere_zu_frueh(self):
        #0.5s nach enter ist das feld oft noch voll, das allein darf nicht mehr als misserfolg gelten
        self.assertFalse(tipper.senden_war_erfolgreich("lang", "lang", False, "x", "x"))


class StatusRegeln(unittest.TestCase):
    def test_fertig(self):
        self.assertEqual(loop.status_nach_antwort("fertig", 1), "fertig")

    def test_korrektur(self):
        self.assertEqual(loop.status_nach_antwort("korrektur_noetig", 1), "korrektur")

    def test_drei_dann_frage(self):
        self.assertEqual(loop.status_nach_antwort("korrektur_noetig", 3), "frage")
        self.assertEqual(loop.status_nach_antwort("korrektur_noetig", 2), "korrektur")

    def test_verstoss(self):
        self.assertEqual(loop.status_nach_antwort("fertig", 1, True), "frage")

    def test_frage_und_blockiert(self):
        self.assertEqual(loop.status_nach_antwort("frage", 1), "frage")
        self.assertEqual(loop.status_nach_antwort("blockiert", 1), "blockiert")


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = Path(self.tmp.name) / "hub"
        self.lane = self.hub / "_zentrale-test"
        self.lane.mkdir(parents=True)
        schreib(
            self.hub / "projekte" / "register.json",
            json.dumps({
                "projekte": [{
                    "id": "zentrale-test",
                    "name": "_zentrale-test",
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
        self.hash_main = git(self.lane, "rev-parse", "HEAD").stdout.strip()
        git(self.lane, "checkout", "-b", "arbeit/t1")
        schreib(self.lane / "readme-t1.txt", "nur t1\n")
        git(self.lane, "add", "readme-t1.txt")
        git(self.lane, "commit", "-m", "arbeit t1")
        self.hash_t1 = git(self.lane, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_name_nicht_ordner(self):
        self.assertEqual(loop.register_name(str(self.lane)), "zentrale-test")
        self.assertEqual(loop.projekt_im_trailer(str(self.lane)), "zentrale-test")
        self.assertNotEqual(loop.projekt_im_trailer(str(self.lane)), "_zentrale-test")

    def test_branch_t2_kommt_von_main(self):
        #aktuell sind wir auf arbeit/t1
        self.assertEqual(loop.git_aktuell(str(self.lane)), "arbeit/t1")
        name, hinweis = loop.arbeit_branch_setzen(str(self.lane), "t2", {"basis": "main"})
        self.assertEqual(name, "arbeit/t2")
        self.assertEqual(loop.git_aktuell(str(self.lane)), "arbeit/t2")
        basis = git(self.lane, "merge-base", "arbeit/t2", "main").stdout.strip()
        self.assertEqual(basis, self.hash_main)
        #t1-commit darf nicht in t2 stecken
        r = git(self.lane, "merge-base", "--is-ancestor", self.hash_t1, "arbeit/t2", check=False)
        self.assertNotEqual(r.returncode, 0, "arbeit/t2 darf t1 nicht enthalten")

    def test_zentrale_branch_anlegen_von_main(self):
        zentrale_ordner = finde_zentrale_ordner()
        if not zentrale_ordner:
            self.skipTest("zentrale.py nicht gefunden")
        sys.path.insert(0, str(zentrale_ordner))
        import zentrale
        ok, msg = zentrale.branch_anlegen(self.lane, "arbeit/t2")
        self.assertTrue(ok, msg)
        self.assertIn("main", msg)
        self.assertEqual(zentrale.aktueller_branch(self.lane), "arbeit/t2")
        basis = git(self.lane, "merge-base", "arbeit/t2", "main").stdout.strip()
        self.assertEqual(basis, self.hash_main)

    def test_trocken_senden_und_commit_trailer(self):
        lane = str(self.lane)
        #loop anlegen
        loop.cmd_init(loop.ns(lane=lane, modus="schrittweise", projekt=""))
        plan, p = loop.lade_plan(lane)
        self.assertEqual(plan.get("projekt"), "zentrale-test")
        self.assertEqual(plan.get("basis"), "main")
        loop.cmd_aufgabe(loop.ns(id="t2", lane=lane, ziel="lege t2.txt an", fenster="6685536", dateien="t2.txt", fertig_wenn="da"))
        #schritt trocken: hwnd muss nicht leben
        loop.cmd_schritt(loop.ns(lane=lane, trocken=True))
        self.assertEqual(loop.git_aktuell(lane), "arbeit/t2")
        #datei und antwort wie nach einem echten fenster-lauf
        schreib(self.lane / "t2.txt", "hallo aus dem test\n")
        loop.schreib_json(os.path.join(p["antwort"], "t2.json"), {
            "id": "t2",
            "status": "fertig",
            "geaenderte_dateien": ["t2.txt"],
            "tests": "ok",
            "offene_fragen": [],
            "kurz": "ok",
        })
        #trocken senden: kein fenster, wertet antwort aus, committet nicht
        loop.cmd_senden(loop.ns(lane=lane, ja=True, trocken=True, max_min=1))
        plan, p = loop.lade_plan(lane)
        aufg = plan["aufgaben"][0]
        self.assertEqual(aufg["status"], "fertig")
        self.assertEqual(int(aufg["versuche"]), 1)
        #working tree noch uncommittet, trocken committet nicht
        st = git(self.lane, "status", "--porcelain").stdout
        self.assertIn("t2.txt", st)
        #jetzt echter lokaler commit-befehl
        loop.cmd_commit(loop.ns(lane=lane, auftrag="t2", art="fenster", ziel="lege t2.txt an"))
        log = git(self.lane, "log", "-1", "--format=%an%n%B").stdout
        self.assertIn("agent-fenster", log)
        self.assertIn("Auftrag: t2", log)
        self.assertIn("Projekt: zentrale-test", log)
        self.assertNotIn("Projekt: _zentrale-test", log)
        self.assertEqual(loop.git_aktuell(lane), "arbeit/t2")

    def test_drei_korrekturen_dann_fragen(self):
        lane = str(self.lane)
        loop.cmd_init(loop.ns(lane=lane, modus="schrittweise", projekt="zentrale-test"))
        loop.cmd_aufgabe(loop.ns(id="t3", lane=lane, ziel="etwas", fenster="1", dateien="", fertig_wenn=""))
        for i in range(3):
            loop.schreib_json(os.path.join(str(self.lane), ".loop", "antwort", "t3.json"), {
                "id": "t3",
                "status": "korrektur_noetig",
                "offene_fragen": [],
                "kurz": "noch nicht",
            })
            loop.cmd_schritt(loop.ns(lane=lane, trocken=True))
            loop.cmd_senden(loop.ns(lane=lane, ja=True, trocken=True, max_min=1))
        plan, p = loop.lade_plan(lane)
        aufg = [a for a in plan["aufgaben"] if a["id"] == "t3"][0]
        self.assertEqual(int(aufg["versuche"]), 3)
        self.assertEqual(aufg["status"], "frage")
        fragen = Path(p["fragen"]).read_text(encoding="utf-8")
        self.assertIn("nach 3 korrekturen nicht fertig", fragen)

    def test_commit_auftrag_ist_pflicht(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "loop.py"), "commit", "--lane", str(self.lane), "--art", "fenster"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0)
        text = (r.stderr or "") + (r.stdout or "")
        self.assertTrue("auftrag" in text.lower() or "required" in text.lower() or "pflicht" in text.lower())


if __name__ == "__main__":
    #nichts an bestehenden projekten aendern, nur temp-ordner
    unittest.main(verbosity=2)
