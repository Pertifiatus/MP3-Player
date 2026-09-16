# Status-Ring: Akku + WLAN/Bluetooth am Displayrand

## Ziel

Akkustand (%), WLAN- und Bluetooth-Status sollen am runden Front-Display sichtbar
sein, ohne bestehenden Screen-Inhalt zu verdecken. Bisher liest `main.py` den
MAX17048 (Fuel Gauge) gar nicht - nur der separate `charge_control.py`-Service tut
das für die Ladelogik. WLAN/BT-Status existiert bereits in `ui_state`/`connectivity.py`,
ist aber nur in den WLAN/BT-Menüs sichtbar, nicht auf einen Blick.

## Sichtbarkeit (Settings-Toggle)

Neuer Eintrag unter Settings → Anzeige: **"Statusanzeige"** (choice, wie
`display.led_mode`), Werte `"home"` (Standard) / `"always"`:
- `"home"`: Ring nur auf dem Homescreen.
- `"always"`: Ring auf jedem Screen.

Technisch macht das kaum einen Unterschied, da der Ring in einem Rand-Bereich liegt,
den kein bestehender Screen aktuell nutzt (siehe unten) - der Toggle existiert rein,
weil der Nutzer das explizit so wollte (z.B. falls der Ring auf dem Now-Playing-Screen
optisch stören sollte).

## Visuelles Design (auf dem Home-Browser-Mockup abgestimmt und freigegeben)

Alle Werte in der 240×240-Koordinate des echten Displays (nicht die gezoomte
320px-Mockup-Darstellung). Ursprung/Formel: `x = 120 + r·cos(θ)`, `y = 120 + r·sin(θ)`,
θ in Grad, steigendes θ läuft am Bildschirm im Uhrzeigersinn.

**Radius/Ring liegt fix bei r=110** (nicht `ui_scale`-abhängig, wie `SAFE_R` eine
Hardware-Konstante) - äußerer Rand des 12px-Strichs landet bei r=116, also ~4px
Abstand zum physischen Bezel-Rand (r=120). Innerer Rand bei r=104 = identisch mit
`SAFE_R`, kollidiert also nicht mit vorhandenem Safe-Area-Inhalt.

1. **Akku-Slot**: Bogen von θ=-55° bis θ=+30° (85° Spannweite), Strichbreite 12px,
   `round`-Linecap an beiden Enden (klassische Pill-/Slot-Form).
   - Track: dunkelgrau (`#3a3a3c`, passt zu `GROUP_BG`-Familie).
   - Fill: Akzentfarbe (`ACCENT` = `#31d1a6`), von θ=-55° bis zum
     ladungs-proportionalen Punkt innerhalb der 85°-Spanne.
2. **WLAN-Punkt**: Kreis bei θ=+38°, Radius 6px (= halbe Strichbreite, gleiche
   optische Dicke wie der Slot).
3. **Bluetooth-Punkt**: Kreis bei θ=+46°, Radius 6px.
   - Abstand Slot-Ende↔WLAN-Punkt und WLAN-Punkt↔BT-Punkt jeweils ~3px zwischen den
     sichtbaren Kanten (Rundungen mit eingerechnet).
4. **Prozent-Text**: klein (~11px Font), nahe der oberen Kante neben dem Slot-Anfang
   (Richtwert (183, 16), siehe Hinweis unten zur Feinjustage).

**Drei Zustände pro Punkt** (WLAN und Bluetooth gleich kodiert, nur Farbe
unterschiedlich - Weiß für WLAN, Blau (`#0a84ff`, passt zu `CATEGORY_COLORS["connectivity"]`)
für Bluetooth):
- **Aus**: gedimmt gefüllt (`#48484a`, wie `_draw_toggle_pill`s Aus-Farbe).
- **An, nicht verbunden**: hohler Ring (`stroke`, kein `fill`) in der jeweiligen Farbe.
- **Verbunden**: voll gefüllt in der jeweiligen Farbe.

## Bekannter Feinjustage-Punkt (bewusst nicht jetzt gelöst)

Der Home-Screen-Header ("MINI-MUSIKPLAYER", zentriert bei y=36, nur wenn
`home_sel == 0`) kann sich mit dem Prozent-Text/Slot-Anfang überschneiden, je
nachdem wie breit der letter-spaced Header mit den echten DejaVu-Fonts tatsächlich
rendert (auf Windows/Arial lokal nicht exakt prüfbar, siehe bestehende Einschränkung
in `NOTES_FOR_PER.md`). Wird beim ersten Live-Test auf echter Hardware geprüft und
falls nötig verschoben (z.B. Prozent-Text ein paar Pixel tiefer) - kein Blocker für
die Implementierung.

## Datenanbindung

### Akkustand (neu für `main.py`)
- `main.py` bekommt eine eigene `MAX17048`-Instanz (gleiches I2C-Gerät, das auch
  `charge_control.py` als separater Prozess nutzt - kurze Einzel-Reads sind
  bus-seitig unproblematisch, kein gemeinsamer State nötig).
- Poll-Intervall: alle 30s (SOC ändert sich langsam, kein Grund häufiger zu lesen,
  gleiches Prinzip wie `charge_control.py`s eigener Poll-Zyklus).
- Fehlerfall (Gauge nicht erreichbar): wie beim IMU in `main()` behandeln -
  `try/except`, Feature fällt auf "kein Ring-Update" zurück statt zu crashen.

### WLAN/Bluetooth-Status (bereits vorhanden, nur neu zusammengeführt)
- **An/Aus**: `state.settings.get("connectivity", "wifi"/"bluetooth")` - existiert
  bereits.
- **Verbunden**: leichte, gedrosselte Polls (kein Shell-Aufruf pro Frame):
  - WLAN: `connectivity.wifi_known_connections()`, `any(n["connected"] for n in ...)`.
  - Bluetooth: `connectivity.bluetooth_known_devices()`, analog.
  - Intervall: alle 10s, gleiches Muster wie die bestehenden
    `WIFI_REDRAW_INTERVAL`/`BT_REDRAW_INTERVAL`-Konstanten in `main.py`.

## Rendering-Integration

Ein neuer `_draw_status_ring(img, draw, state)` in `ui_render.py`, aufgerufen aus
dem zentralen `render()`-Dispatcher (nicht in jeder einzelnen `render_*`-Funktion
dupliziert) - abhängig von `state.settings.get("display", "status_ring")`:
`"always"` → nach jedem Screen zeichnen, `"home"` → nur wenn
`state.screen == ui_state.SCREEN_HOME`.

## Testing

Neue Fälle in `test_ui_render.py` (bestehendes Muster: alle Screens/States
durchrendern, `py_compile`-Smoke-Test): Ring bei 0%/50%/100% Akku und allen
3×3-Kombinationen WLAN/BT-Zustand rendern, keine Exception, Werte bleiben innerhalb
des 240×240-Bilds.
