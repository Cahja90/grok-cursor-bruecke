#cursor-tipper: cursor-fenster sehen, text ins chatfeld legen, erst nach ok abschicken
#regel: "senden" nur mit --ja, und --ja nur wenn der chef im chat ja gesagt hat
import argparse
import ctypes
import datetime
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comtypes
import window_order as wo

ROOT = os.path.dirname(os.path.abspath(__file__))
PROTOKOLL = os.path.join(ROOT, "protokoll.log")
BILDER = os.path.join(ROOT, "bilder")
MAX_TEXT_DATEI = 64 * 1024
PW_RENDERFULLCONTENT = 2
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class BITMAPINFO(ctypes.Structure):
    _fields_ = (
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    )


def log(text):
    zeile = "%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text)
    with open(PROTOKOLL, "a", encoding="utf-8") as f:
        f.write(zeile)


def exe_von(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return "", pid.value
    try:
        puffer = ctypes.create_unicode_buffer(520)
        laenge = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, puffer, ctypes.byref(laenge)):
            return os.path.basename(puffer.value).lower(), pid.value
        return "", pid.value
    finally:
        kernel32.CloseHandle(h)


def cursor_fenster():
    liste = []

    def je(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        puffer = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, puffer, n + 1)
        exe, pid = exe_von(hwnd)
        if exe == "cursor.exe":
            liste.append({"hwnd": int(hwnd), "titel": puffer.value, "pid": pid})
        return True

    user32.EnumWindows(ENUM(je), 0)
    return liste


def waehle(wahl):
    alle = cursor_fenster()
    if not alle:
        raise wo.FensterFehler("kein cursor-fenster offen")
    if wahl.isdigit():
        for f in alle:
            if f["hwnd"] == int(wahl):
                return f
        #listen-nummer nur als hilfe, nicht zum speichern
        if int(wahl) <= len(alle) and int(wahl) >= 1 and len(wahl) < 4:
            return alle[int(wahl) - 1]
        raise wo.FensterFehler("hwnd %s nicht gefunden (listen-nummer nicht verwenden)" % wahl)
    treffer = [f for f in alle if wahl.casefold() in f["titel"].casefold()]
    if len(treffer) != 1:
        raise wo.FensterFehler("titel '%s' passt auf %d fenster, genauer sagen" % (wahl, len(treffer)))
    return treffer[0]


def titel_kern(titel):
    t = (titel or "").replace("\u2014", "-").replace(" — ", " - ").strip()
    for end in (" - Cursor", " - cursor"):
        if t.endswith(end):
            t = t[: -len(end)].strip()
    teile = [x.strip() for x in t.split(" - ") if x.strip()]
    return teile[-1] if teile else t


def titel_passt(aktuell, erwartet):
    if not (erwartet or "").strip():
        return True
    a = (aktuell or "").strip()
    e = erwartet.strip()
    if not a:
        return False
    if a == e:
        return True
    if e.casefold() in a.casefold() or a.casefold() in e.casefold():
        return True
    ka, ke = titel_kern(a), titel_kern(e)
    if ka and ke and ka.casefold() == ke.casefold():
        return True
    if ke and ke.casefold() in a.casefold():
        return True
    return False


def fenster_pruefen(hwnd, erwarteter_titel=None):
    #vor jedem tippen/senden: hwnd muss noch das erwartete cursor-fenster sein
    try:
        n = int(hwnd)
    except (TypeError, ValueError):
        raise wo.FensterFehler("hwnd ungueltig: %s" % hwnd)
    if not user32.IsWindow(n):
        raise wo.FensterFehler("fenster hwnd %s ist weg" % n)
    if not user32.IsWindowVisible(n):
        raise wo.FensterFehler("fenster hwnd %s ist nicht sichtbar" % n)
    exe, _pid = exe_von(n)
    if exe != "cursor.exe":
        raise wo.FensterFehler("hwnd %s ist kein cursor-fenster mehr (prozess: %s)" % (n, exe or "unbekannt"))
    titel = ""
    laenge = user32.GetWindowTextLengthW(n)
    if laenge > 0:
        puffer = ctypes.create_unicode_buffer(laenge + 1)
        user32.GetWindowTextW(n, puffer, laenge + 1)
        titel = puffer.value
    if not titel_passt(titel, erwarteter_titel):
        raise wo.FensterFehler(
            "fenster stimmt nicht: hwnd %s titel '%s', erwartet '%s'" % (n, titel, erwarteter_titel)
        )
    return {"hwnd": n, "titel": titel, "pid": _pid}


def waehle_sicher(wahl, erwarteter_titel=None):
    f = waehle(str(wahl))
    geprueft = fenster_pruefen(f["hwnd"], erwarteter_titel)
    f = dict(f)
    f["titel"] = geprueft.get("titel") or f.get("titel") or ""
    return f


def liegt_unter(kind, eltern):
    kind = os.path.normcase(os.path.abspath(kind))
    eltern = os.path.normcase(os.path.abspath(eltern))
    return kind == eltern or kind.startswith(eltern + os.sep)


def text_holen(args):
    if args.datei:
        pfad = os.path.abspath(args.datei)
        if not os.path.isfile(pfad):
            raise wo.FensterFehler("datei nicht gefunden")
        if os.path.getsize(pfad) > MAX_TEXT_DATEI:
            raise wo.FensterFehler("datei zu gross")
        with open(pfad, encoding="utf-8") as f:
            return f.read()
    return args.text or ""


def bild_ziel(datei, fenster_nr):
    if datei:
        ziel = os.path.abspath(datei)
        if not ziel.lower().endswith(".png"):
            ziel = ziel + ".png"
    else:
        os.makedirs(BILDER, exist_ok=True)
        name = "fenster-%s-%s.png" % (fenster_nr, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        ziel = os.path.join(BILDER, name)
    for sperre in (os.path.join(ROOT, ".git"), os.path.join(ROOT, ".venv")):
        if liegt_unter(ziel, sperre):
            raise wo.FensterFehler("pfad nicht erlaubt")
    if liegt_unter(os.path.dirname(ziel) or ziel, ROOT):
        name = os.path.basename(ziel).lower()
        if name in ("tipper.py", "window_order.py", "liesmich.md", "license", "requirements.txt", ".gitignore"):
            raise wo.FensterFehler("pfad nicht erlaubt")
    parent = os.path.dirname(ziel)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return ziel


def dpi_scharf():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def bitmap_zu_bild(hdc, hbmp, breite, hoehe):
    from PIL import Image
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = breite
    info.bmiHeader.biHeight = -hoehe
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(breite * hoehe * 4)
    geholt = gdi32.GetDIBits(hdc, hbmp, 0, hoehe, buf, ctypes.byref(info), DIB_RGB_COLORS)
    if geholt != hoehe:
        return None
    return Image.frombuffer("RGB", (breite, hoehe), bytes(buf), "raw", "BGRX", 0, 1)


def bild_ist_leer(img):
    if img is None:
        return True
    dunkel, hell = img.convert("L").getextrema()
    return hell <= 8


def fenster_drucken(hwnd, breite, hoehe, flags):
    handle = wintypes.HWND(int(hwnd))
    hdc_win = user32.GetWindowDC(handle)
    if not hdc_win:
        return None
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, breite, hoehe)
    alt = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        ok = bool(user32.PrintWindow(handle, hdc_mem, flags))
        if not ok:
            return None
        return bitmap_zu_bild(hdc_mem, hbmp, breite, hoehe)
    finally:
        gdi32.SelectObject(hdc_mem, alt)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(handle, hdc_win)


def fenster_abfotografieren(hwnd, breite, hoehe, left, top):
    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        return None
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, breite, hoehe)
    alt = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        ok = bool(gdi32.BitBlt(hdc_mem, 0, 0, breite, hoehe, hdc_screen, left, top, SRCCOPY))
        if not ok:
            return None
        return bitmap_zu_bild(hdc_mem, hbmp, breite, hoehe)
    finally:
        gdi32.SelectObject(hdc_mem, alt)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)


def feld_im(handle):
    def mach():
        uia = wo.neues_uia()
        root = wo.uia_root(uia, handle)
        feld = wo.finde_feld(uia, root)
        if not feld:
            time.sleep(0.4)
            feld = wo.finde_feld(uia, root)
        if not feld:
            raise wo.FensterFehler("kein eingabefeld")
        return uia, root, feld
    return wo.com_einmal_noch(mach)


def cmd_fenster(_args):
    print("# hwnd merken und verwenden, die listen-nummer aendert sich")
    for i, f in enumerate(cursor_fenster(), 1):
        print("%d  hwnd=%d  %s" % (i, f["hwnd"], f["titel"]))


def cmd_vorbereiten(args):
    #nur ins feld legen, NICHT abschicken
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    text = text_holen(args).replace("\r\n", "\n").strip()
    if not text or len(text) > 8000:
        raise wo.FensterFehler("text leer oder zu lang")
    comtypes.CoInitialize()
    try:
        uia, root, feld = feld_im(f["hwnd"])
        if not wo.fokus_stimmt(uia, feld, f["hwnd"]):
            raise wo.FensterFehler("fokus nicht im feld")
        if args.modus:
            wo.setze_modus(uia, root, feld, args.modus)
            wo.fokus_stimmt(uia, feld, f["hwnd"])
        wo.schreibe_ins_feld(feld, text)
        log("vorbereitet fenster=%s titel=%s zeichen=%d" % (f["hwnd"], f["titel"], len(text)))
        print("steht im feld von '%s' – NICHT gesendet" % f["titel"])
    finally:
        comtypes.CoUninitialize()


def chat_text(uia, root):
    #sichtbarer text im fenster, nur lesen
    teile, gesehen = [], set()
    for el in wo.alle_elemente(uia, root):
        try:
            if int(el.CurrentControlType) != int(wo.UIA.UIA_TextControlTypeId):
                continue
            name = (el.CurrentName or "").strip()
        except Exception:
            continue
        if name and name not in gesehen:
            gesehen.add(name)
            teile.append(name)
    return "\n".join(teile)


def senden_war_erfolgreich(inhalt_vorher, inhalt_jetzt, stop_sichtbar, chat_vorher, chat_jetzt):
    #feld leer, stop-knopf da, oder neue nutzerzeile im chat
    if not (inhalt_jetzt or "").strip():
        return True
    if stop_sichtbar:
        return True
    vorher = chat_vorher or ""
    jetzt = chat_jetzt or ""
    if jetzt and jetzt != vorher and len(jetzt) > len(vorher):
        return True
    stueck = (inhalt_vorher or "").strip()
    if stueck and stueck in jetzt and stueck not in vorher:
        return True
    return False


def cmd_senden(args):
    if not args.ja:
        raise wo.FensterFehler("regel: senden nur mit --ja nach ok vom chef")
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    comtypes.CoInitialize()
    try:
        uia, root, feld = feld_im(f["hwnd"])
        inhalt = (wo.lese_feld(feld) or "").strip()
        if not inhalt:
            raise wo.FensterFehler("feld ist leer, erst vorbereiten")
        if not wo.fokus_stimmt(uia, feld, f["hwnd"]):
            raise wo.FensterFehler("fokus nicht im feld")
        chat_vorher = chat_text(uia, root)
        wo.enter_senden()
        ende = time.time() + 5
        ok = False
        while time.time() < ende:
            time.sleep(0.3)
            try:
                uia, root, feld = feld_im(f["hwnd"])
                inhalt_jetzt = (wo.lese_feld(feld) or "").strip()
                stop = stop_knopf_da(uia, root)
                chat_jetzt = chat_text(uia, root)
            except (wo.FensterFehler, comtypes.COMError):
                continue
            if senden_war_erfolgreich(inhalt, inhalt_jetzt, stop, chat_vorher, chat_jetzt):
                ok = True
                break
        if not ok:
            raise wo.FensterFehler("nicht abgeschickt")
        log("gesendet fenster=%s titel=%s zeichen=%d" % (f["hwnd"], f["titel"], len(inhalt)))
        print("abgeschickt an '%s'" % f["titel"])
    finally:
        comtypes.CoUninitialize()


def cmd_feld(args):
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    comtypes.CoInitialize()
    try:
        _uia, _root, feld = feld_im(f["hwnd"])
        print(wo.lese_feld(feld) or "")
    finally:
        comtypes.CoUninitialize()


def cmd_leeren(args):
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    comtypes.CoInitialize()
    try:
        uia, _root, feld = feld_im(f["hwnd"])
        if not wo.fokus_stimmt(uia, feld, f["hwnd"]):
            raise wo.FensterFehler("fokus nicht im feld")
        wo.leere_feld()
        log("geleert fenster=%s" % f["hwnd"])
        print("feld geleert")
    finally:
        comtypes.CoUninitialize()


def cmd_lesen(args):
    #sichtbaren text im fenster lesen (chat-verlauf), nur lesen
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    comtypes.CoInitialize()
    try:
        def mach():
            uia = wo.neues_uia()
            root = wo.uia_root(uia, f["hwnd"])
            return chat_text(uia, root)
        text = wo.com_einmal_noch(mach)
        print(text[-args.zeichen:])
    finally:
        comtypes.CoUninitialize()


def stop_knopf_da(uia, root):
    for el in wo.alle_elemente(uia, root):
        try:
            if int(el.CurrentControlType) != int(wo.UIA.UIA_ButtonControlTypeId):
                continue
            if (el.CurrentName or "").lower().startswith("stop"):
                return True
        except Exception:
            continue
    return False


def cmd_warten(args):
    #wartet bis cursor im fenster fertig ist (kein stop-knopf mehr), gibt dann das ende aus
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    start = time.time()
    lief = False
    ruhig = 0
    limit = False
    comtypes.CoInitialize()
    try:
        while time.time() - start < args.max_min * 60:
            try:
                def mach():
                    uia = wo.neues_uia()
                    root = wo.uia_root(uia, f["hwnd"])
                    return stop_knopf_da(uia, root)
                da = wo.com_einmal_noch(mach)
            except comtypes.COMError:
                time.sleep(args.takt)
                continue
            if da:
                lief = True
                ruhig = 0
            else:
                ruhig += 1
                #fertig: lief schon und ist jetzt ruhig, oder lief nie und ist dauerhaft ruhig
                if (lief and ruhig >= 2) or (not lief and ruhig >= args.ruhig_runden):
                    break
            time.sleep(args.takt)
        else:
            print("=== zeitlimit erreicht ===")
            limit = True
    finally:
        comtypes.CoUninitialize()
    dauer = int(time.time() - start)
    print("=== fertig nach %d s (lief=%s) ===" % (dauer, lief))
    log("warten fertig fenster=%s lief=%s timeout=%s" % (f["hwnd"], lief, limit))
    args.zeichen = args.zeichen or 6000
    try:
        cmd_lesen(args)
    except wo.FensterFehler as e:
        print("lesen nach warten: %s" % e)
    return {"timeout": limit, "lief": lief, "sekunden": dauer, "hwnd": f["hwnd"]}


def cmd_stopp(args):
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    ok = wo.stoppe_auftrag(f["hwnd"])
    log("stopp fenster=%s ok=%s" % (f["hwnd"], ok))
    print("gestoppt" if ok else "kein stop-knopf gefunden")


def cmd_bild(args):
    #screenshot nur von diesem cursor-fenster, nichts tippen, nichts senden
    dpi_scharf()
    f = waehle_sicher(args.fenster, getattr(args, "titel", None))
    handle = wintypes.HWND(f["hwnd"])
    if not user32.IsWindow(handle):
        raise wo.FensterFehler("fenster weg")
    rect = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        raise wo.FensterFehler("fenster-groesse unbekannt")
    breite = rect.right - rect.left
    hoehe = rect.bottom - rect.top
    if breite < 8 or hoehe < 8:
        #minimiert? einmal nach vorn holen und nochmal messen
        wo.fokus_fenster(f["hwnd"])
        time.sleep(0.2)
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            raise wo.FensterFehler("fenster-groesse unbekannt")
        breite = rect.right - rect.left
        hoehe = rect.bottom - rect.top
    if breite < 8 or hoehe < 8:
        raise wo.FensterFehler("fenster zu klein fuer ein bild")
    img = fenster_drucken(f["hwnd"], breite, hoehe, PW_RENDERFULLCONTENT)
    weg = "printwindow"
    if bild_ist_leer(img):
        img = fenster_drucken(f["hwnd"], breite, hoehe, 0)
        weg = "printwindow-0"
    if bild_ist_leer(img):
        wo.fokus_fenster(f["hwnd"])
        time.sleep(0.2)
        if user32.GetWindowRect(handle, ctypes.byref(rect)):
            breite = max(8, rect.right - rect.left)
            hoehe = max(8, rect.bottom - rect.top)
        img = fenster_abfotografieren(f["hwnd"], breite, hoehe, rect.left, rect.top)
        weg = "bildschirm"
    if bild_ist_leer(img):
        raise wo.FensterFehler("screenshot leer")
    ziel = bild_ziel(args.datei, args.fenster)
    img.save(ziel, "PNG")
    log("bild fenster=%s titel=%s datei=%s weg=%s" % (f["hwnd"], f["titel"], ziel, weg))
    print(ziel)


def zahlen_pruefen(args):
    grenzen = {
        "zeichen": (1, 200000),
        "max_min": (1, 240),
        "takt": (1, 60),
        "ruhig_runden": (1, 60),
    }
    for name, (mini, maxi) in grenzen.items():
        if hasattr(args, name):
            wert = getattr(args, name)
            if wert is None:
                continue
            if wert < mini or wert > maxi:
                raise wo.FensterFehler("%s muss zwischen %d und %d liegen" % (name, mini, maxi))



def cursor_programm():
    kandidaten = []
    which = shutil.which("cursor")
    if which:
        kandidaten.append(which)
        p = os.path.abspath(which)
        # .../resources/app/bin/cursor.cmd -> .../Cursor.exe
        kandidaten.append(os.path.join(os.path.dirname(p), "Cursor.exe"))
        kandidaten.append(os.path.join(p, os.pardir, os.pardir, os.pardir, os.pardir, "Cursor.exe"))
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        kandidaten.append(os.path.join(local, "Programs", "cursor", "Cursor.exe"))
    gesehen = set()
    for k in kandidaten:
        k = os.path.abspath(k)
        if k in gesehen:
            continue
        gesehen.add(k)
        if os.path.isfile(k) and k.lower().endswith(".exe"):
            return k
    if which:
        return os.path.abspath(which)
    raise wo.FensterFehler("cursor nicht gefunden")


def cmd_oeffnen(args):
    pfad = os.path.abspath(args.ordner)
    if not os.path.isdir(pfad):
        raise wo.FensterFehler("ordner nicht gefunden")
    exe = cursor_programm()
    vorher = {f["hwnd"] for f in cursor_fenster()}
    cmd = [exe, "-n", pfad]
    if exe.lower().endswith(".cmd") or exe.lower().endswith(".bat"):
        cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c"] + cmd
    try:
        subprocess.Popen(cmd, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        raise wo.FensterFehler("cursor startet nicht: %s" % e)
    deadline = time.time() + 45
    neu = []
    while time.time() < deadline:
        time.sleep(0.5)
        jetzt = cursor_fenster()
        neu = [f for f in jetzt if f["hwnd"] not in vorher]
        if neu:
            time.sleep(1.2)
            jetzt = cursor_fenster()
            neu = [f for f in jetzt if f["hwnd"] not in vorher]
            break
    if not neu:
        raise wo.FensterFehler("kein neues cursor-fenster erschienen")
    alle = cursor_fenster()
    ids = {f["hwnd"] for f in neu}
    for i, f in enumerate(alle, 1):
        if f["hwnd"] in ids:
            print("geoeffnet %d  hwnd=%d  pid=%s  %s" % (i, f["hwnd"], f.get("pid", ""), f["titel"]))
    if len(neu) > 1:
        print("mehrere neue fenster, bitte selbst zuordnen")


def cmd_status(args):
    #eine json-uebersicht aller register-projekte, fuer grok bot am handy
    import loop as loop_mod
    loop_mod.cmd_status(args)


def main():
    p = argparse.ArgumentParser(prog="tipper")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("fenster")
    q = s.add_parser("oeffnen")
    q.add_argument("--ordner", required=True, help="ordner, der in einem neuen cursor-fenster aufgeht")
    q = s.add_parser("status")
    q.add_argument("--alle", action="store_true", default=True, help="alle projekte aus dem register (standard)")
    q.add_argument("--lane", help="nur dieses projekt")
    q.add_argument("--register", help="pfad zu projekte/register.json oder zur hub-wurzel")
    for name in ("vorbereiten", "senden", "feld", "leeren", "lesen", "stopp", "warten", "bild"):
        q = s.add_parser(name)
        q.add_argument("--fenster", required=True, help="hwnd (den merken, nicht die listen-nummer) oder teil vom titel")
        q.add_argument("--titel", help="erwarteter fenstertitel, bricht ab wenn hwnd und titel nicht mehr passen")
        if name == "vorbereiten":
            q.add_argument("--text")
            q.add_argument("--datei")
            q.add_argument("--modus", choices=["agent", "plan", "ask"])
        if name == "senden":
            q.add_argument("--ja", action="store_true")
        if name in ("lesen", "warten"):
            q.add_argument("--zeichen", type=int, default=3000 if name == "lesen" else 6000)
        if name == "warten":
            q.add_argument("--max-min", dest="max_min", type=int, default=60)
            q.add_argument("--takt", type=int, default=5)
            q.add_argument("--ruhig-runden", dest="ruhig_runden", type=int, default=6)
        if name == "bild":
            q.add_argument("--datei", help="ziel-png, sonst bilder\\fenster-<n>-<zeit>.png")
    args = p.parse_args()
    try:
        zahlen_pruefen(args)
        globals()["cmd_" + args.cmd](args)
    except wo.FensterFehler as e:
        print("fehler: %s" % e)
        sys.exit(2)
    except comtypes.COMError as e:
        print("fehler: uia nicht erreichbar, nochmal versuchen (%s)" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()
