# Quick Connect: Play/Pause halten im Hauptmenü

## Ziel

Vom Homescreen aus per gehaltenem Play/Pause-Button (ButtonBox) direkt mit den
zuletzt verbundenen Bluetooth-Kopfhörern verbinden und den zuletzt gespielten
Song fortsetzen - ohne den Umweg über Einstellungen → Verbindung → Bluetooth.

## Auslöser & Ablauf

Nur auf `SCREEN_HOME` aktiv (Play/Pause hat dort sonst keine Funktion, also
keine Kollision mit bestehendem Verhalten):

1. **Play/Pause gedrückt halten** → sofort erscheint ein Ring-Overlay über dem
   Homescreen: dünner grauer Kreis-Umriss, darüber der Text "Quick Connect".
   Der Bereich dahinter wird abgedunkelt (gleiches Crop+Blend+Masken-Verfahren
   wie `_frosted_pill`, nur mit Kreismaske statt Rounded-Rect) für Lesbarkeit.
2. **Weiter halten** → ein weißer Bogen wächst von oben (12 Uhr) im
   Uhrzeigersinn und schließt sich nach **2 Sekunden** zum Vollkreis.
3. **Vor Ablauf losgelassen** → Ring verschwindet sofort, keine weitere Aktion
   (wie ein normaler Home-Screen).
4. **Ring komplett gefüllt** → Verbindungsversuch startet automatisch (Loslassen
   des Buttons spielt ab hier keine Rolle mehr):
   - Fehlt entweder ein bekanntes "zuletzt verbundenes" Bluetooth-Gerät oder
     ein zuletzt gespielter Song (`last_played`), bricht sofort ab: Ring bleibt
     kurz (~1,5s) als Vollkreis stehen, Text wechselt zu einer kurzen
     Fehlermeldung ("Kein Gerät" / "Kein Song") in Rot, dann verschwindet der
     Ring wieder.
   - Sonst: Ring bleibt Vollkreis stehen, Text wechselt zu "Verbinde...",
     `bluetoothctl connect <mac>` läuft im Hintergrund (wie bestehender
     `BTWorker`, blockiert nicht die Render-Loop).
     - Erfolg: sofortiger Wechsel zum Now-Playing-Screen mit dem zuletzt
       gespielten Song (identisches Verhalten zum bestehenden "Fortsetzen"-
       Eintrag auf dem Homescreen), Ring verschwindet.
     - Fehler (Timeout/Ablehnung): gleiche Fehleranzeige wie oben, mit der
       tatsächlichen Fehlermeldung von `connectivity.bluetooth_connect()`.

## "Zuletzt verbundenes Gerät"

Existiert aktuell nirgends als Konzept - `bluetooth_known_devices()` liefert
nur *alle* getrauten Geräte plus aktuellen Verbindungsstatus, keine Historie.
Neu: `settings.json` bekommt `connectivity.last_bt_device` (MAC oder `None`),
geschrieben an den beiden Stellen, an denen `main.py` heute schon eine
erfolgreiche Verbindung herstellt: `BTWorker._device_action("connect", mac)`
und `BTWorker._pair(mac)` (pairing verbindet laut `bluetooth_pair()`-Docstring
ohnehin gleich mit). Kein Abgleich gegen `bluetooth_known_devices()` nötig -
schlägt die gespeicherte MAC fehl (Gerät zwischenzeitlich entfernt), läuft das
einfach in den ohnehin vorhandenen Fehlerpfad.

## State (`ui_state.py`)

Neue Felder auf `UIState`: `qc_active` (Overlay sichtbar), `qc_phase`
(`None`/`"hold"`/`"connecting"`/`"error"`), `qc_progress` (0.0-1.0),
`qc_error`. Neue Methoden `quick_connect_press()`, `quick_connect_release()`,
`quick_connect_tick()` (Fortschritt aus verstrichener Zeit berechnen, liefert
`True` genau einmal beim Überschreiten der Schwelle), `quick_connect_start()`
(prüft Vorbedingungen, liefert die MAC oder setzt selbst den Fehlerzustand),
`quick_connect_done(success, error)`, `quick_connect_error_tick()` (Auto-Dismiss
nach 1,5s). Gleiche Bauart wie `power_button.py`s Hold-Erkennung
(`_pressed_since`/Schwellenwert-Vergleich), nur als State-Methoden statt einer
eigenen Klasse, da es UI-State ist statt eines Hardware-Treibers.

## main.py

- `handle_event()`: `play_pause` `button_down` auf `SCREEN_HOME` startet den
  Hold (`quick_connect_press()`), `button_up` bricht ihn ab, falls noch in
  Phase `"hold"` (`quick_connect_release()`).
- Haupt-Loop: pro Iteration `quick_connect_tick()` aufrufen, solange
  `qc_phase == "hold"`; beim Schwellenübertritt `quick_connect_start()` holen
  und ggf. `bt_worker.start_quick_connect(mac)` anstoßen. Redraw während
  `"hold"`/`"connecting"` gedrosselt auf 0.1s (gleiches Intervall wie
  `PLAYING_REDRAW_INTERVAL`, deckt sowohl die Ring-Animation als auch das
  asynchrone `"connecting"→"error"`-Ende ab - der Erfolgsfall wird bereits vom
  bestehenden `state.screen != last_rendered_screen`-Check erfasst).
- `BTWorker.start_quick_connect(mac)` / `_quick_connect(mac)`: wie
  `start_device_action`, ruft aber `state.quick_connect_done(...)` statt
  `state.bt_device_action_done(...)` auf.

## Rendering (`ui_render.py`)

`render()` zeichnet nach dem eigentlichen Screen zusätzlich
`_draw_quick_connect(img, state)`, falls `state.qc_active` - Ring bei
`qc_progress < 1.0` als `draw.arc(...)`-Bogen, sonst als voller
`draw.ellipse(..., outline=...)`-Kreis; Text darüber (`TEXT`-Farbe normal,
Systemrot `(255, 69, 58)` im Fehlerfall).

## Testing

`test_ui_state.py`: Hold unter/über Schwelle, `quick_connect_start()` ohne
bekanntes Gerät bzw. ohne `last_played`, `quick_connect_done()` Erfolg
(→ `SCREEN_PLAYING`) und Fehler (→ `qc_phase == "error"`, Auto-Dismiss nach
Ablauf von `quick_connect_error_tick()`).
