# WLAN aufwecken

## Ziel

Der WLAN-Chip (CYW43455) fällt nach einer gewissen Leerlaufzeit durch NetworkManagers
Powersave komplett vom Netz (bereits live beobachtet, dauerhaft behoben über
`/etc/NetworkManager/conf.d/wifi-powersave-off.conf`, nicht Teil dieser Änderung).
Als Rückfallebene für genau diesen Fall (oder generell "WLAN hängt") soll ein
manueller "WLAN aufwecken"-Knopf im WLAN-Menü existieren, statt das gespeicherte
Passwort neu eingeben zu müssen.

## UI

Neuer Menüpunkt in `wifi_menu_items()` (`ui_state.py`), direkt nach dem
An/Aus-Toggle, vor der Liste bekannter Netzwerke: **"WLAN aufwecken"**.

## Aktion

Läuft im `WifiWorker`-Hintergrund-Thread (wie Scan/Connect/Device-Action) - NICHT
inline im Render-Loop, da `wifi_connect_known()` bis zu 20s blockieren kann
(`connectivity.py`s eigener Timeout):

1. `connectivity.wifi_set_enabled(False)`
2. `connectivity.wifi_set_enabled(True)`
3. Falls mindestens ein bekanntes Netzwerk existiert (`state.wifi_known_networks`):
   `connectivity.wifi_connect_known(name)` auf das erste bekannte Profil (dieses
   Gerät hat in der Praxis genau ein gespeichertes Heim-WLAN, siehe CLAUDE.md -
   keine Mehrfach-Netzwerk-Auswahl nötig, YAGNI). Ohne bekanntes Netzwerk ist
   Schritt 1+2 bereits die gesamte Aktion (Erfolg).

## Feedback

Gleiches Muster wie `render_wifi_device`s "working"/"error"-Zweige: "Aufwecken..."
während die Aktion läuft, Fehlertext falls `wifi_connect_known()` fehlschlägt,
sonst zurück zur normalen Menü-Liste (mit aktualisierter `wifi_known_networks`-Liste).

## Datenfluss (State-Felder, neu in `UIState.__init__`)

- `wifi_wake_status`: `None | "working" | "error"`
- `wifi_wake_error`: Fehlertext oder `None`

## Nicht Teil dieser Änderung

- Der eigentliche Powersave-Fix (NetworkManager-Konfiguration auf dem Gerät) -
  bereits separat live angewendet.
- Auswahl UNTER mehreren bekannten Netzwerken beim Aufwecken - dieses Gerät hat
  nur eines.
