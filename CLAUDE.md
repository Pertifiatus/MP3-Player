# Mini-Musikplayer — Projektkontext für Claude Code

*Diese Datei fasst den aktuellen Stand des Projekts zusammen, damit Claude Code ohne Rückfragen direkt produktiv mitarbeiten kann. Lege sie ins Repo-Root (Claude Code liest `CLAUDE.md` automatisch beim Start).*

---

## 1. Projektziel (Kurzfassung)

Ein selbstgebauter, kompakter Musikplayer:

- **Front:** rundes Display (GC9A01) zur Menü-Navigation
- **Rückseite:** monochromes OLED (SSD1306) für musiksynchrone Visualisierungen
- **Autarke Synchronisation** der YouTube-Music-Bibliothek direkt aufs Gerät (kein Home-Server nötig)
- **Ausgabe:** primär Bluetooth A2DP, zusätzlich 3,5mm-Klinke
- **Formfaktor:** knapp über Akkugröße, kleiner als ein iPod Touch
- **Stückzahl:** 2 Geräte (Prototyp-Serie)

**Compute:** Raspberry Pi CM4 (Wireless, Lite = ohne eMMC → bootet zwingend von microSD), gesockelt über 2× Hirose-Mezzanine-Connector.

---

## 2. Aktueller Stand (05.09.2026)

- **Hauptboard von Board 1** ist vollständig verlötet und wurde erstmals eingeschaltet.
- **Bootproblem gelöst:** kalte Lötstelle am Hirose-Mezzanine-Connector, Pin 86 (Versorgung des SD-Kartenslots) — durch Reflow behoben. Trat nach erneutem Ab-/Aufstecken des CM4-Moduls kurzzeitig wieder auf, danach wieder normal gebootet — bei Bootproblemen also **zuerst Pin 86 / Mezzanine-Sitz prüfen**.
- **WLAN-Verbindungsproblem** nach dem Aufstecken durch komplettes Neuflashen der SD-Karte gelöst.
- **Kontinuitätsprüfung vor Akku-Anschluss:** USB-C-Port verlötet und getestet (CC1/CC2-Sink-Widerstände ✅), 5V am Charger-IC gemessen. Schritte 2–6 der Checkliste (Durchgangsmessungen PS/SYNC, BTST, Pin-Ebene, Power-Up ohne Akku, Labornetzteil-Test) **stehen noch aus, bevor der LiPo-Akku angeschlossen wird**.
- **Software-Bring-up** ist als Plan dokumentiert (siehe Abschnitt 5), aber noch nicht durchgeführt — das ist vermutlich der Einstiegspunkt für die Arbeit mit Claude Code.

⚠️ **Bekanntes Kurzschlussrisiko (noch offen, Stand letztem PCB-Review):** R6 *und* R7 (PS/SYNC-Bestückungsoption) waren beide bestückt — das brückt VBAT/VSYS direkt auf GND. Vor dem ersten echten Akku-Anschluss unbedingt die Kontinuitätsprüfung aus Abschnitt 4 durchführen bzw. verifizieren, dass nur einer der beiden Widerstände bestückt ist.

---

## 3. Hardware-Referenz für Software-Arbeit

### CM4-Pinout (GPIO, BCM-Nummerierung)

| Funktion | Pin(s) | Hinweis |
|---|---|---|
| I2C-Hauptbus | GPIO2 (SDA1), GPIO3 (SCL1) | interne Pull-ups vorhanden |
| SPI0 – Front-Display GC9A01 | CE0=GPIO8, MOSI=GPIO10, SCLK=GPIO11 | MISO (GPIO9) frei, da Display write-only |
| SPI4 – Rück-Display SSD1306 | CE0=GPIO4, MOSI=GPIO6, SCLK=GPIO7 | `dtoverlay=spi4-1cs` |
| I2S/PCM – ES8388 Audio | BCLK=GPIO18, LRCLK=GPIO19, DIN=GPIO20, DOUT=GPIO21 | einziger PCM-Pinsatz |
| ES8388 MCLK | GPIO5 (GPCLK1) | eigenes Overlay nötig, z.B. 12,288 MHz für 256×48kHz |
| LED-Datenleitung (SK6812) | GPIO12 (PWM0_0) | |
| Front-Display DC / RST | GPIO24 / GPIO25 | |
| Rück-Display DC / RST | GPIO26 / GPIO27 | |
| Front-Display Backlight (PWM) | GPIO13 (PWM0_1) | |
| TPS63020 EN (Soft-Shutdown) | GPIO16 | siehe Power-Hold unten |
| RT9466 CEB (Charger Enable) | GPIO17 | für 80%-Ladelimit-Logik |
| RT9466 INT | GPIO22 | |
| MAX17048 ALRT | GPIO23 | |
| QMI8658A INT1 | GPIO0 (ID_SD, Pin 36) | zweckentfremdet, siehe unten |
| Klinkenbuchse Jack-Detect | GPIO1 (ID_SC, Pin 35) | **laut Netzliste aktuell nicht verdrahtet, siehe Abschnitt 6** |
| Power-Taster (Eingang) | GPIO9 | |
| Debug-UART | GPIO14 (TXD0) / GPIO15 (RXD0) | **kein Testpad/Header vorhanden** |

**Wichtig in `config.txt`** (GPIO0/1 sind normalerweise für HAT-EEPROM reserviert):
```
force_eeprom_read=0
disable_poe_fan=1
dtparam=i2c_arm=on
dtparam=spi=on
dtoverlay=spi4-1cs
```

### I2C-Bus-Belegung

| Gerät | Adresse |
|---|---|
| MAX17048 (Fuel Gauge) | 0x36 |
| SX1509 (GPIO-Expander, Tasten/LEDs) | 0x3E / 0x3F |
| QMI8658A (IMU) | 0x6A / 0x6B |
| ES8388 (Audio-Codec) | Datenblatt prüfen — nicht final verifiziert |

### Wichtige Bauteile & Eigenheiten

- **RT9466GQW** (USB-C-Charger, ersetzt BQ25895) — Registeradressen weichen vom BQ25895 ab, eigener I2C-Treiber nötig, kein Copy-Paste möglich.
- **TPS63020** (Buck-Boost) — Power-Good-Pin für Debugging verfügbar, EN-Pin = Soft-Shutdown-Schalter (GPIO16).
- **MAX17048** (Fuel Gauge) — ALRT-Pin für Low-Battery-Shutdown, SOC per I2C auslesbar (für 80%-Ladelimit).
- **ES8388** (Audio-Codec, ersetzt WM8960) — **kein offizieller Mainline-Kernel-Treiber**, Community-Overlay nötig; größter Software-Mehraufwand im Projekt.
- **QMI8658A** (IMU) — kein Kernel-Overlay, wird direkt per I2C/`smbus` angesprochen.
- **SX1509** (I2C-GPIO-Expander für Tasten/LEDs) — Hardware-Debouncing, PWM-LED-Treiber integriert.

---

## 4. Vor dem Akku-Anschluss: Kontinuitätsprüfung (Checkliste)

Vor jedem ersten Akku-Anschluss an ein gefertigtes Board (bei abgestecktem USB, ohne Akku, Multimeter im Diodenmodus):

1. Optische Kontrolle der QFN-Gehäuse (RT9466, TPS63020, ES8388, SX1509) auf Lötbrücken.
2. Durchgangsmessung gegen GND: VBUS, VSYS, VBAT/VINA, 3V3, REGN, LX.
3. **PS/SYNC (R6/R7):** darf nur in **einer** Richtung Durchgang zeigen (GND *oder* VIN, nicht beide) — sonst Kurzschlussrisiko VBAT→GND.
4. **BTST (C15) gegen VBUS:** darf **keinen** Durchgang zeigen (historischer Bug: BTST lag fälschlich auf VBUS statt LX-bezogen).
5. Bei QFN/LGA-ICs zusätzlich Pin-zu-Pin messen, nicht nur Netz-Ebene.
6. Erster Power-Up nur über USB, ohne Akku — Spannungen (nicht Widerstand) an VBUS, REGN, VSYS, 3V3 prüfen.
7. Erster Akku-Test wenn möglich mit Labornetzteil (3,7–4,2V, Strombegrenzung z.B. 200mA) statt echtem LiPo.

---

## 5. Software-Bring-up-Plan (nächste Schritte)

**Phase 1 — microSD vorbereiten:** Raspberry Pi OS Lite (64-bit), im Imager SSH aktivieren, Hostname setzen (z.B. `mini-musikplayer`), Benutzer/Passwort, WLAN-Zugangsdaten für Erstboot-Test.

**Phase 2 — `config.txt` vor dem Boot anpassen:** siehe Snippet in Abschnitt 3.

**Phase 3 — Erstboot & Erreichbarkeit:** Taster gedrückt halten bzw. EN testweise auf VBAT brücken (Labornetzteil), dann `ping mini-musikplayer.local` und SSH-Login.

**Phase 4 — GPIO16 dauerhaft halten (Soft-Power-Hold):**
- Firmware-seitig: `dtoverlay=gpio,gpiopin=16,op,dh` in `config.txt` (hält schon vor dem Kernel-Start).
- Ergänzend ein systemd-Service, der GPIO16 beim Shutdown sauber auf Low zieht (sonst bleibt die Versorgung nach `poweroff` an).

**Phase 5 — Peripherie einzeln testen:**
- `i2cdetect -y 1` → sollte 0x36 (MAX17048), 0x3E/0x3F (SX1509), 0x6A/0x6B (QMI8658A) zeigen.
- ES8388-Audio: Community-Overlay recherchieren/einbinden (kein Mainline-Support).
- Displays zunächst über Python ansteuern (z.B. `luma.lcd`, `spidev`), nicht über Kernel-Framebuffer/fbtft — schneller zum Laufen zu bringen.
- Debug-UART hat aktuell keinen Header — bei Bedarf nachrüsten.

---

## 6. Bekannte offene Punkte / Diskrepanzen

- **Klinkenbuchse Jack-Detect:** in der Pinout-Doku als "GPIO1 mit 10kΩ-Pull-up" beschrieben, laut aktueller Netzliste aber **nicht verdrahtet** (GPIO1 liegt fest auf GND, Klinkenbuchse hat nur eigenen Pulldown). Muss entschieden werden: nachrüsten oder als Software-Feature streichen.
- **Akku-NTC/JEITA-Temperaturüberwachung:** deaktiviert (Workaround über Festwiderstände R15/R16), da 2-poliger statt 3-poliger Akku-Stecker verbaut ist — bewusste Design-Entscheidung, betrifft ggf. die Lade-Software (kein TS-Feedback verfügbar).
- **ES8388 I2C-Adresse:** noch nicht final gegen die anderen Bus-Teilnehmer verifiziert.
- **RT9466-I2C-Treiber:** muss komplett neu geschrieben werden (Register-Layout ≠ BQ25895).
- **80%-Ladelimit-Logik:** Hardware vorbereitet (RT9466-CEB an GPIO17), Software noch zu schreiben (MAX17048-SOC per I2C pollen, bei Schwelle CEB auf HIGH).
- **UI/Menü-State-Machine** für das Frontdisplay: noch nicht entworfen.
- **Visualizer-Pipeline:** Frames werden vorab per KI-Modell auf einem PC generiert (nicht live auf dem Gerät gerendert), Sync über `frame = int(position_sec * fps)`. Welches Modell/welche Pipeline: noch offen.

---

## 7. Software-/Architektur-Entscheidungen (Kontext für spätere Features)

- **YouTube-Music-Sync:** `ytmusicapi` (Bibliothek durchsuchen, braucht eigene Google-Cloud-OAuth-Client-ID/Secret für Device-Flow) + `yt-dlp` (Audio-Download) + `ffmpeg` (Remuxing). Download nur im Heim-WLAN erlaubt (SSID- und Metered-Check vor dem Sync).
- **Bluetooth A2DP:** läuft komplett über BlueZ + CYW43455 (CM4-internes BT), unabhängig vom ES8388-Codec. Umschaltung Klinke↔BT = reine ALSA-Sink-Wahl, keine Hardware-Umschaltung.
- **Soft-Shutdown:** Power-Taster → GPIO-Interrupt → `systemctl poweroff` → Shutdown-Hook zieht GPIO16 (TPS63020 EN) auf LOW. Wichtig gegen SD-Karten-Korruption — kein hartes Abschalten per Schalter.
- **Orientierungsabhängige UI:** QMI8658A löst Interrupts bei Lageänderung aus (kein Polling nötig) → steuert, welches Display aktiv ist bzw. ob Displays schlafen.

---

## 8. Weitere Projektdokumente (im Anthropic-Projekt hinterlegt)

Falls tiefere Details zu einem Thema gebraucht werden, existieren im Projekt zusätzlich:
- `mini-musikplayer-projektuebersicht.md` — vollständige Projektübersicht (Architektur, BOM, Mechanik, Risiken)
- `claude_mini-musikplayer-pcb-review.md`, `-final-check.md`, `-pcb-sync-check.md`, `-trace-breiten.md`, `-rt9466-btst.md` — PCB-Reviews (Hardware, nicht softwarerelevant)
- `claude_mini-musikplayer-rc-audit.md` — separates RC-Panzer-Projekt, nicht Teil des Musikplayers
- `claude_buttonbox-pcb-review.md` — Review des separaten Tasten-Boards
- `minimusikplayerbom_2.xlsx` — Stückliste mit LCSC-Teilenummern, Preisen, Bestellmengen

---

*Stand dieser Zusammenfassung: 06.09.2026, basierend auf dem aktuellen Projektwissen. Bei Widersprüchen zwischen dieser Datei und einem der Originaldokumente hat das jeweils aktuellste Originaldokument Vorrang.*
