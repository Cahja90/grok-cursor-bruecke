#loop: naechste aufgabe an ein cursor-fenster geben, warten, ergebnis sichern
#senden nur mit --ja. in schrittweise nach vorbereiten erst auf ok warten.
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tipper
import window_order as wo

VERBOTEN_STANDARD = ["nichts ausserhalb der lane", "kein git push", "kein deploy", "nichts oeffentliches"]
MAX_KORREKTUREN = 3
_GIT_KW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def jetzt():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def lane_pfad(lane):
    pfad = os.path.abspath(lane)
    if not os.path.isdir(pfad):
        raise wo.FensterFehler("lane nicht gefunden: %s" % pfad)
    return pfad


def liegt_unter(kind, eltern):
    kind = os.path.normcase(os.path.abspath(kind))
    eltern = os.path.normcase(os.path.abspath(eltern))
    return kind == eltern or kind.startswith(eltern + os.sep)


def loop_ordner(lane):
    root = os.path.join(lane, ".loop")
    return {
        "root": root,
        "plan": os.path.join(root, "plan.json"),
        "auftrag": os.path.join(root, "auftrag"),
        "antwort": os.path.join(root, "antwort"),
        "log": os.path.join(root, "log.md"),
        "fragen": os.path.join(root, "fragen.md"),
        "bilder": os.path.join(root, "bilder"),
        "status": os.path.join(root, "status.json"),
        "pid": os.path.join(root, "lauf.pid"),
    }


def lade_plan(lane):
    p = loop_ordner(lane)
    if not os.path.isfile(p["plan"]):
        raise wo.FensterFehler("kein plan.json, erst: loop.py init --lane ...")
    with open(p["plan"], encoding="utf-8") as f:
        plan = json.load(f)
    if not isinstance(plan, dict) or "aufgaben" not in plan:
        raise wo.FensterFehler("plan.json ist ungueltig")
    gespeichert = os.path.normcase(os.path.abspath(plan.get("lane") or ""))
    if gespeichert and gespeichert != os.path.normcase(lane):
        raise wo.FensterFehler("plan.lane passt nicht zum --lane")
    return plan, p


def speichere_plan(p, plan):
    tmp = p["plan"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p["plan"])


def schreib_json(pfad, daten):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, pfad)


def log_an(p, text):
    os.makedirs(p["root"], exist_ok=True)
    with open(p["log"], "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (jetzt(), text))


#test-hooks (unit tests setzen funktionen, sonst None)
warten_fn = None
pruefen_fn = None
senden_fn = None
stopp_fn = None
vorbereiten_fn = None
bild_fn = None


def status_von_plan(plan, extra=None):
    extra = dict(extra or {})
    fertig, offen, fragen = [], [], []
    aktuell = extra.get("aktuell")
    for aufg in plan.get("aufgaben") or []:
        if not isinstance(aufg, dict):
            continue
        aid = str(aufg.get("id") or "")
        st = str(aufg.get("status") or "")
        if not aid:
            continue
        if st == "fertig":
            fertig.append(aid)
        elif st in ("offen", "korrektur", "laeuft"):
            offen.append(aid)
            if aktuell is None and st == "laeuft":
                aktuell = aid
        elif st in ("frage", "blockiert"):
            fragen.append(aid)
    daten = {
        "aktuell": aktuell or None,
        "fertig": fertig,
        "offen": offen,
        "fragen": fragen,
        "letzter_fehler": extra.get("letzter_fehler", ""),
        "zeit": jetzt(),
        "modus": plan.get("modus") or "",
        "phase": extra.get("phase") or "",
        "projekt": plan.get("projekt") or "",
        "lane": plan.get("lane") or "",
    }
    for k, v in extra.items():
        if k not in daten:
            daten[k] = v
    return daten


def schreibe_status(p, plan, extra=None):
    extra = dict(extra or {})
    if "letzter_fehler" not in extra and os.path.isfile(p.get("status") or ""):
        try:
            with open(p["status"], encoding="utf-8") as f:
                alt = json.load(f)
            if isinstance(alt, dict) and alt.get("letzter_fehler"):
                extra["letzter_fehler"] = alt["letzter_fehler"]
        except (OSError, json.JSONDecodeError):
            pass
    daten = status_von_plan(plan, extra)
    schreib_json(p["status"], daten)
    return daten


def lies_status(lane):
    p = loop_ordner(lane)
    if not os.path.isfile(p["status"]):
        if os.path.isfile(p["plan"]):
            try:
                plan, _ = lade_plan(lane)
                return status_von_plan(plan)
            except wo.FensterFehler:
                return {}
        return {}
    try:
        with open(p["status"], encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def suche_register_pfade(start=None, extra=None):
    starts = []
    if extra:
        starts.append(os.path.abspath(extra))
    if start:
        starts.append(os.path.abspath(start))
    starts.append(os.getcwd())
    #optionaler lokaler hinweis, nicht im repo: ort.json neben loop.py oder GROK_ZENTRALE
    ort = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ort.json")
    if os.path.isfile(ort):
        try:
            with open(ort, encoding="utf-8") as f:
                daten = json.load(f)
            wurzel = (daten or {}).get("wurzel") or (daten or {}).get("register") or ""
            if wurzel:
                starts.append(os.path.abspath(wurzel))
        except (OSError, json.JSONDecodeError):
            pass
    umg = os.environ.get("GROK_ZENTRALE") or ""
    if umg:
        starts.append(os.path.abspath(umg))
    gefunden = []
    gesehen = set()
    for s in starts:
        hier = s
        if os.path.isfile(hier) and os.path.basename(hier) == "register.json":
            if hier not in gefunden:
                gefunden.append(hier)
            continue
        if os.path.isdir(hier) and os.path.isfile(os.path.join(hier, "register.json")):
            pfad = os.path.join(hier, "register.json")
            if pfad not in gefunden:
                gefunden.append(pfad)
            continue
        while hier not in gesehen:
            gesehen.add(hier)
            kand = os.path.join(hier, "projekte", "register.json")
            if os.path.isfile(kand) and kand not in gefunden:
                gefunden.append(kand)
                break
            eltern = os.path.dirname(hier)
            if eltern == hier:
                break
            hier = eltern
    return gefunden


def lade_register(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    projekte = []
    for ein in (daten or {}).get("projekte") or []:
        if isinstance(ein, dict) and ein.get("aktiv", True):
            projekte.append(ein)
    return projekte


def projekt_status_eintrag(ein):
    pid = (ein.get("id") or ein.get("name") or "").strip()
    pfad = ein.get("pfad") or ""
    stand = {
        "id": pid,
        "name": ein.get("name") or pid,
        "aktuell": None,
        "fertig": [],
        "offen": [],
        "fragen": [],
        "letzter_fehler": "",
        "zeit": "",
        "modus": "",
        "phase": "",
    }
    if pfad:
        stand["pfad"] = pfad
    if pfad and os.path.isdir(pfad):
        stand.update({k: v for k, v in lies_status(pfad).items() if k in stand or k in ("aktuell", "fertig", "offen", "fragen", "letzter_fehler", "zeit", "modus", "phase", "projekt")})
        stand["id"] = pid
        stand["name"] = ein.get("name") or pid
        stand["pfad"] = pfad
    return stand


def status_uebersicht(lane=None, register=None):
    if lane:
        lane = lane_pfad(lane)
        plan, p = lade_plan(lane)
        daten = lies_status(lane) or status_von_plan(plan)
        daten["id"] = plan.get("projekt") or register_name(lane, plan) or os.path.basename(lane)
        daten["name"] = daten.get("name") or daten["id"]
        daten["pfad"] = lane
        return {"zeit": jetzt(), "projekte": [daten]}
    pfade = suche_register_pfade(extra=register)
    projekte = []
    gesehen = set()
    for pfad in pfade:
        for ein in lade_register(pfad):
            key = os.path.normcase(os.path.abspath(ein.get("pfad") or ein.get("id") or ""))
            if key in gesehen:
                continue
            gesehen.add(key)
            projekte.append(projekt_status_eintrag(ein))
    return {"zeit": jetzt(), "projekte": projekte}


def merke_fenster_titel(aufg, hwnd, pflicht=False):
    if not hwnd:
        return aufg
    titel = ""
    try:
        if pruefen_fn:
            info = pruefen_fn(hwnd, aufg.get("fenster_titel") or None)
            titel = (info or {}).get("titel") or ""
        elif pflicht:
            info = tipper.fenster_pruefen(hwnd, aufg.get("fenster_titel") or None)
            titel = info.get("titel") or ""
        else:
            for f in tipper.cursor_fenster():
                if int(f["hwnd"]) == int(hwnd):
                    titel = f.get("titel") or ""
                    break
    except wo.FensterFehler:
        if pflicht:
            raise
    except Exception:
        if pflicht:
            raise
    if titel:
        aufg["fenster_titel"] = titel
    aufg["fenster_hwnd"] = int(hwnd) if str(hwnd).isdigit() else aufg.get("fenster_hwnd")
    aufg["fenster"] = str(hwnd)
    return aufg


def pruefe_aufgabe_fenster(aufg, pflicht=True):
    hwnd = aufg.get("fenster_hwnd") or aufg.get("fenster")
    if not hwnd:
        raise wo.FensterFehler("aufgabe %s hat kein fenster (hwnd setzen)" % (aufg.get("id") or "?"))
    titel = aufg.get("fenster_titel") or ""
    if pruefen_fn:
        info = pruefen_fn(hwnd, titel or None)
        if info and info.get("titel"):
            aufg["fenster_titel"] = info["titel"]
        return str(hwnd)
    if not pflicht:
        return str(hwnd)
    info = tipper.fenster_pruefen(hwnd, titel or None)
    if info.get("titel") and not titel:
        aufg["fenster_titel"] = info["titel"]
    return str(info["hwnd"])


def rufe_vorbereiten(fenster, text, titel=None):
    if vorbereiten_fn:
        return vorbereiten_fn(fenster, text, titel)
    tipper.cmd_vorbereiten(ns(fenster=str(fenster), text=text, datei=None, modus=None, titel=titel))


def rufe_senden(fenster, titel=None):
    if senden_fn:
        return senden_fn(fenster, titel)
    tipper.cmd_senden(ns(fenster=str(fenster), ja=True, titel=titel))


def rufe_stopp(fenster, titel=None):
    if stopp_fn:
        return stopp_fn(fenster, titel)
    tipper.cmd_stopp(ns(fenster=str(fenster), titel=titel))


def rufe_warten(fenster, max_min, titel=None):
    if warten_fn:
        return warten_fn(fenster, max_min, titel) or {}
    return tipper.cmd_warten(ns(
        fenster=str(fenster), max_min=max_min, takt=5, ruhig_runden=6, zeichen=6000, titel=titel
    )) or {}


def rufe_bild(fenster, datei, titel=None):
    if bild_fn:
        return bild_fn(fenster, datei, titel)
    tipper.cmd_bild(ns(fenster=str(fenster), datei=datei, titel=titel))


def korrektur_auftrag(lane, p, aufg, auftrag):
    #korrektur bekommt den vorherigen stand mit, damit der worker weiss was schief ging
    antwort, _ = lies_antwort(p, aufg)
    if not antwort:
        return auftrag
    auftrag["art"] = "korrektur"
    kurz = (antwort.get("kurz") or "")[:400]
    auftrag["vorher"] = {
        "status": antwort.get("status") or "",
        "kurz": kurz,
        "geaenderte_dateien": list(antwort.get("geaenderte_dateien") or []),
    }
    auftrag["hinweis"] = (
        (auftrag.get("hinweis") or "")
        + " das ist eine korrektur (versuch %s). vorheriger stand: %s. bitte nachbessern und antwort/%s.json neu schreiben."
        % (int(aufg.get("versuche") or 0) + 1, kurz or (antwort.get("status") or "unbekannt"), aufg["id"])
    )
    return auftrag


def warte_mit_haenger(lane, plan, p, aufg, fenster, max_min=60, trocken=False):
    #warten-timeout -> stopp -> nochmal senden, versuche++. nach 3: fragen.md
    if trocken:
        return "ok"
    titel = aufg.get("fenster_titel") or None
    while True:
        pruefe_aufgabe_fenster(aufg, pflicht=True)
        ergebnis = rufe_warten(fenster, max_min, titel)
        if not (ergebnis or {}).get("timeout"):
            return "ok"
        log_an(p, "haenger aufgabe=%s nach %ss, versuch=%s" % (
            aufg["id"], (ergebnis or {}).get("sekunden") or "?", aufg.get("versuche") or 0
        ))
        print("haenger bei aufgabe %s, stopp und ggf. nochmal senden" % aufg["id"])
        if int(aufg.get("versuche") or 0) >= MAX_KORREKTUREN:
            aufg["status"] = "frage"
            aufg["phase"] = "haenger"
            with open(p["fragen"], "a", encoding="utf-8") as f:
                f.write(
                    "\n## %s aufgabe %s\n\nhaenger: warten hat %d mal das zeitlimit erreicht.\n"
                    "optionen: [a] nochmal  [b] aufgabe schliessen  [c] anders, ich schreibs selbst\n"
                    % (jetzt(), aufg["id"], MAX_KORREKTUREN)
                )
            speichere_plan(p, plan)
            schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": "frage", "letzter_fehler": "haenger"})
            return "haenger"
        try:
            rufe_stopp(fenster, titel)
        except wo.FensterFehler as e:
            log_an(p, "stopp nach haenger: %s" % e)
        pruefe_aufgabe_fenster(aufg, pflicht=True)
        text = auftrag_text(lane, p, aufg)
        rufe_vorbereiten(fenster, text, titel)
        rufe_senden(fenster, titel)
        aufg["versuche"] = int(aufg.get("versuche") or 0) + 1
        aufg["phase"] = "gesendet_nach_haenger"
        speichere_plan(p, plan)
        schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": "warte_nach_haenger"})
        log_an(p, "nochmal gesendet nach haenger aufgabe=%s versuch=%s" % (aufg["id"], aufg["versuche"]))


def sperre_lauf(p):
    pfad = p["pid"]
    if os.path.isfile(pfad):
        try:
            alt = int(open(pfad, encoding="utf-8").read().strip() or "0")
        except (OSError, ValueError):
            alt = 0
        lebt = False
        if alt:
            if sys.platform == "win32":
                r = subprocess.run(["tasklist", "/FI", "PID eq %d" % alt], capture_output=True, text=True)
                lebt = str(alt) in (r.stdout or "") and "INFO:" not in (r.stdout or "")
            else:
                try:
                    os.kill(alt, 0)
                    lebt = True
                except OSError:
                    lebt = False
        if lebt:
            raise wo.FensterFehler("loop laeuft schon (pid %s), erst stoppen" % alt)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("%s\n" % os.getpid())


def entsperre_lauf(p):
    try:
        if os.path.isfile(p["pid"]):
            os.remove(p["pid"])
    except OSError:
        pass


def ns(**kw):
    return argparse.Namespace(**kw)


def fenster_als_hwnd(wert, pflicht=True):
    #immer hwnd speichern, nie die listen-nummer
    s = str(wert or "").strip()
    if not s:
        raise wo.FensterFehler("kein fenster angegeben")
    if s.isdigit() and (not pflicht or pruefen_fn is not None):
        return int(s)
    alle = tipper.cursor_fenster()
    if s.isdigit():
        n = int(s)
        for f in alle:
            if f["hwnd"] == n:
                return int(f["hwnd"])
        raise wo.FensterFehler("hwnd %s nicht gefunden, tipper.py fenster zeigt die hwnds" % s)
    f = tipper.waehle(s)
    return int(f["hwnd"])


def naechste_aufgabe(plan):
    for aufg in plan.get("aufgaben") or []:
        if aufg.get("status") in ("offen", "korrektur"):
            return aufg
    return None


def warte_aufgabe(plan):
    treffer = []
    for aufg in plan.get("aufgaben") or []:
        if aufg.get("status") == "laeuft" and aufg.get("phase") == "warte_auf_senden":
            treffer.append(aufg)
    if len(treffer) == 1:
        return treffer[0]
    if len(treffer) > 1:
        raise wo.FensterFehler("mehrere aufgaben warten auf senden, plan pruefen")
    return None


def auftrag_text(lane, p, aufg):
    auftrag_pfad = os.path.join(p["auftrag"], "%s.json" % aufg["id"])
    antwort_pfad = os.path.join(p["antwort"], "%s.json" % aufg["id"])
    return (
        "lies die datei %s komplett und fuehre den auftrag aus.\n\n"
        "regeln: nur im projektordner %s arbeiten. nichts ausserhalb aendern oder loeschen. "
        "kein git push, kein deploy, nichts oeffentliches. nicht selbst committen, das macht der loop.\n\n"
        "wenn du fertig bist oder nicht weiterkommst, schreib genau die datei %s, format:\n"
        '{"id":"%s","status":"fertig","geaenderte_dateien":[],"tests":"ok","offene_fragen":[],"kurz":"..."}\n'
        "status ist fertig, korrektur_noetig, frage oder blockiert."
        % (auftrag_pfad, lane, antwort_pfad, aufg["id"])
    )


def git_aenderungen(lane):
    try:
        root = subprocess.check_output(
            ["git", "-C", lane, "rev-parse", "--show-toplevel"],
            stderr=subprocess.STDOUT, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None, []
    try:
        roh = subprocess.check_output(
            ["git", "-C", lane, "status", "--porcelain", "-uall"],
            stderr=subprocess.STDOUT, text=True,
        )
    except subprocess.CalledProcessError:
        return root, []
    dateien = []
    for zeile in roh.splitlines():
        if not zeile.strip():
            continue
        # status ist 2 zeichen plus leerzeichen, umbenennungen: "R  alt -> neu"
        rest = zeile[3:] if len(zeile) >= 3 else zeile
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if not rest:
            continue
        dateien.append(os.path.abspath(os.path.join(root, rest)))
    return root, dateien


def lane_pruefung(lane):
    root, dateien = git_aenderungen(lane)
    if root is None:
        return "kein_git", [], []
    draussen = [d for d in dateien if not liegt_unter(d, lane)]
    drinnen = [d for d in dateien if liegt_unter(d, lane)]
    return "ok" if not draussen else "verstoss", drinnen, draussen


def git_lauf(lane, args, env=None):
    umg = os.environ.copy()
    if env:
        umg.update(env)
    try:
        fertig = subprocess.run(
            ["git", "-C", lane, *args],
            capture_output=True, text=True, check=False, env=umg, **_GIT_KW,
        )
    except OSError:
        return "", 1
    return ((fertig.stdout or "") + (fertig.stderr or "")), fertig.returncode


def git_aktuell(lane):
    out, code = git_lauf(lane, ["branch", "--show-current"])
    return (out or "").strip() if code == 0 else ""


def git_branch_liste(lane):
    out, code = git_lauf(lane, ["branch", "--format=%(refname:short)"])
    if code != 0:
        return []
    return [z.strip() for z in (out or "").splitlines() if z.strip()]


def git_basis_branch(lane, plan=None):
    branches = set(git_branch_liste(lane))
    bevorzugt = ""
    if plan and plan.get("basis"):
        bevorzugt = str(plan.get("basis") or "").strip()
        if bevorzugt in branches and not bevorzugt.startswith("arbeit/"):
            return bevorzugt
    for name in ("main", "master"):
        if name in branches:
            return name
    aktuell = git_aktuell(lane)
    if aktuell and not aktuell.startswith("arbeit/"):
        return aktuell
    return bevorzugt or aktuell


def arbeit_branch_name(auftrag_id):
    return "arbeit/%s" % auftrag_id


def arbeit_branch_setzen(lane, auftrag_id, plan=None):
    #neuen arbeit-branch von main/basis anlegen, nicht von einem anderen arbeit/* erben
    name = arbeit_branch_name(auftrag_id)
    aktuell = git_aktuell(lane)
    if aktuell == name:
        return name, "schon auf %s" % name
    branches = set(git_branch_liste(lane))
    if name in branches:
        out, code = git_lauf(lane, ["checkout", name])
        if code != 0:
            raise wo.FensterFehler("checkout %s fehlgeschlagen: %s" % (name, (out or "")[:200]))
        return name, "wechsel auf %s" % name
    basis = git_basis_branch(lane, plan)
    if not basis:
        raise wo.FensterFehler("keine basis-branch gefunden (main/master)")
    if aktuell != basis:
        out, code = git_lauf(lane, ["checkout", basis])
        if code != 0:
            raise wo.FensterFehler("checkout basis %s fehlgeschlagen: %s" % (basis, (out or "")[:200]))
    out, code = git_lauf(lane, ["checkout", "-b", name])
    if code != 0:
        raise wo.FensterFehler("branch %s anlegen fehlgeschlagen: %s" % (name, (out or "")[:200]))
    return name, "angelegt von %s" % basis


def register_name(lane, plan=None):
    if plan and (plan.get("projekt") or "").strip():
        return str(plan.get("projekt")).strip()
    start = os.path.abspath(lane)
    hier = start
    gesehen = set()
    while hier not in gesehen:
        gesehen.add(hier)
        kandidat = os.path.join(hier, "projekte", "register.json")
        if os.path.isfile(kandidat):
            try:
                with open(kandidat, encoding="utf-8") as f:
                    daten = json.load(f)
            except (OSError, json.JSONDecodeError):
                daten = {}
            ziel = os.path.normcase(start)
            for ein in daten.get("projekte") or []:
                if not isinstance(ein, dict):
                    continue
                pfad = ein.get("pfad") or ""
                try:
                    if os.path.normcase(os.path.abspath(pfad)) == ziel:
                        return (ein.get("id") or ein.get("name") or "").strip()
                except OSError:
                    continue
        eltern = os.path.dirname(hier)
        if eltern == hier:
            break
        hier = eltern
    return ""


def projekt_im_trailer(lane, plan=None):
    name = register_name(lane, plan)
    if name:
        return name
    #nur falls kein register: ordnername, aber ohne taeuschedes _-prefix erzwingen
    return os.path.basename(os.path.abspath(lane))


def status_nach_antwort(antwort_status, versuche, lane_verstoss=False):
    if lane_verstoss:
        return "frage"
    status = (antwort_status or "").strip()
    if status == "fertig":
        return "fertig"
    if status == "frage":
        return "frage"
    if status == "blockiert":
        return "blockiert"
    if int(versuche or 0) >= MAX_KORREKTUREN:
        return "frage"
    return "korrektur"


def agent_commit(lane, plan, p, auftrag_id, art, ziel=""):
    #lokaler commit als agent-cli / agent-fenster auf arbeit/<id>, kein push
    if not (auftrag_id or "").strip():
        raise wo.FensterFehler("auftrag fehlt, --auftrag ist Pflicht")
    aid = auftrag_id.strip()
    branch, hinweis = arbeit_branch_setzen(lane, aid, plan)
    log_an(p, "branch %s (%s)" % (branch, hinweis))
    wert, drinnen, draussen = lane_pruefung(lane)
    if wert == "verstoss":
        raise wo.FensterFehler("lane-verstoss, kein commit: %s" % ", ".join(draussen))
    if wert == "kein_git":
        raise wo.FensterFehler("kein git in der lane")
    rel = []
    for d in drinnen:
        r = os.path.relpath(d, lane).replace("\\", "/")
        if r.startswith(".loop/") or r.startswith(".dev/laeufe/") or r.endswith(".log"):
            continue
        rel.append(r)
    if not rel:
        return "", "nichts zu committen"
    autor = "agent-cli" if art == "cli" else "agent-fenster"
    env = {
        "GIT_AUTHOR_NAME": autor,
        "GIT_AUTHOR_EMAIL": autor + "@local",
        "GIT_COMMITTER_NAME": autor,
        "GIT_COMMITTER_EMAIL": autor + "@local",
    }
    for r in rel:
        out, code = git_lauf(lane, ["add", "--", r], env=env)
        if code != 0:
            raise wo.FensterFehler("git add fehlgeschlagen: %s %s" % (r, (out or "")[:120]))
    projekt = projekt_im_trailer(lane, plan)
    msg = "%s\n\nAgent: %s\nAuftrag: %s\nProjekt: %s\n" % (
        (ziel or ("auftrag " + aid)).strip()[:120],
        "cli" if art == "cli" else "fenster",
        aid,
        projekt,
    )
    out, code = git_lauf(lane, ["commit", "-m", msg], env=env)
    if code != 0:
        if "nothing to commit" in (out or "").lower():
            return "", "nichts zu committen"
        raise wo.FensterFehler("commit fehlgeschlagen: " + (out or "")[:200])
    hash_, _ = git_lauf(lane, ["rev-parse", "--short", "HEAD"])
    hash_ = (hash_ or "").strip()
    log_an(p, "commit %s art=%s auftrag=%s projekt=%s dateien=%s" % (hash_, art, aid, projekt, ", ".join(rel)))
    return hash_, "commit %s als %s auf %s (lokal, nicht gepusht, Projekt: %s)" % (hash_, autor, branch, projekt)


def cmd_init(args):
    lane = lane_pfad(args.lane)
    p = loop_ordner(lane)
    if os.path.isfile(p["plan"]):
        raise wo.FensterFehler("plan.json gibt es schon, nichts ueberschrieben")
    os.makedirs(p["auftrag"], exist_ok=True)
    os.makedirs(p["antwort"], exist_ok=True)
    os.makedirs(p["bilder"], exist_ok=True)
    plan = {
        "lane": lane,
        "modus": args.modus,
        "fenster_anzahl": 1,
        "projekt": (getattr(args, "projekt", None) or register_name(lane) or "").strip(),
        "basis": git_basis_branch(lane) or "",
        "aufgaben": [],
    }
    speichere_plan(p, plan)
    with open(p["log"], "w", encoding="utf-8") as f:
        f.write("# log\n\n")
    with open(p["fragen"], "w", encoding="utf-8") as f:
        f.write("# fragen\n\n(noch keine)\n")
    log_an(p, "init modus=%s lane=%s" % (args.modus, lane))
    schreibe_status(p, plan, {"phase": "bereit"})
    print("loop angelegt in %s" % p["root"])
    print("modus: %s" % args.modus)
    print("aufgaben stehen in plan.json, danach: loop.py schritt --lane \"%s\"" % lane)


def cmd_schritt(args):
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    wartend = warte_aufgabe(plan)
    if wartend:
        raise wo.FensterFehler(
            "aufgabe %s wartet noch auf senden: loop.py senden --lane \"%s\" --ja" % (wartend["id"], lane)
        )
    aufg = naechste_aufgabe(plan)
    if not aufg:
        print("keine offene aufgabe")
        return
    if not aufg.get("id"):
        raise wo.FensterFehler("aufgabe ohne id")
    if not (aufg.get("ziel") or "").strip():
        raise wo.FensterFehler("aufgabe %s hat kein ziel" % aufg["id"])
    fenster = aufg.get("fenster_hwnd") or aufg.get("fenster")
    if not fenster:
        raise wo.FensterFehler("aufgabe %s hat kein fenster (hwnd setzen)" % aufg["id"])
    hwnd = fenster_als_hwnd(fenster, pflicht=not args.trocken)
    aufg["fenster_hwnd"] = hwnd
    aufg["fenster"] = str(hwnd)
    fenster = str(hwnd)
    merke_fenster_titel(aufg, hwnd, pflicht=not args.trocken)
    try:
        branch, bhinweis = arbeit_branch_setzen(lane, aufg["id"], plan)
        log_an(p, "schritt branch=%s %s" % (branch, bhinweis))
        plan["basis"] = plan.get("basis") or git_basis_branch(lane, plan)
        if not plan.get("projekt"):
            plan["projekt"] = register_name(lane, plan)
    except wo.FensterFehler as e:
        if not args.trocken:
            raise
        log_an(p, "schritt branch trocken nicht gesetzt: %s" % e)
        print("trocken: branch nicht gesetzt: %s" % e)
    auftrag = {
        "id": aufg["id"],
        "art": "auftrag",
        "ziel": aufg.get("ziel") or "",
        "dateien": list(aufg.get("dateien") or []),
        "fertig_wenn": aufg.get("fertig_wenn") or "",
        "verboten": list(aufg.get("verboten") or VERBOTEN_STANDARD),
        "hinweis": "nur in diesem projektordner. lokal committen macht der loop, nicht du. nichts pushen. am ende antwort/%s.json schreiben." % aufg["id"],
    }
    if aufg.get("status") == "korrektur" or int(aufg.get("versuche") or 0) > 0:
        auftrag = korrektur_auftrag(lane, p, aufg, auftrag)
    auftrag_pfad = os.path.join(p["auftrag"], "%s.json" % aufg["id"])
    schreib_json(auftrag_pfad, auftrag)
    aufg["status"] = "laeuft"
    aufg["phase"] = "warte_auf_senden"
    aufg["versuche"] = int(aufg.get("versuche") or 0)
    speichere_plan(p, plan)
    schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": "warte_auf_senden"})
    log_an(p, "schritt aufgabe=%s fenster=%s trocken=%s" % (aufg["id"], fenster, bool(args.trocken)))
    text = auftrag_text(lane, p, aufg)
    if args.trocken:
        print("trocken: auftrag liegt in %s" % auftrag_pfad)
        print("wuerde vorbereiten in fenster %s, nicht senden" % fenster)
        print("danach: loop.py senden --lane \"%s\" --ja" % lane)
        return aufg
    rufe_vorbereiten(fenster, text, aufg.get("fenster_titel") or None)
    print("auftrag %s steht im fenster %s – NICHT gesendet" % (aufg["id"], fenster))
    if plan.get("modus") == "autonom":
        print("modus ist autonom, in diesem schritt wird trotzdem erst nach --ja gesendet")
    print("warte auf freigabe: loop.py senden --lane \"%s\" --ja" % lane)
    return aufg


def lies_antwort(p, aufg):
    antwort_pfad = os.path.join(p["antwort"], "%s.json" % aufg["id"])
    if not os.path.isfile(antwort_pfad):
        return None, antwort_pfad
    try:
        with open(antwort_pfad, encoding="utf-8") as f:
            antwort = json.load(f)
        if not isinstance(antwort, dict):
            return None, antwort_pfad
        return antwort, antwort_pfad
    except (OSError, json.JSONDecodeError) as e:
        log_an(p, "antwort unlesbar: %s" % e)
        return None, antwort_pfad


def nach_senden(lane, plan, p, aufg, fenster, trocken=False, max_min=60):
    #nach dem senden: warten, antwort lesen, bild, log, status, ggf. commit
    antwort_pfad = os.path.join(p["antwort"], "%s.json" % aufg["id"])
    bild_pfad = os.path.join(p["bilder"], "%s.png" % aufg["id"])
    antwort = None
    if not trocken:
        haenger = warte_mit_haenger(lane, plan, p, aufg, fenster, max_min=max_min, trocken=False)
        if haenger == "haenger":
            schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": "frage", "letzter_fehler": "haenger"})
            print("aufgabe %s: frage (haenger)" % aufg["id"])
            print("log: %s" % p["log"])
            return aufg
        antwort, antwort_pfad = lies_antwort(p, aufg)
        if antwort is None:
            log_an(p, "keine antwort-json, fallback lesen")
            try:
                from io import StringIO
                buf = StringIO()
                alt = sys.stdout
                sys.stdout = buf
                try:
                    tipper.cmd_lesen(ns(fenster=str(fenster), zeichen=6000))
                finally:
                    sys.stdout = alt
                roh = buf.getvalue()
            except Exception as e:
                roh = "lesen fehlgeschlagen: %s" % e
            antwort = {
                "id": aufg["id"],
                "status": "korrektur_noetig",
                "geaenderte_dateien": [],
                "tests": "unbekannt",
                "offene_fragen": [],
                "kurz": "keine antwort-json, text aus dem fenster steht im log",
            }
            schreib_json(antwort_pfad, antwort)
            log_an(p, "lesen-fallback:\n%s\n" % roh[-4000:])
        try:
            rufe_bild(fenster, bild_pfad, aufg.get("fenster_titel") or None)
            log_an(p, "bild %s" % bild_pfad)
        except wo.FensterFehler as e:
            log_an(p, "bild fehlgeschlagen: %s" % e)
            print("bild fehlgeschlagen: %s" % e)
    else:
        antwort, antwort_pfad = lies_antwort(p, aufg)
        if antwort is None:
            print("trocken: keine antwort-json, wuerde im fenster lesen")
            antwort = {"id": aufg["id"], "status": "", "offene_fragen": [], "kurz": "trocken, keine antwort"}
        else:
            print("trocken: antwort gelesen aus %s, status=%s" % (antwort_pfad, antwort.get("status") or ""))

    wert, drinnen, draussen = lane_pruefung(lane)
    verstoss = wert == "verstoss"
    if wert == "kein_git":
        log_an(p, "lane-pruefung: kein git in der lane")
        print("lane-pruefung: kein git, diff nicht pruefbar")
    elif verstoss:
        log_an(p, "lane-verstoss: %s" % ", ".join(str(x) for x in draussen))
        print("lane-verstoss, nicht als fertig markiert. siehe fragen.md")
        with open(p["fragen"], "a", encoding="utf-8") as f:
            f.write(
                "\n## %s aufgabe %s\n\naenderungen ausserhalb der lane:\n%s\n\n"
                "optionen: [a] zuruecknehmen  [b] lane erweitern  [c] anders, ich schreibs selbst\n"
                % (jetzt(), aufg["id"], "\n".join(str(x) for x in draussen))
            )
    else:
        rel = [os.path.relpath(d, lane) for d in drinnen]
        log_an(p, "lane-pruefung ok, geaendert: %s" % (", ".join(rel) if rel else "nichts"))
        print("lane-pruefung ok")

    status = status_nach_antwort((antwort or {}).get("status"), aufg.get("versuche") or 0, verstoss)
    aufg["status"] = status
    aufg["phase"] = "lane_verstoss" if verstoss else "geprueft"
    if status == "frage" and not verstoss:
        fragen = list((antwort or {}).get("offene_fragen") or [])
        with open(p["fragen"], "a", encoding="utf-8") as f:
            f.write("\n## %s aufgabe %s\n\n" % (jetzt(), aufg["id"]))
            if int(aufg.get("versuche") or 0) >= MAX_KORREKTUREN:
                f.write("nach %d korrekturen nicht fertig.\n" % MAX_KORREKTUREN)
            for i, frage in enumerate(fragen, 1):
                f.write("%d. %s\n" % (i, frage))
            f.write("\noptionen: [a] nochmal  [b] aufgabe schliessen  [c] anders, ich schreibs selbst\n")
    elif status == "frage" and (antwort or {}).get("offene_fragen"):
        #verstoss-fragen stehen schon, offene fragen dazu
        pass
    speichere_plan(p, plan)
    schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": aufg.get("phase") or aufg.get("status") or ""})
    log_an(p, "aufgabe=%s antwort-status=%s plan-status=%s versuche=%s" % (
        aufg["id"], (antwort or {}).get("status") or "", aufg["status"], aufg.get("versuche") or 0
    ))
    print("aufgabe %s: %s" % (aufg["id"], aufg["status"]))

    if status == "fertig" and not verstoss:
        art = "fenster" if (aufg.get("fenster_hwnd") or aufg.get("fenster")) else "cli"
        if trocken:
            print("wuerde lokal committen als agent-%s auf %s, Projekt: %s" % (
                art, arbeit_branch_name(aufg["id"]), projekt_im_trailer(lane, plan)
            ))
            #im trocken-lauf den commit wirklich machen, wenn --trocken-commit nicht noetig:
            #nur ankuendigen, nichts committen, damit --trocken unschaedlich bleibt
        else:
            hash_, text = agent_commit(lane, plan, p, aufg["id"], art, aufg.get("ziel") or "")
            print(text)
            if hash_:
                aufg["commit"] = hash_
                speichere_plan(p, plan)
                schreibe_status(p, plan, {"aktuell": None, "phase": "fertig"})
    schreibe_status(p, plan, {"aktuell": aufg["id"] if aufg.get("status") != "fertig" else None, "phase": aufg.get("status") or ""})
    print("log: %s" % p["log"])
    return aufg


def cmd_senden(args):
    if not args.ja:
        raise wo.FensterFehler("regel: senden nur mit --ja nach ok")
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    aufg = warte_aufgabe(plan)
    if not aufg:
        raise wo.FensterFehler("keine aufgabe wartet auf senden, erst loop.py schritt")
    fenster = str(aufg.get("fenster_hwnd") or aufg.get("fenster") or "")
    if fenster:
        fenster = str(fenster_als_hwnd(fenster, pflicht=not args.trocken))
        aufg["fenster_hwnd"] = int(fenster) if str(fenster).isdigit() else aufg.get("fenster_hwnd")
        aufg["fenster"] = fenster
        merke_fenster_titel(aufg, fenster, pflicht=not args.trocken)
        if not args.trocken:
            pruefe_aufgabe_fenster(aufg, pflicht=True)
    if args.trocken:
        aufg["phase"] = "gesendet"
        aufg["versuche"] = int(aufg.get("versuche") or 0) + 1
        speichere_plan(p, plan)
        log_an(p, "senden trocken aufgabe=%s (nicht wirklich gesendet)" % aufg["id"])
        print("trocken: wuerde senden und warten in fenster %s" % fenster)
        nach_senden(lane, plan, p, aufg, fenster, trocken=True, max_min=args.max_min)
        return
    pruefe_aufgabe_fenster(aufg, pflicht=True)
    rufe_senden(fenster, aufg.get("fenster_titel") or None)
    aufg["phase"] = "gesendet"
    aufg["versuche"] = int(aufg.get("versuche") or 0) + 1
    speichere_plan(p, plan)
    log_an(p, "gesendet aufgabe=%s fenster=%s versuch=%s" % (aufg["id"], fenster, aufg["versuche"]))
    nach_senden(lane, plan, p, aufg, fenster, trocken=False, max_min=args.max_min)


def cmd_aufgabe(args):
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    aid = (args.id or "").strip()
    if not aid:
        raise wo.FensterFehler("id fehlt")
    for alt in plan.get("aufgaben") or []:
        if alt.get("id") == aid:
            raise wo.FensterFehler("aufgabe %s gibt es schon" % aid)
    hwnd = None
    if args.fenster:
        #hwnd nur merken, fenster muss jetzt nicht offen sein
        hwnd = fenster_als_hwnd(args.fenster, pflicht=not str(args.fenster).strip().isdigit())
    aufg = {
        "id": aid,
        "ziel": (args.ziel or "").strip(),
        "dateien": [x.strip() for x in (args.dateien or "").split(",") if x.strip()],
        "fertig_wenn": args.fertig_wenn or "",
        "verboten": list(VERBOTEN_STANDARD),
        "fenster_hwnd": hwnd,
        "fenster": str(hwnd) if hwnd else "",
        "status": "offen",
        "versuche": 0,
    }
    if not aufg["ziel"]:
        raise wo.FensterFehler("ziel fehlt")
    if hwnd:
        merke_fenster_titel(aufg, hwnd, pflicht=False)
    plan.setdefault("aufgaben", []).append(aufg)
    speichere_plan(p, plan)
    schreibe_status(p, plan, {"phase": "offen"})
    log_an(p, "aufgabe angelegt id=%s hwnd=%s" % (aid, hwnd))
    print("aufgabe %s angelegt%s" % (aid, " hwnd=" + str(hwnd) if hwnd else " (noch ohne fenster)"))


def cmd_commit(args):
    #lokaler commit als agent-cli / agent-fenster, kein push. --auftrag bleibt Pflicht.
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    art = args.art
    aid = (args.auftrag or "").strip()
    if not aid:
        raise wo.FensterFehler("auftrag fehlt, --auftrag ist Pflicht")
    hash_, text = agent_commit(lane, plan, p, aid, art, getattr(args, "ziel", "") or "")
    print(text)
    if hash_:
        print("commit: %s" % hash_)


def cmd_modus(args):
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    alt = plan.get("modus") or ""
    plan["modus"] = args.modus
    speichere_plan(p, plan)
    schreibe_status(p, plan, {"phase": plan.get("phase") or "", "modus": args.modus})
    log_an(p, "modus %s -> %s" % (alt, args.modus))
    print("modus: %s" % args.modus)


def cmd_status(args):
    lane = getattr(args, "lane", None)
    register = getattr(args, "register", None)
    daten = status_uebersicht(lane=lane, register=register)
    print(json.dumps(daten, ensure_ascii=False, indent=2))
    return daten


def _sende_eine(lane, plan, p, aufg, trocken, max_min):
    fenster = str(aufg.get("fenster_hwnd") or aufg.get("fenster") or "")
    if not fenster:
        raise wo.FensterFehler("aufgabe %s hat kein fenster (hwnd setzen)" % aufg["id"])
    if not trocken:
        pruefe_aufgabe_fenster(aufg, pflicht=True)
        fenster = str(aufg.get("fenster_hwnd") or fenster)
        rufe_senden(fenster, aufg.get("fenster_titel") or None)
    aufg["phase"] = "gesendet"
    aufg["versuche"] = int(aufg.get("versuche") or 0) + 1
    speichere_plan(p, plan)
    log_an(p, "gesendet aufgabe=%s fenster=%s versuch=%s trocken=%s" % (
        aufg["id"], fenster, aufg["versuche"], bool(trocken)
    ))
    if trocken:
        print("trocken: wuerde senden und warten in fenster %s" % fenster)
    nach_senden(lane, plan, p, aufg, fenster, trocken=trocken, max_min=max_min)
    return aufg


def cmd_lauf(args):
    #alle offenen aufgaben nacheinander. schrittweise stoppt vor jedem senden.
    #autonom nur wenn plan.json modus=autonom, und nur mit --ja (oder --trocken).
    lane = lane_pfad(args.lane)
    plan, p = lade_plan(lane)
    trocken = bool(getattr(args, "trocken", False))
    max_min = int(getattr(args, "max_min", 60) or 60)
    modus = (plan.get("modus") or "schrittweise").strip()
    if modus not in ("schrittweise", "autonom"):
        raise wo.FensterFehler("unbekannter modus in plan.json: %s" % modus)
    if not trocken:
        sperre_lauf(p)
    schreibe_status(p, plan, {"phase": "lauf", "letzter_fehler": ""})
    log_an(p, "lauf start modus=%s trocken=%s" % (modus, trocken))
    try:
        if modus != "autonom":
            #ein schritt, dann vor dem senden stehen bleiben
            wartend = warte_aufgabe(plan)
            if wartend:
                schreibe_status(p, plan, {"aktuell": wartend["id"], "phase": "warte_auf_senden"})
                print("schrittweise: aufgabe %s wartet auf senden: loop.py senden --lane \"%s\" --ja" % (wartend["id"], lane))
                return
            aufg = naechste_aufgabe(plan)
            if not aufg:
                schreibe_status(p, plan, {"phase": "fertig" if (plan.get("aufgaben") or []) else "bereit"})
                print("keine offene aufgabe")
                return
            cmd_schritt(ns(lane=lane, trocken=trocken))
            print("schrittweise: vor dem senden gestoppt")
            return

        if not getattr(args, "ja", False) and not trocken:
            raise wo.FensterFehler(
                "autonom senden nur mit --ja (einmalige start-freigabe) oder --trocken"
            )

        #aufgaben nacheinander, ein fenster nach dem anderen, vor typ/send hwnd+titel pruefen
        gesehen_hwnd_frage = set()
        while True:
            plan, p = lade_plan(lane)
            wartend = warte_aufgabe(plan)
            aufg = wartend or naechste_aufgabe(plan)
            if not aufg:
                offen = [a for a in (plan.get("aufgaben") or []) if a.get("status") in ("offen", "korrektur", "laeuft")]
                if offen:
                    #sollte nicht vorkommen
                    break
                schreibe_status(p, plan, {"aktuell": None, "phase": "fertig"})
                log_an(p, "lauf fertig, keine offene aufgabe mehr")
                print("lauf fertig")
                break
            hwnd = aufg.get("fenster_hwnd") or aufg.get("fenster")
            if hwnd and str(hwnd) in gesehen_hwnd_frage:
                log_an(p, "ueberspringe aufgabe %s, fenster %s zuvor abgebrochen" % (aufg["id"], hwnd))
                aufg["status"] = "frage"
                aufg["phase"] = "fenster_unpassend"
                speichere_plan(p, plan)
                continue
            schreibe_status(p, plan, {"aktuell": aufg["id"], "phase": "laeuft"})
            log_an(p, "lauf aufgabe=%s" % aufg["id"])
            print("lauf: aufgabe %s" % aufg["id"])
            try:
                if not wartend:
                    cmd_schritt(ns(lane=lane, trocken=trocken))
                    plan, p = lade_plan(lane)
                    aufg = next((a for a in plan.get("aufgaben") or [] if a.get("id") == aufg["id"]), aufg)
                _sende_eine(lane, plan, p, aufg, trocken=trocken, max_min=max_min)
            except wo.FensterFehler as e:
                msg = str(e)
                log_an(p, "lauf abbruch aufgabe=%s: %s" % (aufg["id"], msg))
                print("fehler bei aufgabe %s: %s" % (aufg["id"], msg))
                plan, p = lade_plan(lane)
                for a in plan.get("aufgaben") or []:
                    if a.get("id") == aufg["id"]:
                        a["status"] = "frage"
                        a["phase"] = "abbruch"
                with open(p["fragen"], "a", encoding="utf-8") as f:
                    f.write(
                        "\n## %s aufgabe %s\n\n%s\n\n"
                        "optionen: [a] fenster neu zuordnen  [b] aufgabe schliessen  [c] anders, ich schreibs selbst\n"
                        % (jetzt(), aufg["id"], msg)
                    )
                speichere_plan(p, plan)
                schreibe_status(p, plan, {
                    "aktuell": aufg["id"], "phase": "frage", "letzter_fehler": msg[:240],
                })
                if "fenster stimmt nicht" in msg or "kein cursor-fenster" in msg or "ist weg" in msg or "nicht sichtbar" in msg:
                    if hwnd:
                        gesehen_hwnd_frage.add(str(hwnd))
                    continue
                #andere fehler: loop beenden, rest bleibt offen
                raise
        plan, p = lade_plan(lane)
        schreibe_status(p, plan, {"aktuell": None, "phase": "fertig" if not naechste_aufgabe(plan) and not warte_aufgabe(plan) else "pause"})
    except wo.FensterFehler as e:
        plan, p = lade_plan(lane)
        schreibe_status(p, plan, {"phase": "fehler", "letzter_fehler": str(e)[:240]})
        log_an(p, "lauf fehler: %s" % e)
        raise
    finally:
        if not trocken:
            entsperre_lauf(p)



def main():
    p = argparse.ArgumentParser(prog="loop")
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("init")
    q.add_argument("--lane", required=True)
    q.add_argument("--modus", required=True, choices=["schrittweise", "autonom"])
    q.add_argument("--projekt", help="id aus dem register, fuer den git-trailer Projekt:")
    q = s.add_parser("schritt")
    q.add_argument("--lane", required=True)
    q.add_argument("--trocken", action="store_true", help="nur dateien schreiben, nichts ins fenster tippen")
    q = s.add_parser("senden")
    q.add_argument("--lane", required=True)
    q.add_argument("--ja", action="store_true")
    q.add_argument("--trocken", action="store_true", help="nicht wirklich senden, nur pruefen")
    q.add_argument("--max-min", dest="max_min", type=int, default=60)
    q = s.add_parser("aufgabe")
    q.add_argument("--lane", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--ziel", required=True)
    q.add_argument("--fenster", help="hwnd des cursor-fensters")
    q.add_argument("--dateien", default="")
    q.add_argument("--fertig-wenn", dest="fertig_wenn", default="")
    q = s.add_parser("commit")
    q.add_argument("--lane", required=True)
    q.add_argument("--auftrag", required=True)
    q.add_argument("--art", required=True, choices=["cli", "fenster"])
    q.add_argument("--ziel", default="")
    q = s.add_parser("lauf")
    q.add_argument("--lane", required=True)
    q.add_argument("--ja", action="store_true", help="einmalige start-freigabe fuer autonomes senden")
    q.add_argument("--trocken", action="store_true", help="kein fenster, nichts senden, nichts committen")
    q.add_argument("--max-min", dest="max_min", type=int, default=60)
    q = s.add_parser("status")
    q.add_argument("--alle", action="store_true", help="alle register-projekte (standard ohne --lane)")
    q.add_argument("--lane", help="nur dieses projekt")
    q.add_argument("--register", help="pfad zu register.json oder zur hub-wurzel")
    q = s.add_parser("modus")
    q.add_argument("--lane", required=True)
    q.add_argument("--modus", required=True, choices=["schrittweise", "autonom"])
    args = p.parse_args()
    if getattr(args, "max_min", None) is not None and (args.max_min < 1 or args.max_min > 240):
        print("fehler: max-min muss zwischen 1 und 240 liegen")
        sys.exit(2)
    try:
        if args.cmd == "init":
            cmd_init(args)
        elif args.cmd == "schritt":
            cmd_schritt(args)
        elif args.cmd == "senden":
            cmd_senden(args)
        elif args.cmd == "aufgabe":
            cmd_aufgabe(args)
        elif args.cmd == "commit":
            cmd_commit(args)
        elif args.cmd == "lauf":
            cmd_lauf(args)
        elif args.cmd == "status":
            cmd_status(args)
        elif args.cmd == "modus":
            cmd_modus(args)
    except wo.FensterFehler as e:
        print("fehler: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()
