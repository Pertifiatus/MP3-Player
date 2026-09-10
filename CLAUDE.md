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

## 2. Aktueller Stand (08.09.2026)

- **Board 1 ist Geschichte** — nach wiederholtem Nachlöten (Q1-Power-Latch, Hirose-Connector, QMI8658A) hat sich das PCB im zentralen Power-Bereich sichtbar braun verfärbt (thermischer Schaden am FR4-Substrat). Grund war eine Kombination aus zu geringer Temperaturmarge (Wismut-Zinn-Lot, 138°C Schmelzpunkt, Heizplatte nur auf 150°C) und dadurch nötigen langen Verweilzeiten. Board 1 wird nicht weiter repariert.
- **Board 2 ist jetzt das aktive Board.** Bestückt mit denselben Fixes/Erkenntnissen (siehe Abschnitt 3 & "Lessons Learned" unten). **Bootet stabil, Power-Latch-Problem (Q1) ist behoben.**
- **Software ist komplett blank** — frische microSD, frisches Raspberry Pi OS, noch keiner unserer Fixes drauf. Wir fangen beim Software-Bring-up wieder bei **Phase 1** an (Abschnitt 5), aber alle nötigen Fixes sind unten bereits fertig dokumentiert — sollte diesmal schnell gehen.
- **Netzwerk:** IP `192.168.188.108`, Hostname `MP3`, User `pkenner`, gleiche WLAN-Zugangsdaten wie zuvor (SSID "TILTEDTOWERS", per cloud-init `network-config` hinterlegt).
- **SSH-Zugriff:** noch nicht eingerichtet auf der neuen Karte (alter Key `~/.ssh/id_ed25519_mp3player` lokal noch vorhanden, aber nicht mehr auf dem Pi hinterlegt). `ssh_pwauth: true` ist im cloud-init `user-data` gesetzt, Passwort-Login sollte also direkt gehen, bis der Key wieder eingerichtet ist.
- ✅ **R6/R7-Kurzschlussrisiko geprüft (08.09.2026):** Auf Board 2 ist nur R6 bestückt, kein Kurzschluss. Damit war der R6/R7-Verdacht als Ursache für das zweimalige Q1-Durchbrennen auf Board 1 wahrscheinlich **falsch** (bzw. zumindest nicht die alleinige Ursache) — der eigentliche Fix war vermutlich primär die Lötqualität (SAC305 statt SnBi) und/oder die R14-Wertänderung (siehe Abschnitt 6).
- Aktuelle Stromversorgung: Labornetzteil, keine Strombegrenzung aktiv, 5V-Schiene unbelastet stabil.

### Wie Claude Code mit dem Pi arbeitet (Zugriff & Arbeitsweise)

- **SSH per Key, nicht Passwort.** Claude kann keine Passwörter eingeben (Sicherheitsregel) und die Bash-Sitzung ist nicht-interaktiv (kein TTY) — ein Passwort-Prompt würde ohnehin nur hängen bleiben. Setup pro Pi/SD-Karte einmalig:
  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_mp3player -N "" -C "claude-code@mp3player"
  ```
  Danach den Public Key selbst auf den Pi bringen (der Nutzer führt das aus, braucht einmalig das Account-Passwort) — unter `cmd.exe` gibt's kein `ssh-copy-id`:
  ```bash
  type "C:\Users\Per Kenner\.ssh\id_ed25519_mp3player.pub" | ssh pkenner@192.168.188.108 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
  ```
  Danach kann Claude direkt: `ssh -i ~/.ssh/id_ed25519_mp3player pkenner@192.168.188.108 "<befehl>"`.
- **`sudo` mit Passwort kann Claude nicht selbst ausführen** (gleicher Grund: kein TTY, und Passwörter grundsätzlich nicht eingeben). Muster: Claude gibt den fertigen Befehl aus, der Nutzer führt ihn in seinem eigenen Terminal aus und meldet "fertig", danach prüft Claude das Ergebnis per SSH. Ausnahme: `sudo -n reboot` funktioniert auf diesem Image passwortlos (vermutlich eine vorkonfigurierte NOPASSWD-Regel nur für reboot/shutdown) — normale `sudo`-Befehle (apt, systemctl, Dateien in `/etc/` verschieben) brauchen aber das Passwort und damit den Nutzer.
- **Datei-Transfer auf den Pi:** `scp -i ~/.ssh/id_ed25519_mp3player <lokale-datei> pkenner@192.168.188.108:/tmp/` — für systemd-Units o.ä. dann `sudo mv` durch den Nutzer von `/tmp` nach `/etc/systemd/system/`.
- **SD-Karte direkt bearbeiten, solange sie im Kartenleser steckt:** die Boot-Partition (FAT32) erscheint als eigener Laufwerksbuchstabe (zuletzt `G:`) und kann mit den normalen Read/Edit/Write-Tools direkt bearbeitet werden (`config.txt`, `user-data`, `network-config`) — spart eine komplette Boot-Runde gegenüber "erst booten, dann per SSH anpassen". Vorsicht bei `user-data`: enthält den Passwort-Hash des Nutzers, Edits daran können vom Auto-Mode-Classifier als sensibel geblockt werden — dann den Nutzer selbst editieren lassen.
- **Vorsichtig & schrittweise vorgehen:** vor jeder wichtigen Änderung (Config-Edits, `sudo`-Befehle, erst recht Reboots/Poweroffs) kurz erklären und Zustimmung einholen, nicht einfach durchziehen. Explizite Vorgabe aus dieser Session, gilt weiter.

---

## 3. Hardware-Referenz für Software-Arbeit

### CM4-Pinout (GPIO, BCM-Nummerierung)

| Funktion | Pin(s) | Hinweis |
|---|---|---|
| I2C-Hauptbus | GPIO2 (SDA1), GPIO3 (SCL1) | interne Pull-ups vorhanden |
| SPI0 – Front-Display GC9A01 | CE0=GPIO8, MOSI=GPIO10, SCLK=GPIO11 | MISO (GPIO9) frei, da Display write-only |
| SPI4 – Rück-Display SSD1306 | CE0=GPIO4, MOSI=GPIO6, SCLK=GPIO7 | `dtoverlay=spi4-1cs` — **GPIO7 kollidiert mit SPI0-CE1 (Default), zusätzlich `dtoverlay=spi0-1cs,no_miso` nötig** |
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
| QMI8658A INT1 | GPIO0 (ID_SD, Pin 36) | zweckentfremdet — kollidiert potenziell mit HAT-EEPROM-Sondierung, siehe Abschnitt 6 |
| Klinkenbuchse Jack-Detect | GPIO1 (ID_SC, Pin 35) | laut Netzliste aktuell nicht verdrahtet, siehe Abschnitt 6 |
| Power-Taster (Eingang) | GPIO9 | |
| Debug-UART | GPIO14 (TXD0) / GPIO15 (RXD0) | kein Testpad/Header vorhanden |

### `config.txt` — bekannt funktionierender Stand (vor dem ersten Boot eintragen)

```
dtparam=i2c_arm=on
dtparam=i2s=on
dtparam=spi=on
dtoverlay=spi0-1cs,no_miso
dtoverlay=spi4-1cs

force_eeprom_read=0
disable_poe_fan=1
```

**GPIO9-Pull-up NICHT in `config.txt` per `gpio=9=ip,pu` erzwingen** — das greift schon vor dem Kernel/systemd-Start und cuttet dadurch manchmal die Power noch während des Boot-Tastendrucks (siehe GPIO16-Soft-Power-Hold-Abschnitt unten). Stattdessen: Firmware-Default (Pull-Down) für den frühen Boot beibehalten, Pull-up erst per systemd-Service (`gpio9-pullup.service`) **nach** `gpio16-hold.service` setzen — volle Erklärung und fertige Unit unten.

**Wichtig — NICHT `dtoverlay=gpio,gpiopin=16,op,dh` oder `dtoverlay=gpio-hog,gpio=16` für GPIO16 verwenden:**
- `gpio,gpiopin=...` existiert als Overlay in aktueller Firmware (Kernel 6.18) nicht mehr.
- `gpio-hog` funktioniert zum Hochziehen, aber ein Hog lässt sich von Userspace **nie wieder freigeben** — blockiert sauberen Shutdown komplett.
- Stattdessen: GPIO16 komplett aus der `config.txt` raushalten, per systemd + `gpioset` steuern (siehe Phase 4 unten).

**Bekannte Pin-Konflikte durch Default-SPI0-Belegung (GPIO7=CE1, GPIO9=MISO):**
- GPIO7 wird von SPI0-CE1 *und* SPI4-SCLK gebraucht → ohne `spi0-1cs` schlägt `spi4-1cs` mit `pinctrl-bcm2835: pin gpio7 already requested` fehl (kein `/dev/spidev4.0`).
- GPIO9 wird von SPI0-MISO *und* dem Power-Taster gebraucht → `no_miso`-Param bei `spi0-1cs` nötig.
- `dtparam=i2c_arm=on` erzeugt `/dev/i2c-1` nur, wenn zusätzlich das Kernelmodul `i2c-dev` geladen ist:
  ```bash
  sudo modprobe i2c-dev
  echo "i2c-dev" | sudo tee /etc/modules-load.d/i2c-dev.conf
  ```

### I2C-Bus-Belegung

| Gerät | Adresse |
|---|---|
| MAX17048 (Fuel Gauge) | 0x36 |
| RT9466 (USB-C-Charger) | 0x53 |
| SX1509 (GPIO-Expander, Tasten/LEDs) | erwartet **0x3E** (ADDR0+ADDR1 laut ButtonBox-Netzliste beide auf GND), nach dem Verlöten per `i2cdetect` bestätigen — auf Board 1 nie bestückt |
| QMI8658A (IMU) | SA0 fest auf 3V3 verdrahtet → erwartet 0x6B, antwortet auf Board 2 aber tatsächlich auf **0x6A** (verifiziert 08.09.2026, siehe Abschnitt 7) — auf Board 1 nie erkannt |
| ES8388 (Audio-Codec) | Datenblatt prüfen — nicht final verifiziert |

### GPIO16 Soft-Power-Hold — fertige Lösung (systemd + gpioset)

Zwei Units, `libgpiod` v2 (`gpioset`) nutzt standardmäßig `pinctrl-bcm2835`s "GPIO_OUT persistence" — der Pegel bleibt auch nach Prozessende erhalten, kein `--mode=wait` nötig. **Wichtig:** `gpioset` braucht `-c <chip>` als Flag, nicht positional (`gpioset -c gpiochip0 16=1`, nicht `gpioset gpiochip0 16=1`).

`/etc/systemd/system/gpio16-hold.service`:
```ini
[Unit]
Description=Hold GPIO16 high while running (TPS63020 EN latch)
DefaultDependencies=no
After=local-fs.target
Before=basic.target shutdown.target
Conflicts=shutdown.target

[Service]
ExecStart=/usr/bin/gpioset -C gpio16-hold -c gpiochip0 16=1
Restart=no

[Install]
WantedBy=sysinit.target
```

`/etc/systemd/system/gpio16-poweroff.service`:
```ini
[Unit]
Description=Drive GPIO16 low to cut power (TPS63020 EN release) on poweroff/halt
DefaultDependencies=no
After=gpio16-hold.service
Before=poweroff.target halt.target

[Service]
Type=oneshot
ExecStart=/usr/bin/gpioset -c gpiochip0 16=0

[Install]
WantedBy=poweroff.target halt.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gpio16-hold.service
sudo systemctl enable gpio16-poweroff.service
```

**Wichtiger Design-Hinweis (`DefaultDependencies=no` + `Before=basic.target`):** ohne das entsteht ein Ordering-Zyklus mit `basic.target` (systemd verwirft den Start-Job stillschweigend, GPIO16 bleibt Input). Das `After=gpio16-hold.service` auf der Poweroff-Unit sorgt dafür, dass der Hold-Service die Leitung erst freigibt, bevor die Poweroff-Unit sie zum Low-Ziehen belegt (sonst `EBUSY`).

✅ **Ende-zu-Ende auf Board 2 verifiziert (09.09.2026):**
1. `systemctl status gpio16-hold.service` → `active`, `gpioinfo | grep gpio16` → `output consumer="gpio16-hold"`. ✅
2. Reboot-Test bestanden — Hold-Service startet sauber beim Kaltstart, kein Ordering-Zyklus. ✅
3. `sudo poweroff` → Verbrauch sinkt auf ~0,1A (vorher, vor dem unten beschriebenen Fix: hing bei 0,3A fest). Die verbleibenden ~0,1A sind erwarteter Ruhestrom von MAX17048 (Fuel Gauge) und RT9466 (Charger) — beide hängen laut Netzliste direkt an VBAT, nicht hinter dem TPS63020/EN-Schalter, und müssen auch im "Aus"-Zustand für Akku-Überwachung/Laden weiterlaufen. Kein Fehler, By-Design. ✅

**Vorgeschichte / echter Bug, jetzt behoben:** Nach `poweroff` sank der Verbrauch zunächst nur auf 0,3A statt der erwarteten ~0,1A, und zwar reproduzierbar sogar **ganz ohne SD-Karte** bei nur kurzem Tasterdruck (kein Linux/keine Software beteiligt) — klarer Hinweis auf einen Hardware-Selbsthalt. Root Cause: Q1 (P-MOSFET, Source=VBAT, Drain=EN-Netz, siehe Netzliste) wird beim Tasterdruck über Diode D1 vom Power-Taster-Knoten (GPIO9 / RT9466 `#QON`) durchgeschaltet und soll nach Loslassen über R13 (100kΩ Gate-Pullup zu VBAT) wieder sperren. GPIO9 stand aber per Firmware-Default auf **internem Pull-Down**, während nur ein vergleichsweise schwacher interner Pull-up im RT9466 dagegenhielt — der Knoten las digital zwar "HIGH", lag aber nicht sauber auf VBAT-Pegel, genug um über D1 minimal Gate-Strom aus Q1 abzuziehen und ihn nie ganz zu sperren. Bestätigt durch: **Stecken des CM4 ab → Verbrauch geht sofort auf 0** (der Pull-Down existiert nur mit gestecktem CM4). **Erster Fix-Versuch (`gpio=9=ip,pu` in `config.txt`) hatte einen Nebeneffekt:** Diese Firmware-Boot-Direktive greift schon vor dem Kernel/systemd-Start — der Taster musste danach wieder die volle Zeit gehalten werden (korrektes, ursprünglich dokumentiertes Verhalten, kein Rückschritt), aber gelegentlich cuttete der jetzt schon früh aktive Pull-up die Power noch während des Boot-Tastendrucks, bevor `gpio16-hold.service` überhaupt laufen konnte (der parasitäre Pull-Down hatte vorher unbeabsichtigt als Zeitpuffer fürs Hochfahren gedient).

✅ **Finaler Fix (09.09.2026), mehrfach verifiziert — Boot UND Shutdown funktionieren beide sauber:** `gpio=9=ip,pu` wieder aus `config.txt` entfernt (Firmware-Default Pull-Down bleibt für den frühen Boot bestehen, gibt dem Tasterdruck wieder die gewohnte Toleranz). Stattdessen ein zweiter systemd-Service, der den Pull-up erst **nach** `gpio16-hold.service` per `pinctrl` setzt — zu dem Zeitpunkt läuft Software schon zuverlässig, Q1 kann also gefahrlos hart gesperrt werden, ohne den Boot zu gefährden.

`/etc/systemd/system/gpio9-pullup.service`:
```ini
[Unit]
Description=Switch GPIO9 (power button node) to internal pull-up after GPIO16 hold is active
After=gpio16-hold.service
Requires=gpio16-hold.service

[Service]
Type=oneshot
ExecStart=/usr/bin/pinctrl set 9 ip pu
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable gpio9-pullup.service
```

### Displays per Python (SPI, kein Kernel-Framebuffer)

```bash
sudo apt install -y python3-pip python3-pil python3-numpy
pip3 install --break-system-packages luma.lcd luma.oled
pip3 install --break-system-packages adafruit-circuitpython-gc9a01a adafruit-blinka adafruit-blinka-displayio
```

- **Rück-Display (SSD1306, SPI4):** `luma.oled` deckt SSD1306 direkt ab. ✅ **Auf Board 2 visuell verifiziert (09.09.2026):** Vollbild-Weiß-Test läuft sauber. Panel blieb zunächst komplett schwarz trotz vollständig korrekter Verkabelung (RST/DC/CS/VCC/GND/SCLK alle sauber, Pin-Reihenfolge gegen Netzliste abgeglichen, Controller-Identität als echtes SSD1306 verifiziert, Modul auf einem unabhängigen ESP32-C3 erfolgreich getestet). Root Cause fand sich erst beim gezielten Test auf LOW (nicht nur HIGH!): MOSI/GPIO6 blieb bei aktivem LOW-Kommando trotzdem bei 3,3V hängen — klassisches Symptom einer unterbrochenen Leitung mit Pull-Up auf der Gegenseite (viele China-SSD1306-Module behalten den I2C-Pull-Up auch im SPI-Modus). Kein Kurzschluss zu VCC, GPIO16 oder sonst einem Nachbarpin (alles per Multimeter bei abgeschaltetem Strom ausgeschlossen) — reine kalte Lötstelle am GPIO6-Pin des Steckverbinders, durch Nachlöten behoben. Zusätzlich zeigte RST kurzzeitig eine instabile Spannung (0,7V→100mV) unter LOW-Last, ebenfalls durch Nachlöten am selben Steckverbinder mitbehoben. **Lesson (gilt für beide Displays jetzt):** Ein Pin-Test, der nur einen einzigen Zielwert (z.B. nur HIGH) gegen alle Leitungen gleichzeitig prüft, kann eine unterbrochene Leitung mit Pull-Up/Pull-Down auf der Gegenseite nicht erkennen — IMMER zusätzlich auf den jeweils anderen Pegel (LOW) testen, das deckt genau diese Fehlerklasse auf.

**Nachtrag (09.09.2026):** Nach dem oben beschriebenen Fix ist das Display noch **zweimal erneut komplett ausgefallen** (einmal MOSI wieder bei 3,3V hängend — durch bloßen Reboot ohne Löten von selbst wieder verschwunden, vermutlich Software-Ressourcenkonflikt durch gleichzeitiges Ausführen beider Display-Skripte, siehe Lesson unten; einmal RST komplett unresponsive konstant bei 1,2V unabhängig vom Kommando — durch erneutes Nachlöten behoben). **Wackelkontakte an den direkt angelöteten Kabeln (kein Steckverbinder, siehe Abschnitt 6 Hirose-Lesson für die generelle Wackel-Problematik dieses Boards) sind bei diesem Board offenbar ein wiederkehrendes Muster**, nicht nur ein einmaliger Fehler — bei zukünftigen erneuten Blackouts zuerst RST/MOSI/SCLK auf Wackelkontakt prüfen (Drucktest), bevor an der Software gesucht wird. Nach dem zweiten Nachlöten mehrfach (Vollbild-Weiß-Test + RST-HIGH/LOW-Test) verifiziert, aktuell stabil.

**Software-Lesson:** Beide Display-Skripte (Front SPI0 + Rück SPI4) **gleichzeitig** laufen zu lassen führte einmal zu unerklärlichen Fehlmessungen (MOSI schien kurzzeitig kaputt, war nach Reboot aber wieder einwandfrei) — vermutlich ein GPIO/Blinka-Ressourcenkonflikt zwischen den beiden Prozessen. Für Tests: Skripte nacheinander laufen lassen, nicht parallel.
- **Front-Display (GC9A01, SPI0):** `luma.lcd` hat **kein** GC9A01-Device — stattdessen `adafruit-circuitpython-gc9a01a` (Paketname mit "a" am Ende!) nutzen. Braucht zusätzlich `adafruit-blinka-displayio` für das `busdisplay`-Modul (kommt nicht automatisch mit).
- Die neue `displayio`-API von `adafruit_gc9a01a` nutzt **kein** `.image()` mehr (alte luma-Semantik) — stattdessen `fourwire.FourWire(spi, command=.., chip_select=.., reset=..)` als Bus, dann `displayio.Group`/`Bitmap`/`Palette`/`TileGrid` und `display.root_group = group`.
- Funktionierendes Minimalbeispiel (roter Vollbild-Test) lag in `/tmp/test_front_display.py` auf Board 1 — Muster:
  ```python
  import board, fourwire, displayio, adafruit_gc9a01a
  displayio.release_displays()
  spi = board.SPI()
  display_bus = fourwire.FourWire(spi, command=board.D24, chip_select=board.CE0, reset=board.D25, baudrate=24000000)
  display = adafruit_gc9a01a.GC9A01A(display_bus, width=240, height=240)
  splash = displayio.Group()
  bitmap = displayio.Bitmap(240, 240, 1)
  palette = displayio.Palette(1); palette[0] = 0xFF0000
  splash.append(displayio.TileGrid(bitmap, pixel_shader=palette))
  display.root_group = splash
  ```
  ✅ **Auf Board 2 visuell verifiziert (09.09.2026):** Vollbild-Rot-Test läuft sauber bei 24MHz (Standard-Baudrate aus dem Beispiel oben). Auf dem Weg dahin gab es einen echten Hardware-Fehler: Panel blieb komplett schwarz (Backlight leuchtete normal, da eigener unabhängiger Stromkreis). Durchgemessen wurden nacheinander RST/DC/CS/VCC/GND/MOSI (alle sauber 3,3V) und SCLK (instabil ~0,3V statt 3,3V) — kalte Lötstelle an SCLK, per Drucktest bestätigt (Spannung stabilisierte sich bei mechanischem Druck auf die Platine). Nach Nachlöten der SCLK-Stelle funktioniert das Display einwandfrei, auch bei voller 24MHz-Baudrate. **Lesson:** bei "Backlight an, Panel schwarz" zuerst SCLK-Kontinuität prüfen, nicht Software/Treiber verdächtigen — RST/DC/CS/VCC/GND/MOSI waren alle in Ordnung.

### Wichtige Bauteile & Eigenheiten

- **RT9466GQW** (USB-C-Charger, ersetzt BQ25895) — Registeradressen weichen vom BQ25895 ab, eigener I2C-Treiber nötig, kein Copy-Paste möglich.
- **TPS63020** (Buck-Boost) — Power-Good-Pin für Debugging verfügbar, EN-Pin = Soft-Shutdown-Schalter (GPIO16).
- **MAX17048** (Fuel Gauge) — ALRT-Pin für Low-Battery-Shutdown, SOC per I2C auslesbar (für 80%-Ladelimit).
- **ES8388** (Audio-Codec, ersetzt WM8960) — **kein offizieller Mainline-Kernel-Treiber**, Community-Overlay nötig; größter Software-Mehraufwand im Projekt.
- **QMI8658A** (IMU) — kein Kernel-Overlay, wird direkt per I2C/`smbus` angesprochen.
- **SX1509** (I2C-GPIO-Expander für Tasten/LEDs) — Hardware-Debouncing, PWM-LED-Treiber integriert. **Keine brauchbare CircuitPython/Blinka-Bibliothek verfügbar** (nur 1-8-Sterne-Hobby-Repos) — Treiber ist rohe I2C-Registeransteuerung per `smbus2`, siehe [Software/buttonbox.py](Software/buttonbox.py). Pin-Layout laut `KiCad/Projekt 1/ButtonBox/ButtonBox.net`: I/O0=Encoder A, I/O1=Encoder B, I/O2=Encoder-Klick, I/O3=Play/Pause, I/O4=Shuffle, I/O5=Stop (alle active-low, interne Pull-ups). I/O7-I/O14 liegen an einem 8-Pin-Reserve-Stecker (J7), noch nicht belegt. **NINT/NRESET sind nicht zum Pi durchverbunden** — Buttons/Encoder müssen gepollt werden, kein Interrupt verfügbar.
  ✅ **Auf Board 2 / ButtonBox verifiziert (09.09.2026):** I2C-Adresse exakt wie vorhergesagt auf **0x3E** (per `i2cdetect`). Play/Pause, Shuffle und Stop liefern über `buttonbox.py` saubere `button_down`/`button_up`-Events ohne Prellen (Kontakte manuell überbrückt, Taster noch nicht verlötet). Rotary Encoder noch nicht getestet (noch nicht angeschlossen) — Pinout des 5-Pin-Steckers (J3): Pin1=Encoder A, Pin2=Encoder B, Pin3=Encoder-Klick, Pin4=VCC, Pin5=GND.
  ⚠️ **LEDs (SK6812) leuchten weiß ohne Ansteuerung** — erwartetes Verhalten bei offener/unangesteuerter DIN-Leitung (Single-Wire-Protokoll interpretiert Rauschen meist als "alle Bits high"), kein Fehler. Verschwindet sobald die Haupt-PCB-LEDs verlötet sind und GPIO12 die Kette aktiv ansteuert.

---

## 4. Vor dem Akku-Anschluss: Kontinuitätsprüfung (Checkliste)

Vor jedem ersten Akku-Anschluss an ein gefertigtes Board (bei abgestecktem USB, ohne Akku, Multimeter im Diodenmodus):

1. Optische Kontrolle der QFN-Gehäuse (RT9466, TPS63020, ES8388, SX1509) auf Lötbrücken.
2. Durchgangsmessung gegen GND: VBUS, VSYS, VBAT/VINA, 3V3, REGN, LX.
3. ✅ **PS/SYNC (R6/R7) — auf Board 2 geprüft (08.09.2026):** nur R6 bestückt, kein Kurzschluss. Darf nur in **einer** Richtung Durchgang zeigen (GND *oder* VIN, nicht beide) — bei zukünftigen Boards weiter so prüfen.
4. **BTST (C15) gegen VBUS:** darf **keinen** Durchgang zeigen (historischer Bug: BTST lag fälschlich auf VBUS statt LX-bezogen).
5. Bei QFN/LGA-ICs zusätzlich Pin-zu-Pin messen, nicht nur Netz-Ebene.
6. Erster Power-Up nur über USB, ohne Akku — Spannungen (nicht Widerstand) an VBUS, REGN, VSYS, 3V3 prüfen.
7. Erster Akku-Test wenn möglich mit Labornetzteil (3,7–4,2V) statt echtem LiPo.

---

## 5. Software-Bring-up-Plan (Board 2, bei null anfangen)

**Phase 1 — microSD vorbereiten:** Raspberry Pi OS Lite (64-bit) per Imager, OS-Customisation aktivieren: Hostname `MP3`, User `pkenner`, SSH aktivieren (Passwort-Auth reicht fürs Erste), WLAN "TILTEDTOWERS".

**Phase 2 — `config.txt` vor dem Boot anpassen:** Snippet aus Abschnitt 3 direkt in `config.txt` auf der Boot-Partition eintragen, bevor die Karte das erste Mal steckt — spart eine Boot-Runde.

**Phase 3 — Erstboot & Erreichbarkeit:** Taster **mindestens 20-30 Sekunden gedrückt halten** (kein Selbsthalte-Mechanismus in der Schaltung — Software muss GPIO16 erst hochfahren und übernehmen, bevor losgelassen werden darf!), dann `ping MP3.local` bzw. `192.168.188.108`, SSH-Login.

**Phase 4 — GPIO16 Soft-Power-Hold:** fertige Lösung + offene Verifikation, siehe Abschnitt 3.

**Phase 5 — Peripherie einzeln testen:**
- `sudo modprobe i2c-dev` + persistieren, dann `i2cdetect -y 1` → sollte 0x36 (MAX17048), 0x53 (RT9466), 0x3E/0x3F (SX1509, falls bestückt), 0x6A (QMI8658A, siehe Abschnitt 7 zur 0x6A/0x6B-Diskrepanz) zeigen.
- Displays per Python testen (Abschnitt 3) — dieses Mal auch **visuell verifizieren**, nicht nur "Skript läuft ohne Fehler".
- ES8388-Audio: Community-Overlay recherchieren/einbinden (kein Mainline-Support) — noch nicht begonnen.
- Debug-UART hat aktuell keinen Header — bei Bedarf nachrüsten.

---

## 6. Lessons Learned (Board 1 → Board 2)

Kompakt, damit die Fehler sich nicht wiederholen — Details der Fehlersuche selbst sind nicht mehr relevant:

- **Hirose-Mezzanine-Connector ist der Wackelkandidat des Projekts.** Mehrfach Ursache für scheinbar unabhängige Fehler (Bootprobleme, kompletter I2C-Ausfall). Nach jedem Ab-/Aufstecken des CM4-Moduls fest andrücken; bei mysteriösen, sonst unerklärlichen Ausfällen **zuerst hier prüfen**, bevor an Einzelbauteilen gelötet wird.
- **Lötzinn-Wahl ist kritisch für den Power-Bereich und Steckverbinder.** Wismut-Zinn-Lot (SnBi, ~138°C Schmelzpunkt) ist spröder als SAC305 und hat wenig thermische Reserve zu sich selbst erwärmenden Bauteilen (Charger, Buck-Boost) — ungeeignet für Q1/TPS63020/RT9466-Umgebung und den Hirose-/USB-C-Connector (mechanisch belastet). Für diese Bereiche **SAC305 (~217°C)** verwenden. Bei SnBi: Heizplatte mit ausreichend Marge (170–180°C, nicht nur 12°C über Schmelzpunkt) und Zeit oberhalb Schmelzpunkt auf 30–60s begrenzen, sonst PCB-Verfärbung/Substratschädigung (genau das ist Board 1 passiert). Zwischen Reflow-Durchgängen min. 10-15 Min. vollständig abkühlen lassen, max. 2-3 Durchgänge pro Bauteil/Board.
- **R12/R14 (GPIO16 → EN-Netz) waren mit 220Ω/100kΩ zu unausgewogen:** Der interne SoC-Pull-up an GPIO16 konnte über R12 genug ins EN-Netz durchsickern, um TPS63020 auch ganz ohne aktive Software knapp über der Einschaltschwelle zu halten. **Fix: R14 von 100kΩ auf 5,1kΩ** (R12 bei 220Ω belassen) — sauber unter Schwelle im unkonfigurierten Zustand, sicher über Schwelle bei aktiv getriebenem GPIO16.
- **R6/R7-Kurzschluss war der Hauptverdacht fürs zweimalige Durchbrennen von Q1** auf Board 1, hat sich auf Board 2 aber **nicht bestätigt** (nur R6 bestückt, kein Kurzschluss) — die tatsächliche Ursache war vermutlich die Lötqualität (SnBi/PCB-Verfärbung) statt eines Verdrahtungsfehlers.

---

## 7. Bekannte offene Punkte / Diskrepanzen

- ✅ **QMI8658A (IMU) — auf Board 2 verifiziert (08.09.2026):** Auf Board 1 nie im I2C-Scan erschienen (0x6B erwartet), trotz mehrfachem Reflow. Auf Board 2 antwortet der Chip jedoch zuverlässig — allerdings auf **0x6A statt der dokumentierten 0x6B**. WHO_AM_I-Register (0x00) liefert exakt `0x05` (Datenblatt-Sollwert), und nach korrektem Init (CTRL1=0x60 Adress-Auto-Increment, CTRL2=0x26 Accel ±8g/125Hz, CTRL3=0x56 Gyro ±512dps/125Hz, CTRL7=0x03 Accel+Gyro enable) liefert er plausible Live-Werte: Accel X:0,05g Y:0,05g Z:1,02g (Betrag ≈1g, Board lag ruhig — passt zur Schwerkraft), Temp 30,5°C, Gyro-Achsen nahe 0 (unkalibrierter Offset von ~20-40dps ist normal ohne Zero-Rate-Kalibrierung). Damit ist klar: Bauteil/Footprint sind nicht das Problem, der Board-1-Ausfall lag vermutlich am Löten. **Diskrepanz 0x6A statt 0x6B bleibt ungeklärt** (würde auf SA0=GND statt SA0=3V3 hindeuten, im Widerspruch zur Netzliste) — für die spätere Treiber-Implementierung einfach 0x6A verwenden, SA0-Pin-Spannung noch nicht per Multimeter nachgemessen.
- **Klinkenbuchse Jack-Detect:** in der Pinout-Doku als "GPIO1 mit 10kΩ-Pull-up" beschrieben, laut Netzliste aber **nicht verdrahtet** (GPIO1 liegt fest auf GND). Muss entschieden werden: nachrüsten oder als Software-Feature streichen.
- **QMI8658A INT1 auf GPIO0 (ID_SD):** GPIO0/1 sind eigentlich für HAT-EEPROM-Erkennung reserviert. `force_eeprom_read=0` unterdrückt das meiste, aber ein Teil der Sondierung passiert schon vor dem Lesen der `config.txt` — möglicher Interferenz-Kandidat für Boot-Flakiness (u.a. die wiederholten WLAN-Verbindungsprobleme, siehe Abschnitt 2 der Vorgängerversion). Nicht abschließend geklärt.
- **Akku-NTC/JEITA-Temperaturüberwachung:** deaktiviert (Workaround über Festwiderstände R15/R16), da 2-poliger statt 3-poliger Akku-Stecker verbaut ist — bewusste Design-Entscheidung, betrifft ggf. die Lade-Software (kein TS-Feedback verfügbar).
- **ES8388 I2C-Adresse:** noch nicht final verifiziert.
- **RT9466-I2C-Treiber:** muss komplett neu geschrieben werden (Register-Layout ≠ BQ25895).
- **80%-Ladelimit-Logik:** Hardware vorbereitet (RT9466-CEB an GPIO17), Software noch zu schreiben (MAX17048-SOC per I2C pollen, bei Schwelle CEB auf HIGH).
- **UI/Menü-State-Machine** für das Frontdisplay: noch nicht entworfen.
- **Visualizer-Pipeline:** Frames werden vorab per KI-Modell auf einem PC generiert (nicht live auf dem Gerät gerendert), Sync über `frame = int(position_sec * fps)`. Welches Modell/welche Pipeline: noch offen.

---

## 8. Software-/Architektur-Entscheidungen (Kontext für spätere Features)

- **YouTube-Music-Sync:** `ytmusicapi` (Bibliothek durchsuchen, braucht eigene Google-Cloud-OAuth-Client-ID/Secret für Device-Flow) + `yt-dlp` (Audio-Download) + `ffmpeg` (Remuxing). Download nur im Heim-WLAN erlaubt (SSID- und Metered-Check vor dem Sync).
- **Bluetooth A2DP:** läuft komplett über BlueZ + CYW43455 (CM4-internes BT), unabhängig vom ES8388-Codec. Umschaltung Klinke↔BT = reine ALSA-Sink-Wahl, keine Hardware-Umschaltung.
- **Soft-Shutdown:** Power-Taster → GPIO-Interrupt → `systemctl poweroff` → Shutdown-Hook zieht GPIO16 (TPS63020 EN) auf LOW. Wichtig gegen SD-Karten-Korruption — kein hartes Abschalten per Schalter.
- **Orientierungsabhängige UI:** QMI8658A löst Interrupts bei Lageänderung aus (kein Polling nötig) → steuert, welches Display aktiv ist bzw. ob Displays schlafen.

---

## 9. Weitere Projektdokumente (im Anthropic-Projekt hinterlegt)

Falls tiefere Details zu einem Thema gebraucht werden, existieren im Projekt zusätzlich:
- `mini-musikplayer-projektuebersicht.md` — vollständige Projektübersicht (Architektur, BOM, Mechanik, Risiken)
- `claude_mini-musikplayer-pcb-review.md`, `-final-check.md`, `-pcb-sync-check.md`, `-trace-breiten.md`, `-rt9466-btst.md` — PCB-Reviews (Hardware, nicht softwarerelevant)
- `claude_mini-musikplayer-rc-audit.md` — separates RC-Panzer-Projekt, nicht Teil des Musikplayers
- `claude_buttonbox-pcb-review.md` — Review des separaten Tasten-Boards
- `minimusikplayerbom_2.xlsx` — Stückliste mit LCSC-Teilenummern, Preisen, Bestellmengen

---

*Stand dieser Zusammenfassung: 08.09.2026. Bei Widersprüchen zwischen dieser Datei und einem der Originaldokumente hat das jeweils aktuellste Originaldokument Vorrang.*
