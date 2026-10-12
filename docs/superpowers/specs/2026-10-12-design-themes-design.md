# Design-Themes: 8 umschaltbare Designs fürs Frontdisplay

## Ziel

Neben dem bisherigen iOS-Look ("Klassik", bleibt Standard) sieben grundlegend
neue Designs, im Einstellungsmenü umschaltbar: **Cybercore, Y2K, Glassmorphism,
Neumorphism, Bento Grid, Pixelhaus, Cyberpunk**. "Grundlegend neu" heißt: eigenes
Layout und eigene Komposition pro Design, nicht nur andere Farben. Alle 17 Screens
plus Statusring und Quick-Connect-Overlay sind pro Design gestaltet.

**Erfolgskriterien:** auf dem Gerät durch alle 8 Designs schaltbar; jedes klar als
seine Designsprache erkennbar; nichts vom runden Rand abgeschnitten; kein Design
langsamer als heute; bestehende Tests grün.

## Umschalten

- `settings.py`: neuer Default `display.theme = "klassik"`.
- `ui_state.SETTINGS_ITEMS["display"]`: neuer **erster** Eintrag
  `{"key": "theme", "label": "Design", "type": "choice", "choices": [...]}` mit
  `klassik/Klassik, cybercore/Cybercore, y2k/Y2K, glass/Glas, neumorph/Neumorph,
  bento/Bento, pixelhaus/Pixelhaus, cyberpunk/Cyberpunk`. Klick schaltet zum
  nächsten Design (bestehende `choice`-Logik), wirkt sofort - der Settings-Screen
  ist damit selbst die Live-Vorschau.
- Unbekannter Wert in `settings.json` → Fallback Klassik (kein Crash).

## Architektur

Inhalt und Look werden getrennt: aus dem `UIState` wird pro Screen ein neutrales
**View** abgeleitet (nur Inhalt), jedes Design zeichnet Views mit komplett eigenem
Layout auf die vollen 240×240 Pixel.

### `ui_views.py` (neu) - Inhalt, keine Pixel

`build(state)` liefert genau ein View pro Frame. Die gesamte "welcher State →
welcher Text"-Logik (heute verstreut über die `render_*`-Funktionen) lebt nur hier.

| View | Felder | Screens |
|---|---|---|
| `ListView` | `screen, title, items, sel` | Home, Bibliothek, Playlist, Einstellungen-Übersicht, BT-Menü/-Gerät/-Scanliste, WLAN-Menü/-Netz/-Scanliste, Playlists verwalten (+Detail) |
| `MessageView` | `screen, title, mood (busy/error/success/info), text, detail, hint, subtitle` | alle "Verbinde…/Fehler:/Suche…/Keine … gefunden/Bitte warten…"-Zustände |
| `SettingsView` | `screen, title, category, rows, sel` | Einstellungen-Detail |
| `PlayingView` | `title, artist, playlist, playlist_idx, color, cover, position, duration, playing, shuffle` | Now Playing |
| `CodeView` | `title, url, code` | YouTube koppeln |
| `ProgressView` | `title, current, total, track, done` | Sync-Fortschritt |
| `PasswordView` | `title, ssid, typed, charset, char_idx, hint` | WLAN-Passwort |
| `StatusView` | `battery_pct, charging, watts, eta_min, wifi_on, wifi_connected, bt_on, bt_connected, show_labels` | Statusring-Overlay |
| `QuickConnectView` | `phase, progress, label, error` | Quick-Connect-Overlay |

- `Item` (Listeneintrag): `label, sub, icon, kind, tone, cover`. `kind` ist die
  Bedeutung (`library`, `resume`, `settings`, Kategorie-Key, `toggle`, `device`,
  `pair_new`, `network`, `connect_new`, `wake`, `playlist`, `track`, …), `tone` ist
  `accent | muted | danger` - Designs übersetzen das in eigene Farben/Objekte.
- `cover` ist eine Referenz `(pfad_oder_None, seed, farbe_hex)`, kein fertiges Bild:
  jedes Design lädt das Cover in der Größe/Form, die es braucht.
- `SettingRow`: `label, kind (toggle/stepper/choice/info/action), value, max, on`.
  Der Live-Speicherwert ("x GB frei") wird hier berechnet, nicht im Renderer.
- Listen enthalten **alle** Einträge; welcher Ausschnitt sichtbar ist, entscheidet
  das Design (Cover nur für sichtbare Einträge laden - siehe 60-Track-Lag-Fix).

### `themes/`-Paket - ein Modul pro Design

`themes/__init__.py`: Registry `THEMES = {"klassik": klassik, ...}`, `get(name)` mit
Klassik-Fallback. Jedes Modul implementiert:

```
draw_list(view, ctx) -> Image      draw_code(view, ctx) -> Image
draw_message(view, ctx) -> Image   draw_progress(view, ctx) -> Image
draw_settings(view, ctx) -> Image  draw_password(view, ctx) -> Image
draw_playing(view, ctx) -> Image   draw_shutdown(ctx) -> Image
draw_status(img, status, ctx)      draw_quick_connect(img, qc, ctx)
animating() -> bool                (optional, Default False)
```

`ctx` = `RenderCtx(scale, status)`: UI-Größen-Faktor und Status-Infos (Bento z.B.
zeigt Akku/WLAN als Kacheln auf Home). Ein Design darf Modul-Zustand halten
(Pixelhaus: Kameraposition über Screenwechsel hinweg).

### `ui_common.py` (neu) - gemeinsame Helfer

Aus `ui_render.py` herausgezogen: Font-Loader, Text zentrieren/kürzen/umbrechen,
Rundbezel-Mathematik (`SAFE_R`, `safe_half_width`), Cover-Laden + prozedurale
Cover-Art, Statusring-Geometrie (Winkel/Radien bleiben hardware-getunt für alle
Designs gleich, nur der Look ändert sich).

### `ui_render.py` - schlanke Fassade

```
render(state):
    theme = themes.get(settings display.theme)
    view  = ui_views.build(state)
    img   = theme.draw_<viewtyp>(view, ctx)
    + theme.draw_status(...)        wenn status_ring_visible()
    + theme.draw_quick_connect(...) wenn qc_active (None-Guard wie heute)
render_shutdown(state=None)   # main.py übergibt state, Default Klassik
animating(state) -> bool      # aktives Design fliegt gerade (Pixelhaus-Kamera)
```

Der heutige Code zieht nach `themes/klassik.py` um. **Klassik bleibt pixelgleich**
(per Vorher/Nachher-Pixelvergleich aller Screens geprüft), mit genau drei
gewollten Vereinheitlichungen in Meldungs-Screens: "Suche Netzwerke…" y 106→110,
"Keine Playlists" y 106→100, WLAN-Menü zeigt beim "Aufwecken…" immer den Header.

### `main.py`

- `render_shutdown(state)` statt `render_shutdown()`.
- Neuer Redraw-Fall: solange `ui_render.animating(state)`, alle
  `ANIM_REDRAW_INTERVAL = 0.05` s neu zeichnen (praktisch: so schnell wie der
  SPI-Push erlaubt). Nur der Pixelhaus-Kameraflug nutzt das.
- Sonst unverändert: Menüs zeichnen nur bei Eingaben neu, Now-Playing wie bisher
  mit 0,1 s - **keine Dauer-Animationen, kein Mehrverbrauch im Idle**.

### Schriften (`Software/fonts/`)

Freie OFL-Schriften von github.com/google/fonts, je Familie mit `OFL.txt`
(Lizenz verlangt das Mitliefern):

| Datei | Größe | Design |
|---|---|---|
| `Orbitron[wght].ttf` | 39 KB | Cybercore (Titel) |
| `ShareTechMono-Regular.ttf` | 43 KB | Cybercore (Text), Cyberpunk (Mikrotext) |
| `Rajdhani-Medium.ttf`, `Rajdhani-Bold.ttf` | 384 + 401 KB | Cyberpunk |
| `Righteous-Regular.ttf` | 43 KB | Y2K (Titel) |
| `Nunito[wght].ttf` | 277 KB | Y2K (Text), Neumorph |
| `Poppins-Regular.ttf`, `Poppins-SemiBold.ttf` | 160 + 157 KB | Glass |
| `SpaceGrotesk[wght].ttf` | 137 KB | Bento |
| `PixelifySans[wght].ttf` | 79 KB | Pixelhaus (Ersatz falls nicht pixelscharf: `Silkscreen-Regular.ttf`, 32 KB) |

Summe ≈ 1,7 MB. Variable Fonts (`[wght]`) bekommen ihr Gewicht per
`set_variation_by_axes`; schlägt das fehl → Regular. Fehlt eine Datei → DejaVu
(bzw. PIL-Default off-device). **Nie ein Crash wegen Fonts.**

### Performance

- Pro Frame wird nur zusammengesetzt. Hintergründe und teure Effekte (Blur, Glow,
  weiche Schatten, Raster/Dither) sind gecacht (`lru_cache`, begrenzt), Schlüssel
  = Größe/Farbe/Cover.
- Messlatte (lokal gemessen, Verhältnis zählt, da der Pi gerade nicht messbar ist):
  der langsamste Screen jedes Designs ≤ Klassik-Now-Playing.

### UI-Größe

Klassik, Cybercore, Y2K, Glass, Neumorph und Cyberpunk skalieren Schrift/Zeilen
mit `ctx.scale` wie heute. Bento und Pixelhaus sind feste Kompositionen und
ignorieren die Einstellung.

## Die Designs

Für alle gilt: alles Wichtige innerhalb `SAFE_R`, Statusring an der heutigen
Position, aber im eigenen Look.

### Klassik
Unverändert der heutige iOS/tvOS-Look.

### Cybercore - blaues Terminal/HUD, "im Mainframe"
- **Look:** Schwarz-Navy, Elektro-Cyan, Weiß, Säuregrün für "OK", Rot für Fehler.
  Hintergrund: Radar-Ringe + Fadenkreuz, Tron-Drahtgitterboden in der unteren
  Hälfte, Binärziffern am Rand, Scanlines. Orbitron (Titel), Share Tech Mono (Rest).
- **Listen:** Terminal-Menü `01 // BIBLIOTHEK`, Auswahl in HUD-Zielklammern ⌜ ⌝
  mit Cyan-Glow, Untertitel als `> …`. Cover als cyan gerasterte Duotone-Bilder.
- **Settings:** Konsolentabelle `HELLIGKEIT ··· [■■■□□]`, Schalter `[ON ]/[OFF]`,
  Auswahl = invertierter Cyan-Balken.
- **Now Playing:** gerastertes Cover im Kreis, Radar-Sweep dreht mit der Wiedergabe,
  Tick-Ring außen als Fortschritt, `STATUS: PLAYING` + Zeit in Mono.
- **Meldungen:** Konsolenzeilen `> VERBINDE…█`, Fehler `!! ERROR` in Rot.
- **Statusring:** Tick-Segmente in Cyan. **Quick Connect:** HUD-Lock-on-Klammern.

### Y2K - Bubblegum-Zukunft von 2001
- **Look:** holografischer Pastellverlauf (Rosa/Babyblau/Flieder/Mint),
  funkelnde 4-Zack-Sterne, Seifenblasen. Righteous mit Chromverlauf + Kontur
  (Titel), Nunito (Text).
- **Listen:** gestapelte glänzende "Aqua"-Candy-Pillen (Gloss-Highlight oben),
  Auswahl = knallpinke Pille + Funkelstern, Icons/Cover in Glasperlen.
- **Settings:** Aqua-Kapselschalter, Stepper als Glanzperlen.
- **Now Playing:** drehende **CD** mit dem Cover als Label; der Regenbogen-Schimmer
  bleibt stehen, während die CD dreht.
- **Meldungen:** Pop-up-Fenster mit Glanz-Titelleiste (XP-Stil); Sync-Fortschritt
  als Aqua-Barber-Pole-Balken.
- **Statusring:** Glanzröhre Pink→Aqua. **Quick Connect:** Funkelring.

### Glassmorphism - Milchglas über Farblicht
- **Look:** dunkles Navy mit großen weichgezeichneten Farb-Orbs; in Bibliothek/
  Playlist nehmen sie die Playlist-Farbe an. Poppins.
- **Listen:** Milchglaskarten mit dünnem Lichtrand; Auswahl groß und hell in der
  Mitte, Nachbarn kleiner und durchsichtiger (Tiefe).
- **Settings:** ein großes Glaspanel, Glaskapsel-Schalter mit leuchtendem Knopf.
- **Now Playing:** unscharfes Cover als Vollbild-Hintergrund, scharfes Cover
  schwebend mit Schatten, Glasleiste mit Zeit/Fortschritt.
- **Statusring:** Glasröhre mit Verlauf. **Quick Connect:** Glaskreis mit Verlaufsbogen.

### Neumorphism - weiches Material
- **Look:** hell #E0E5EC, alles aus einem Material gedrückt (Licht oben links,
  Schatten unten rechts); der ganze runde Screen wirkt wie eine eingedrückte
  Schale. Sanftes Blau als Akzent. Nunito. (Hell → nachts heller als die anderen.)
- **Listen:** Auswahl erhaben, Rest flach; Cover in runden Mulden.
- **Settings:** Neumorph-Schalter (eingelassene Spur, erhabener Knopf), Stepper als
  Schieberegler.
- **Now Playing:** erhabene runde Scheibe mit eingelassenem Cover, rundum
  eingelassene Fortschrittsrille mit Akzentbogen und Knopf.
- **Statusring:** eingelassene Rille. **Quick Connect:** erhabener Kreis mit Rille.

### Bento Grid - Kachel-Mosaik
- **Look:** schwarzer Grund, dunkle Kacheln verschiedener Größe, einige knallige
  (Lime/Orange/Blau/Pink); das Raster wird vom runden Rand angeschnitten → äußere
  Kacheln haben gebogene Außenkanten. Space Grotesk mit großen Zahlen.
- **Home:** Kacheln Bibliothek / Fortsetzen (großes Cover) / Einstellungen + Info-
  Kacheln Akku-% und WLAN/BT. Drehen springt von Kachel zu Kachel.
- **Listen:** Auswahl als große Kachel (großes Cover + Titel), Nachbarn klein,
  Zähler-Kachel "3/12". Einstellungs-Kategorien: alle 6 als 2×3-Raster.
- **Settings:** jede Einstellung eine Kachel mit großem Wert.
- **Now Playing:** Mosaik aus Cover, Titel, großer Zeit, Fortschritt, Play-Status,
  Shuffle.
- **Statusring:** schlanker Lime-Bogen (Raster lässt dafür am Rand Platz).

### Cyberpunk - Night City
- **Look:** Schwarz + Signalgelb #FCEE0A, Rot/Cyan-Akzente; Panels mit
  abgeschrägten Ecken, Warnstreifen, Barcodes, Mikrotext ("SYS//MP3-2077"), leichte
  Scanlines. Rajdhani, Mikrotext Share Tech Mono.
- **Listen:** Auswahl = gelbes gechamfertes Panel mit schwarzem Text und
  Glitch-Versatz (Rot/Cyan-Kanaltrennung); Rest `01 ▸` mit gelber Kontur.
- **Settings:** Segmentschalter `ON|OFF`, Stepper als schräge Segmentbalken.
- **Now Playing:** Cover im gechamferten Rahmen mit gelegentlichen Glitch-Streifen
  (deterministisch aus der Position), Titel groß gelb, segmentierter Balken.
- **Meldungen:** ALERT-Panel mit Warnstreifen; WLAN-Passwort als
  "Breach Protocol"-Codespalte.
- **Statusring:** schräge gelbe Segmente, rot unter 20 %.

### Pixelhaus - schwebende Kamera durch ein Pixelart-Haus (2D-Seitenansicht)

**Asset:** Pers Beispielbild (1536×1024 Pixelart-Villa im Querschnitt) als
`Software/assets/pixelhaus.png`, 1:1 verwendet - ein Raum füllt den runden
240-px-Screen fast genau aus. Wird beim ersten Gebrauch geladen (RGB im RAM, ~4,7 MB).
Fehlt es → schlichter dunkler Hintergrund mit denselben Dialogboxen, kein Crash.

**Raumplan** (Mittelpunkte im Bild, ca. - Feinjustage bei der Umsetzung):

| Screen | Raum | ≈ Mitte (x, y) |
|---|---|---|
| Home (+ Quick Connect) | Wohnzimmer mit Kamin | (220, 635) |
| Bibliothek | Bibliothek | (930, 458) |
| Playlist | Bibliothek, Kamera näher am Regal | (895, 458) |
| Now Playing | Musikzimmer | (1198, 458) |
| Einstellungen-Übersicht | Werkstatt | (1218, 635) |
| Einstellungen → Anzeige | Großer Saal (Bogenfenster) | (642, 298) |
| Einstellungen → LED | Treppenhalle (Kronleuchter) | (642, 458) |
| Einstellungen → Verbindung, alle WLAN/BT-Screens | Arbeitszimmer | (378, 458) |
| Einstellungen → Sync, YouTube-Login, Sync-Fortschritt | Kinderzimmer | (1168, 298) |
| Einstellungen → Bewegung | Küche | (918, 635) |
| Einstellungen → Über | Eingangshalle | (648, 635) |
| Playlists verwalten (+Detail) | Kellerlager | (230, 835) |
| Ausschalten | Schlafzimmer: "Gute Nacht…" | (350, 298) |

**Kamera:**
- Screenwechsel → Flug geradeaus (durch Wände/Decken) zum Zielraum,
  Dauer `clamp(0,35 s + Distanz/1500 px/s, 0,4 s, 1,0 s)`, Ease-in-out, in der
  Flugmitte leichter Zoom-out (bis 0,8×, Drohnen-Gefühl).
- Auswahl drehen auf Home/Werkstatt → kurzer Drift (≤ 30 px) Richtung des Raums,
  in den man gleich fliegen würde, plus Pixelpfeil am Rand in diese Richtung.
- Nach dem Flug steht das Bild; `animating()` ist wahr bis der Ruhe-Frame gezeichnet
  wurde. Erster Frame nach Design-Wechsel: Kamera springt direkt ans Ziel.
- Während des Flugs keine Dialogbox, sie erscheint bei Ankunft.

**UI im Raum:**
- Oben kleines Holzschild mit dem Namen.
- Unten RPG-Dialogbox (dunkles Navy, heller Pixelrahmen, Pixelschrift ohne
  Antialiasing, auf 2×-Pixelraster): Auswahl mit ▶, Nachbarn gedimmt, Zähler "3/12".
- Cover als grobe Pixel-Cover (auf 16×16 herunter, NEAREST hoch).
- **Now Playing:** Pixel-Cover als gerahmtes Bild an der Wand, Noten ♪ steigen vom
  Flügel auf (aus der Position animiert), Dialogbox mit Titel, Pixelbalken, Zeit, ▶/❚❚.
- **Meldungen:** Dialogbox mit laufenden Punkten. **Settings:** Pixelmenü mit
  Pixelschaltern [■□] und Balken. **Code/Fortschritt/Passwort:** jeweils in der
  Dialogbox.
- **Statusring:** grobe Pixeloptik (halbe Auflösung zeichnen, NEAREST hoch).

## Testing & Verifikation

1. **Klassik-Pixelvergleich:** vor dem Umbau alle Screens × alle UI-Größen als PNG
   sichern, danach vergleichen - nur die drei oben genannten Diffs erlaubt.
2. `test_ui_render.py`: alle Screens × alle UI-Größen × **alle 8 Designs**
   (inkl. Overlays, Shutdown, langer 60-Track-Playlist); jede Registry-Choice hat
   ein Theme-Modul; unbekanntes Theme → Klassik.
3. Pixelhaus: Kameraflug wird nach Ablauf der Flugdauer ruhig (`animating()` → False),
   mit steuerbarer Uhr getestet.
4. `test_ui_state.py`: "Design" schaltet durch alle 8 und springt zurück auf Klassik.
5. `preview_themes.py`: PNG-Übersichtsblatt pro Design (alle Screens) nach
   `Software/previews/` (gitignored) - Anschauen ohne Pi.
6. Render-Zeiten pro Design lokal messen, gegen die Performance-Messlatte prüfen.
7. Live-Test auf dem Pi durch Per (Deploy nur nach Rückfrage).

## Nicht im Umfang

Idle-Animationen in Menüs, Tag/Nacht-Varianten, Übergangsanimationen in anderen
Designs als Pixelhaus, Rückdisplay (SSD1306), designabhängige LED-Farben.
