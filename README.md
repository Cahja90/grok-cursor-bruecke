# grok-cursor-bruecke

A small local Windows CLI that connects Grok Bot (director, on your phone) to Cursor windows and the Cursor CLI on your PC (workers).

Grok Bot can list Cursor windows, type a prompt into a chosen window, wait until the agent is done, read the reply, and take a screenshot. A director/worker loop (`loop.py`) can run a plan of tasks in a project folder: prepare, send, wait, log, and make a local git commit. The optional Zentrale app on your PC shows loop status per project and can start a loop or approve a pending push (local only, never silent).

Windows only. The tool drives the Cursor UI with UI Automation (`comtypes`) and takes screenshots with Pillow. Sending a prompt always needs `--ja`. Everything runs locally. This repo does not start a server and does not make network calls.

## Install

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## tipper.py

Run with `.venv\Scripts\python tipper.py <command>`.

| Command | Description |
| --- | --- |
| `fenster` | List open Cursor windows (use the hwnd, not the list number) |
| `vorbereiten` | Type a prompt into a window's chat field (does not send) |
| `senden --ja` | Send the text already in the field. Requires `--ja`. |
| `feld` / `leeren` / `lesen` | Read, clear, or read the visible chat |
| `stopp` | Press the Stop button, if it is shown |
| `warten` | Wait until the agent is done, then print the reply |
| `bild` | Save a PNG screenshot of that window |
| `oeffnen` | Open a folder in a new Cursor window |
| `status` | Print one JSON overview of all registered projects (for Grok Bot) |

Window commands take `--fenster <hwnd>`. Optional `--titel` aborts if that hwnd no longer matches the expected window title.

## loop.py

State lives in the project folder under `.loop/` (gitignored): plan, tasks, answers, `log.md`, `fragen.md`, `status.json`.

```
.venv\Scripts\python loop.py init --lane <project> --modus schrittweise
.venv\Scripts\python loop.py aufgabe --lane <project> --id t1 --ziel "..." --fenster <hwnd>
.venv\Scripts\python loop.py schritt --lane <project>
.venv\Scripts\python loop.py senden --lane <project> --ja
.venv\Scripts\python loop.py lauf --lane <project> --ja
.venv\Scripts\python loop.py status --alle
.venv\Scripts\python loop.py modus --lane <project> --modus autonom
.venv\Scripts\python loop.py commit --lane <project> --auftrag t1 --art fenster
```

- `schrittweise` (the plan modus): `lauf` prepares the next task and stops before send. Send with `senden --ja`.
- `autonom`: only if `plan.json` says `autonom`. `lauf --ja` is the one-time go-ahead; then the loop sends, waits, logs, screenshots, and locally commits each finished task. Hang: wait timeout, Stop, resend, up to 3 tries, then `fragen.md`.
- Tasks run one after another. Before every type or send, the loop checks hwnd and window title and aborts that task on a mismatch.
- Each task gets its own `arbeit/<id>` branch from main. `--auftrag` on `commit` stays required.
- `status --alle` / `tipper.py status` prints JSON (`aktuell`, `fertig`, `offen`, `fragen`, `letzter_fehler`, `zeit`) for Grok Bot. Point it at your hub with a local `ort.json` (`{"wurzel":"..."}`, gitignored) or the `GROK_ZENTRALE` environment variable.

`--trocken` writes files but does not type, send, or commit.

See [PLAN.md](PLAN.md). German: [LIESMICH.md](LIESMICH.md).

## License

MIT, see [LICENSE](LICENSE).
