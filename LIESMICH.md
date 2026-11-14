# grok-cursor-bruecke

Lokales Werkzeug: Cursor-Fenster sehen, Text ins Chatfeld legen, Screenshot machen, erst nach OK abschicken. Dazu ein Loop, der Aufgaben aus `.loop/plan.json` abarbeitet. Läuft auf dem eigenen Rechner. Dieser Ordner startet keinen Server und geht nicht ins Netz.

Regel: **abschicken nur nach OK.** `senden` und autonomes `lauf` gehen nur mit `--ja`.

    .venv\Scripts\python tipper.py fenster
    .venv\Scripts\python tipper.py vorbereiten --fenster 123456 --text "..."
    .venv\Scripts\python tipper.py senden --fenster 123456 --ja
    .venv\Scripts\python tipper.py feld --fenster 123456
    .venv\Scripts\python tipper.py lesen --fenster 123456
    .venv\Scripts\python tipper.py leeren --fenster 123456
    .venv\Scripts\python tipper.py stopp --fenster 123456
    .venv\Scripts\python tipper.py warten --fenster 123456 --max-min 60
    .venv\Scripts\python tipper.py bild --fenster 123456
    .venv\Scripts\python tipper.py oeffnen --ordner C:\pfad\zum\projekt
    .venv\Scripts\python tipper.py status

hwnd merken, nicht die Listen-Nummer. Optional `--titel`, dann bricht tipper ab, wenn das Fenster nicht mehr passt.

`bild` speichert ein PNG nur von diesem Cursor-Fenster. Standardordner: `bilder\` (gitignoriert).

Protokoll: `protokoll.log` (nur Metadaten, kein Textinhalt, gitignoriert).

Installieren: `python -m venv .venv` und `.venv\Scripts\python -m pip install -r requirements.txt`

## loop

    .venv\Scripts\python loop.py init --lane C:\projekt --modus schrittweise
    .venv\Scripts\python loop.py aufgabe --lane C:\projekt --id t1 --ziel "..." --fenster 123456
    .venv\Scripts\python loop.py schritt --lane C:\projekt
    .venv\Scripts\python loop.py senden --lane C:\projekt --ja
    .venv\Scripts\python loop.py lauf --lane C:\projekt --ja
    .venv\Scripts\python loop.py status --alle
    .venv\Scripts\python loop.py modus --lane C:\projekt --modus autonom
    .venv\Scripts\python loop.py commit --lane C:\projekt --auftrag t1 --art fenster

In `schrittweise` stoppt `lauf` / `schritt` nach dem Vorbereiten. In `autonom` (nur wenn `plan.json` das sagt) arbeitet `lauf --ja` alle offenen Aufgaben nacheinander ab: senden, warten, Antwort lesen, Screenshot, log, bei Fertig lokaler Commit. Nach 3 Korrekturen oder einem Hänger (warten-Timeout, dann Stopp und nochmal senden) steht die Frage in `fragen.md`.

`.loop/status.json` ist der kurze Stand für Grok Bot (aktuell, fertig, offen, fragen, letzter_fehler, zeit). `status --alle` fasst alle Projekte aus dem Register zusammen. Den Hub-Ordner kannst du lokal in `ort.json` oder über `GROK_ZENTRALE` angeben, diese Datei gehört nicht ins Repo.

`--trocken` schreibt nur Dateien, tippt und committet nichts.

Plan: [PLAN.md](PLAN.md)

MIT-Lizenz, siehe LICENSE

English: [README.md](README.md)
