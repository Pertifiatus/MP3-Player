## Nachtrag: UI-Groesse überarbeitet - echtes Reflow statt Zoom (12.09.2026, fünfter Durchgang)

Kein Pi-Zugriff, rein lokal (Windows) an `ui_render.py` gearbeitet + Logik-/Layout-
Smoketest (`test_ui_render.py`, neu) - **noch nicht auf echter Hardware/mit den
echten DejaVu-Fonts visuell verifiziert**, bitte beim nächsten Boot durch alle 5
UI-Groesse-Stufen auf Home/Bibliothek/Playlist/Settings klicken.

Auslöser: Feedback, dass "UI Scale" bisher nur pixelig rein-/rauszoomt statt bei
kleineren Stufen den gewonnenen Platz für mehr Inhalt zu nutzen, dass generell zu
viel Text abgeschnitten wird und dass die Ränder unnötig dick sind.

**Kompletter Umbau von `_apply_ui_scale`** (der alte Zoom-aufs-fertige-Bild-Ansatz,
siehe Nachtrag weiter unten - jetzt entfernt) **zu echter Layout-Skalierung**: Der
`scale`-Faktor fließt jetzt direkt in Fontgrößen, Row-Heights, Icon-Größen und
Innenabstände in `_render_nav_list`, `render_settings_detail` etc. ein, statt nur
das fertige 240×240-Bild zu croppen/skalieren. Effekt: bei kleiner UI-Groesse
passen durch kleinere Rows tatsächlich mehr Einträge in denselben runden Safe-Bereich
(gemessen: Playlist-Liste zeigt bei Stufe 1 eine dritte teilsichtbare Zeile, die bei
Stufe 3 nicht mehr da ist), bei größerer UI-Groesse werden Fonts/Rows größer
(besser lesbar), dafür passt weniger gleichzeitig auf den Screen - erwarteter
Trade-off, kein Bug. Fonts werden jetzt lazy per `(key, scale)` geladen und gecacht
(`ui_render._font`), nicht mehr als fixe Modul-Konstanten.

Nebenbei allgemein die Innenabstände verkleinert (Header-Padding, Icon/Text-Abstände
in den Listen, Settings-Card-Ränder), damit generell mehr vom runden Screen genutzt
wird, unabhängig von der UI-Groesse-Stufe. **SAFE_R (der physische Rundbezel-Wert)
wurde bewusst NICHT verändert** - das ist eine Hardware-Grenze, keine Stil-Vorgabe.

**Echter Bug beim Umbau gefunden und gefixt:** `render_settings_detail` ging bisher
davon aus, dass eine Settings-Kategorie immer komplett auf den Screen passt (stimmte
zufällig bei allen aktuellen Kategorien bei Stufe 3). Sobald Rows bei größeren
UI-Groesse-Stufen mitwachsen, ragte die Karte für Kategorien mit mehr Einträgen
(z.B. "LED", 4 Einträge) über den unteren Bildrand hinaus - `draw.rounded_rectangle`
crashte dabei sogar hart (`x1 must be greater than or equal to x0`), weil die Karte
an dem Punkt schon komplett außerhalb des runden Safe-Bereichs lag. Fix: die Liste
scrollt jetzt um die aktuelle Auswahl herum (gleiches Prinzip wie die Home/Bibliothek-
Listen), inkl. kleiner Auf/Ab-Pfeil-Indikatoren, wenn oben/unten noch mehr Einträge
verborgen sind. `test_ui_render.py` rendert alle Screens bei allen 5 Stufen durch und
hätte diesen Crash sofort gefangen.

`UI_SCALE_STEPS`-Werte dabei leicht verbreitert (0.75-1.3 statt 0.82-1.25), damit der
jetzt echte Skalierungseffekt sichtbarer ist. Stufe 3 bleibt exakt 1.0 = alle Pixel-
Konstanten im File wie ursprünglich getunt, unverändertes Verhalten für den Standard-
Fall.

---

## Nachtrag: ~1fps-Refresh + Encoder-Aussetzer (12.09.2026, vierter Durchgang)

Du warst kurz weg, ich hatte keinen Pi-Zugriff. Beides unten ist lokal
simuliert/getestet (reine Logik + Timing-Messung auf meinem Windows-Rechner) und
per Recherche im offiziellen Adafruit_Blinka_Displayio-Quellcode auf GitHub
abgesichert — **aber noch NICHT auf echter Hardware verifiziert**. Bitte beim
nächsten Boot beides gezielt gegentesten (Navigation durchklicken + Encoder in
beide Richtungen mehrfach drehen).

### 1fps-Fix: `push_frame()` → `FrameSink` in [main.py](main.py)

Root Cause gefunden, nicht nur vermutet: Ich habe den tatsächlichen Quellcode von
`Adafruit_Blinka_Displayio` auf GitHub geprüft. `displayio.OnDiskBitmap._get_pixel()`
liest **jeden einzelnen Pixel per eigenem Datei-`seek()`+`read()` vom Datenträger**,
und das passiert innerhalb der (ebenfalls reinem Python, pixel-für-pixel-Schleife)
Bildkomposition in `_tilegrid.py`. Die alte `push_frame()` hat bei **jedem** Redraw
ein komplett neues `OnDiskBitmap` aus einer frisch gespeicherten Datei gebaut — macht
bei 240×240 = 57.600 Pixel pro Frame theoretisch 57.600 Einzel-Dateizugriffe. Das
erklärt die ~1fps ziemlich genau (das reine `ui_render()` selbst braucht lokal
gemessen nur ~20ms/Frame, ist also nicht der Flaschenhals).

Fix: `FrameSink`-Klasse baut `Bitmap`/`TileGrid`/`Group` **einmalig** beim Start
(nicht mehr pro Frame neu), hält sie im RAM, und jeder Redraw schreibt die
RGB565-Pixel direkt in das bestehende `Bitmap` — kein Datei-Umweg mehr. Farbkonvertierung
RGB→RGB565 läuft vektorisiert über numpy (schnell), nur das eigentliche Schreiben in
den `Bitmap` läuft noch pixelweise über `bitmap[i] = value` (das ist die einzige
öffentlich dokumentierte Schreib-API, die ich im Quellcode bestätigt gefunden habe —
lokal gemessen ~5-7ms für 57.600 Pixel auf einem schnellen PC, auf dem CM4 evtl.
30-100ms, aber selbst das wäre um Größenordnungen schneller als der alte
Platten-Umweg).

**Falls es auf dem Pi immer noch spürbar hakt:** nächster Hebel wäre, `displayio`
für die Pixel-Übertragung ganz zu umgehen und die RGB565-Bytes direkt über den
SPI-Bus zu schreiben (wie z.B. `luma.lcd` es für andere Displays macht) — das ist ein
größerer Umbau, den ich nicht blind schreiben wollte ohne die aktuelle
Verbesserung erst mal live zu sehen.

### Encoder-Fix: Debounce-State-Machine in [buttonbox.py](buttonbox.py)

Die alte `_QUAD_TABLE`-Logik hat bei **jedem einzelnen Viertelschritt** gefeuert und
hatte keinerlei Prellschutz auf den Encoder-Leitungen (nur Buttons hatten
`DEBOUNCE_S`). Recherche dazu (siehe Quellenliste unten) bestätigt: genau das ist
eine bekannte Fehlerklasse bei I2C-gepollten Encodern — ein Prellen auf nur einer der
beiden Leitungen (A oder B) kann in der einfachen Tabelle als gültiger Übergang in
die **falsche** Richtung interpretiert werden, was zur gemeldeten
richtungsabhängigen Unzuverlässigkeit passt.

Neue Logik in `decode_encoder_step()`: läuft dem gültigen Gray-Code-Zyklus
(00→01→11→10→00) als Zähler entlang und feuert erst nach einem **vollständigen**,
in sich konsistenten 4-Schritt-Durchlauf (= ein Klick am Rastpunkt). Prellen
(Sprung zurück zum vorherigen Wert) und übersprungene Zwischenzustände (bei zu
langsamer Poll-Schleife) verwerfen jeweils nur den einen zweideutigen Schritt,
lösen aber keine Fehlauslösung mehr aus. Mit 8 Tests in
[test_buttonbox.py](test_buttonbox.py) durchgetestet (saubere CW/CCW-Klicks,
Prellen an verschiedenen Stellen der Sequenz, übersprungene Zustände) — alle grün.

**Nebeneffekt, bitte beachten:** Die alte Logik hat pro physischem Klick (4
Viertelschritte) theoretisch 4x ausgelöst, die neue genau 1x pro Klick. Falls sich
der Encoder jetzt "zu träge" anfühlt (mehr Drehung nötig pro Menüschritt als
gewohnt), sag mir das — dann justiere ich `DETENT_STEPS` in `buttonbox.py`.

Da der 1fps-Bug die komplette Poll-Schleife bei jedem Redraw für hunderte
Millisekunden blockiert hat, dürfte der FrameSink-Fix allein schon einen Großteil
der Encoder-Aussetzer beheben (verpasste Zwischenzustände durch zu seltenes
Pollen) — die Debounce-Fix behebt zusätzlich die richtungsabhängigen Fehlauslösungen
durch Prellen, die auch bei schneller Poll-Schleife noch auftreten könnten.

## Nachtrag: UI-Größe-Einstellung (11.09.2026, dritter Durchgang)

**Überholt, siehe Nachtrag ganz oben (12.09.2026, fünfter Durchgang)** - der
Zoom-Ansatz unten wurde durch echte Layout-Skalierung ersetzt. Als Historie
stehen gelassen.

Neuer Settings-Punkt unter Anzeige: "UI-Groesse" (Stepper 1-5, Standard 3=100%).
Implementiert als **Zoom aufs fertig gerenderte Bild** (`_apply_ui_scale` in
`ui_render.py`), nicht als Skalierung jeder einzelnen Pixelzahl im Code — deutlich
weniger Code, kein Risiko dass irgendwo eine feste Zahl vergessen wird und Elemente
überlappen. Trade-off: bei größeren Stufen wird das Bild reingezoomt (Ränder werden
abgeschnitten, wie bei jedem Digital-Zoom), bei kleineren rausgezoomt (schwarzer Rand
rundrum). Lokal bei allen 5 Stufen getestet, sieht sauber aus. Logik-Tests weiterhin
grün (nur ein neuer Settings-Eintrag, State-Machine sonst unverändert).

## Nachtrag: Apple/iOS-Redesign (11.09.2026, zweiter Durchgang)

Auf Wunsch komplett neuer visueller Look für `ui_render.py` (State-Machine/Logik
unverändert, nur die Optik):
- Echtes Schwarz als Hintergrund statt Dunkelgrau, iOS-System-Grau-Palette für Text
- Settings-Kategorien haben jetzt knallige, iOS-typische Icon-Farben (Anzeige=Orange,
  LED=Gelb, Verbindung=Blau, Sync=Türkis, Bewegung=Rot, Über=Grau) statt einheitlichem
  Grau
- Settings-Detail-Screens sind jetzt eine einzelne abgerundete Karte mit
  Trennlinien zwischen den Zeilen (iOS "Inset Grouped List"), statt einzelner Pillen
  pro Zeile
- Now-Playing hat jetzt einen echten Frosted-Glass-Effekt (geblurrter,
  abgedunkelter Ausschnitt hinter einer abgerundeten Pille) für die
  Play/Pause-Anzeige, statt nur freistehendem Text
- Icon-Badges sind jetzt "Squircle"-artig (großzügigerer Eckenradius) statt einfacher
  abgerundeter Quadrate

Alles wieder lokal gerendert + die 8 Logik-Tests laufen weiterhin durch (an der
State-Machine wurde nichts geändert). Gleiche Einschränkung wie vorher: nie auf
echter Hardware/DejaVu gesehen.

---

# Notizen zum UI/Interface-Ausbau (11.09.2026, während du weg warst)

Pi war die ganze Zeit aus — nichts davon ist auf echter Hardware getestet. Ich habe
alle Screens lokal mit PIL gerendert (Arial statt DejaVu als Ersatz-Font, da DejaVu
hier auf Windows nicht verfügbar war) um Layout/Lesbarkeit zu prüfen, und dabei ein
paar echte Bugs gefunden und gefixt (siehe unten). Alle Python-Dateien sind
syntax-geprüft (`py_compile`), aber der komplette Hardware-Pfad (Buttons, IMU, beide
Displays, LEDs) läuft zum ersten Mal beim nächsten Boot — bitte Schritt für Schritt
testen, nicht direkt alles auf einmal.

## Neue/geänderte Dateien in `Software/`

| Datei | Zweck |
|---|---|
| `ui_state.py` | State Machine: Home, Bibliothek, Playlist, Now-Playing, Settings (Kategorien + Detail), Sync-Login, Sync-Progress |
| `ui_render.py` | PIL-Rendering für alle Screens, inkl. rotierender Cover-Art-Platte mit Tonarm |
| `main.py` | Event-Loop: ButtonBox + IMU (Bewegungs-Features) + Display |
| `qmi8658.py` | IMU-Treiber als wiederverwendbares Modul (vorher nur Einweg-Testskript) |
| `led_control.py` | SK6812-Ansteuerung (Presets, Modi) |
| `led_service.py` | **Separater** root-Prozess, der `settings.json` beobachtet und die LEDs ansteuert |
| `settings.py` | Persistente Einstellungen (JSON-Datei) |
| `sync_youtube.py` | YouTube-Device-Flow-Login (echt implementiert) + simulierter Sync (Platzhalter) |

## Was garantiert noch nicht getestet ist — bitte in dieser Reihenfolge

1. **`python3 main.py` auf dem Pi starten** (braucht laufendes Front-Display + ButtonBox +
   QMI8658A — alles einzeln schon mal verifiziert, aber nie zusammen in einer Schleife).
2. Falls Fehler beim Start: `adafruit-blinka` + `adafruit-circuitpython-neopixel` sind
   evtl. noch nicht installiert (`pip3 install --break-system-packages
   adafruit-circuitpython-neopixel`) — nur für `led_control.py`/`led_service.py` nötig,
   `main.py` selbst importiert das nicht direkt.
3. `led_service.py` **braucht `sudo`** (PWM/DMA für die LEDs) — separat testen:
   `sudo python3 led_service.py`, dann in `settings.json` `led.enabled` auf `true`
   setzen und schauen ob die LEDs reagieren.

## Bewusste Design-Entscheidungen (getroffen, nicht mehr offen)

- **Stop-Taste = "Zurück"** in allen Menüs, zusätzlich "echtes Stop" (setzt Now-Playing
  zurück auf Home) wenn man sie im Now-Playing-Screen drückt.
- **Encoder-Drehen im Now-Playing-Screen = Track vor/zurück** (nicht Lautstärke — dafür
  gibt's aktuell keinen dedizierten Regler, siehe offene Frage unten).
- **Settings sind in 6 Kategorien** (Anzeige, LED, Verbindung, Sync, Bewegung, Über)
  organisiert, nicht eine lange flache Liste — bei einem 240px-Rundbildschirm sonst
  schnell unübersichtlich.
- **Icons als Buchstaben-Badges** (A/L/V/S/B/i) statt Symbol-Glyphen für die
  Settings-Kategorien — ich hatte erst Unicode-Symbole (☀ ✦ ⚡ ↻ ↕ ℹ) probiert, aber
  mehrere davon fehlen sogar in Arial (einem sehr breit unterstützten Font). Nur ♪
  und ⚙ sind aus einem früheren Live-Test auf dem echten Pi/DejaVu bestätigt sicher,
  alles andere Risiko wurde durch ASCII/Buchstaben ersetzt. **Bitte beim ersten Live-Test
  trotzdem kurz schauen ob irgendwo ein Kästchen (☐) statt einem Zeichen auftaucht** —
  falls ja, sag mir wo, dann tausche ich das gezielt aus.
- **Sync-Backend ist simuliert** (`sync_youtube.sync_library()` erzeugt Fake-Fortschritt
  über 8 Demo-Tracks) — die UI drumherum (Fortschrittsbalken, TV-Code-Screen) ist aber
  vollständig fertig und funktional, nur der eigentliche Download/ytmusicapi/yt-dlp/ffmpeg-Teil
  fehlt noch (siehe "Braucht deine Mitarbeit" unten).
- **LED-Kette läuft als separater root-Prozess** (`led_service.py`), nicht im
  Haupt-UI-Skript — vermeidet, dass die ganze UI (Display/Buttons/IMU) als root laufen
  muss, nur weil die LEDs PWM+DMA-Zugriff brauchen.

## Bewegungssensor-Features ("coole Sachen" mit dem Accelerometer)

Umgesetzt (in `main.py` / `apply_motion_features`):
- **Schütteln = Shuffle**: kräftige Bewegung (|Beschleunigung| > 2.2g) während
  Now-Playing überspringt zufällig vor/zurück und aktiviert die Shuffle-Anzeige.
- **Umdrehen = Pause**: wenn `orientation()` "z-" liefert (siehe Achsen-Warnung unten)
  und gerade etwas läuft, wird automatisch pausiert.

**Nicht umgesetzt, nur als Setting vorhanden (tut noch nichts):**
- **Auto-Display-Wechsel** (vorne/hinten je nach Ausrichtung) — der Setting-Toggle
  existiert in den Einstellungen, ist aber noch nicht verdrahtet. Grund: das würde
  bedeuten, das Rück-Display (SSD1306/luma) aus derselben Event-Loop wie das
  Front-Display zu steuern — das ist eine echte Architektur-Erweiterung
  (zwei Displays gleichzeitig koordinieren), die ich nicht blind bauen wollte ohne
  das live zu sehen. Wenn du zurück bist, können wir das als nächsten Schritt angehen.

**⚠️ Wichtig — Achsen-Mapping ist geraten, nicht verifiziert:** `orientation()` in
`qmi8658.py` gibt einfach die Achse zurück, die am nächsten an ±1g liegt (z.B. "z-").
Ich weiß nicht, welche physische Seite (vorne/hinten) das tatsächlich bedeutet — das
hängt davon ab, wie der QMI8658A-Chip auf der Platine liegt. **Bitte beim ersten Test:
Board flach hinlegen (Vorderseite nach oben), `python3 qmi8658.py` laufen lassen und
schauen welche Achse/Vorzeichen ausgegeben wird, dann das Gleiche mit Rückseite nach
oben — danach sag mir die beiden Werte, dann stelle ich `"z-"` in `apply_motion_features`
korrekt ein** (aktuell nur geraten, könnte auch falsch rum sein oder eine andere Achse
sein).

## Fragen, die ich nicht beantworten konnte (brauchen deine Entscheidung)

1. **LED-Kettenlänge:** `led_control.py` geht von 9 LEDs aus (6 Hauptplatine + 3
   ButtonBox, angenommen in Reihe). Nicht anhand des PCB-Layouts verifiziert — falls
   falsch, `NUM_LEDS` in `led_control.py` anpassen.
2. **SK6812MINI-E: RGB oder RGBW?** Ich bin von reinem RGB ausgegangen (Standard für
   die "MINI-E"-Variante). Falls es tatsächlich RGBW ist, braucht `neopixel.NeoPixel(...)`
   einen zusätzlichen `pixel_order=neopixel.GRBW`-Parameter.
3. **Lautstärke-Regelung:** Es gibt aktuell keinen UI-Weg die Lautstärke zu ändern
   (Encoder ist für Track-Skip belegt). Optionen für später: langes Drücken des
   Encoders = Lautstärke-Modus, oder ein Settings-Eintrag, oder Shuffle-Taste
   umwidmen. Sag mir was du willst.
4. **Auto-Sleep-Verhalten:** Der Settings-Eintrag "Auto-Aus" (Display-Standby nach
   X Sekunden Inaktivität) existiert als Einstellung, ist aber in `main.py` noch
   nicht tatsächlich verdrahtet (Backlight wird nirgends automatisch ausgeschaltet).
   Soll das den Backlight-Pin einfach dimmen/ausschalten, oder den ganzen
   Displayinhalt auf schwarz setzen?

## YouTube-Sync / TV-Setup — was noch fehlt

`sync_youtube.py` implementiert den **echten** Google-OAuth-Device-Flow (der
Standard-Mechanismus für TV/Limited-Input-Geräte: Code + URL anzeigen, User gibt den
Code auf Handy/PC ein, wir pollen bis bestätigt). Das ist kein Fake — das ist echtes,
funktionierendes Protokoll, sobald du Zugangsdaten hast.

**Was du dafür brauchst, bevor das erste Mal ein echter Login klappt:**
1. In der Google Cloud Console ein Projekt anlegen.
2. OAuth-Consent-Screen einrichten (reicht im "Testing"-Modus für privaten Gebrauch).
3. "YouTube Data API v3" aktivieren.
4. Unter Credentials einen OAuth-Client vom Typ **"TVs and Limited Input devices"**
   anlegen.
5. Die `client_id`/`client_secret` in eine neue Datei `Software/youtube_credentials.json`
   eintragen (Format steht im Docstring von `sync_youtube.py` oben) — **diese Datei
   NICHT committen**, sie ist noch nicht in `.gitignore`, das sollte ich/du noch
   ergänzen sobald die Datei existiert.

**Danach fehlt noch (nicht implementiert, nur die UI-Hülle steht):**
- Echte Bibliotheks-Abfrage über `ytmusicapi` (aktuell nicht mal als pip-Paket
  installiert).
- Download über `yt-dlp` + Remux über `ffmpeg`.
- Der WLAN/Metered-Check in `wifi_ok_for_sync()` ist aktuell ein Stub der immer
  `True` zurückgibt — müsste die echte Heim-SSID kennen und `nmcli` abfragen.

Das ist bewusst so gelassen — echtes Downloaden ohne deine OAuth-Zugangsdaten kann ich
eh nicht testen, aber die komplette UI drumherum (Code anzeigen, auf Bestätigung
warten, Fortschrittsbalken) ist fertig und sollte schon mit den echten Zugangsdaten
funktionieren, auch ohne dass der eigentliche Download-Teil schon existiert.

## Kleinere Bugs, die der lokale Test aufgedeckt hat (schon gefixt)

- `_render_nav_list` griff über einen privaten PIL-internen Pfad (`draw._image`) auf
  das Bild zu, um Cover-Art einzufügen — sauber gefixt, `img` wird jetzt explizit
  durchgereicht.
- Zwei Aufrufstellen von `_render_nav_list` hatten die alte Funktionssignatur nach
  einer Änderung nicht mitbekommen (`render_settings_root` u.a.) — hätte beim ersten
  Öffnen der Einstellungen sofort einen Crash gegeben.
- Lange Titel/Untertitel liefen über den Bildschirmrand hinaus statt abgeschnitten zu
  werden — Ellipsis-Kürzung ergänzt (wie im `beispiel.html`-Original).
- `state.shuffle` wurde in `ui_render.py` referenziert aber nie in `UIState.__init__`
  deklariert — hätte beim ersten Now-Playing-Aufruf gecrasht.

## Nicht getestet, aber nicht offensichtlich riskant

- Die hier vorhergesagte Performance-Sorge zum BMP-Datei-Umweg hat sich bestätigt
  (~1fps live gemeldet) — siehe "Nachtrag: ~1fps-Refresh + Encoder-Aussetzer" ganz
  oben in dieser Datei für Root Cause + Fix.
