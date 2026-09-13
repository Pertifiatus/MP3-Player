"""WiFi radio control + Bluetooth radio control/pairing, via nmcli/bluetoothctl.

WiFi radio on/off needs root: `nmcli general permissions` on this Pi reports
enable-disable-wifi = "no" for the regular user (not "auth" - NetworkManager
refuses it outright over a headless SSH session, no polkit prompt possible
anyway), so those two calls go through `sudo -n`. Requires a one-time NOPASSWD
sudoers entry for exactly `nmcli radio wifi on`/`off` - see CLAUDE.md.

Bluetooth radio power/scan/pair do NOT need sudo here: the BT adapter's rfkill
soft-block is cleared once at boot by bluetooth-unblock.service (see
CLAUDE.md) instead of being toggled from this module, so plain `bluetoothctl`
works as the regular user for everything below.

Every call shells out to a real system tool and can fail for reasons outside
this code's control (tool missing, D-Bus/BlueZ hiccup, device out of range,
sudoers rule not set up yet) - that's a genuine trust boundary, not a
"can't happen" case, so every function here degrades to a clear return value
(None/False/[] + error string) instead of raising.
"""
import re
import subprocess

_SUDO_TIMEOUT = 5


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(e))


def _short_error(result, fallback):
    text = (result.stderr or result.stdout or "").strip()
    return text.splitlines()[-1] if text else fallback


# --- WiFi ----------------------------------------------------------------

def wifi_is_enabled():
    """True/False, or None if the state couldn't be determined (nmcli missing, etc)."""
    r = _run(["nmcli", "radio", "wifi"])
    return r.stdout.strip() == "enabled" if r.returncode == 0 else None


def wifi_set_enabled(enabled):
    r = _run(["sudo", "-n", "nmcli", "radio", "wifi", "on" if enabled else "off"], timeout=_SUDO_TIMEOUT)
    return r.returncode == 0


def wifi_known_connections():
    """Saved WiFi profiles (nmcli remembers credentials once connected), each
    tagged with whether it's the one currently active - used for the "known
    networks" list in the WLAN menu, same role as bluetooth_known_devices().

    "name" (the nmcli connection profile id, needed for `connection up/down/
    delete`) is NOT reliably the same string as "ssid" (what to show the user,
    and what a fresh scan's SSIDs need to be matched against) - confirmed live
    on this Pi, where cloud-init/netplan names the home WLAN profile
    "netplan-wlan0-TILTEDTOWERS" instead of just "TILTEDTOWERS". Look the real
    SSID up per-profile instead of assuming name == ssid.
    """
    r = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    if r.returncode != 0:
        return []
    names = [name for name, _, ctype in (line.rpartition(":") for line in r.stdout.splitlines())
              if ctype == "802-11-wireless"]
    ra = _run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"])
    active = set(ra.stdout.splitlines()) if ra.returncode == 0 else set()
    result = []
    for name in names:
        rs = _run(["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", name])
        ssid = rs.stdout.strip() if rs.returncode == 0 and rs.stdout.strip() else name
        result.append({"name": name, "ssid": ssid, "connected": name in active})
    return result


def wifi_scan(timeout=15):
    """Nearby SSIDs, strongest signal first. nmcli lists one row per access
    point (BSSID) - the same SSID can show up several times (e.g. mesh/multiple
    APs), so collapse to the strongest signal per SSID."""
    _run(["nmcli", "dev", "wifi", "rescan"], timeout=timeout)
    r = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"], timeout=timeout)
    if r.returncode != 0:
        return []
    best = {}
    for line in r.stdout.splitlines():
        ssid, _, rest = line.partition(":")
        signal_s, _, security = rest.partition(":")
        if not ssid:
            continue
        signal = int(signal_s) if signal_s.isdigit() else 0
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secured": security not in ("", "--")}
    return sorted(best.values(), key=lambda d: -d["signal"])


def wifi_connect(ssid, password=None, timeout=30):
    """Connect to a network not yet known to nmcli (fresh SSID from a scan)."""
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    r = _run(cmd, timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Verbindung fehlgeschlagen")
    return True, None


def wifi_connect_known(name, timeout=20):
    """(Re)connect using an already-saved profile, addressed by its nmcli
    connection NAME (see wifi_known_connections) - not necessarily the SSID."""
    r = _run(["nmcli", "connection", "up", name], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Verbindung fehlgeschlagen")
    return True, None


def wifi_disconnect(name, timeout=10):
    r = _run(["nmcli", "connection", "down", name], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Trennen fehlgeschlagen")
    return True, None


def wifi_forget(name, timeout=10):
    """Forget a saved network entirely (deletes the nmcli connection profile)."""
    r = _run(["nmcli", "connection", "delete", name], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Entfernen fehlgeschlagen")
    return True, None


def wifi_is_metered():
    """True/False, or None if undeterminable. Used to block syncs over a mobile
    hotspot - NetworkManager's own metered flag (auto-detected or user-set via
    `nmcli connection modify ... connection.metered yes`), not a hardcoded SSID,
    so this works for any WLAN the device joins, not just one "home" network."""
    r = _run(["nmcli", "-g", "GENERAL.METERED", "dev", "show", "wlan0"])
    if r.returncode != 0:
        return None
    val = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    if val in ("yes", "metered"):
        return True
    if val in ("no", "not-metered"):
        return False
    return None  # "unknown"/guessed - fail open rather than block sync on ambiguity


# --- Bluetooth: radio power ------------------------------------------------

def bluetooth_is_enabled():
    r = _run(["bluetoothctl", "show"])
    if r.returncode != 0:
        return None
    m = re.search(r"Powered:\s*(yes|no)", r.stdout)
    return m.group(1) == "yes" if m else None


def bluetooth_set_enabled(enabled):
    r = _run(["bluetoothctl", "power", "on" if enabled else "off"], timeout=_SUDO_TIMEOUT)
    return r.returncode == 0


# --- Bluetooth: scan + pair --------------------------------------------------

_DEVICE_LINE = re.compile(r"^Device ([0-9A-Fa-f:]{17})\s+(.*)$", re.MULTILINE)


def _parse_devices(stdout):
    return [{"mac": mac, "name": name.strip()} for mac, name in _DEVICE_LINE.findall(stdout)]


def bluetooth_known_devices():
    """Every device we've paired before, each tagged with whether it's connected
    right now - used for the "known devices" list in the Bluetooth menu.

    Filtered by "Trusted" rather than "Paired": confirmed live that some devices
    (AirPods) have BlueZ flip their own "Paired" property back to false the
    moment they disconnect, even though nothing about the pairing a user cares
    about actually changed - a plain `connect` afterwards still succeeds with no
    re-pairing needed. "Trusted" (set once by bluetooth_pair() right after a
    successful pair) stays true regardless, and is what actually gates BlueZ's
    own auto-reconnect behavior anyway."""
    r = _run(["bluetoothctl", "devices", "Trusted"])
    devices = _parse_devices(r.stdout) if r.returncode == 0 else []
    rc = _run(["bluetoothctl", "devices", "Connected"])
    connected_macs = {mac for mac, _ in _DEVICE_LINE.findall(rc.stdout)} if rc.returncode == 0 else set()
    for d in devices:
        d["connected"] = d["mac"] in connected_macs
    return devices


def bluetooth_connect(mac, timeout=20):
    r = _run(["bluetoothctl", "connect", mac], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Verbindung fehlgeschlagen")
    return True, None


def bluetooth_disconnect(mac, timeout=10):
    r = _run(["bluetoothctl", "disconnect", mac], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Trennen fehlgeschlagen")
    return True, None


def bluetooth_remove(mac, timeout=10):
    """Forget a paired device entirely (unpair)."""
    r = _run(["bluetoothctl", "remove", mac], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Entfernen fehlgeschlagen")
    return True, None


def bluetooth_scan(duration=8):
    """Blocks for `duration` seconds (bluetoothctl's own non-interactive scan
    window) - call from a background thread, never from the render loop.

    Scans BR/EDR (classic Bluetooth) only, not LE: A2DP audio - what every
    Bluetooth headphone/speaker actually uses - is a BR/EDR profile, and
    plain `scan on` covers LE too, which is where most of the unnamed-looking
    "5F-59-21-53..." entries came from live-testing this - BLE peripherals
    (fitness trackers, smart-home sensors, etc.) that only put their MAC/a
    rotating id in their advertisement, not a real name, and were never
    headphones to begin with. Restricting to BR/EDR filters that noise out at
    the radio level instead of guessing which names "look real" in software."""
    _run(["bluetoothctl", "--timeout", str(duration), "scan", "bredr"], timeout=duration + 5)
    r = _run(["bluetoothctl", "devices"])
    devices = _parse_devices(r.stdout) if r.returncode == 0 else []
    known_macs = {d["mac"] for d in bluetooth_known_devices()}
    for d in devices:
        d["paired"] = d["mac"] in known_macs
    return devices


def bluetooth_pair(mac, timeout=20):
    """Pair (if not already known), trust, and connect. Returns (success, error).
    Devices needing a passkey confirmation (rare for headphones - most use
    "Just Works" SSP) can't be answered non-interactively; `timeout` bounds
    that instead of hanging the calling thread forever."""
    known_macs = {d["mac"] for d in bluetooth_known_devices()}
    if mac not in known_macs:
        r = _run(["bluetoothctl", "pair", mac], timeout=timeout)
        if r.returncode != 0:
            return False, _short_error(r, "Pairing fehlgeschlagen")
        _run(["bluetoothctl", "trust", mac], timeout=10)
    r = _run(["bluetoothctl", "connect", mac], timeout=timeout)
    if r.returncode != 0:
        return False, _short_error(r, "Verbindung fehlgeschlagen")
    return True, None


# --- Audio -------------------------------------------------------------------

def set_system_volume(pct):
    """Best-effort ALSA master volume. No real audio pipeline exists yet (see
    CLAUDE.md, ES8388) - this is here so the volume control UI/state is ready
    for when one does, and is a harmless no-op until then (amixer either isn't
    reachable or "Master" doesn't exist on whatever ALSA card ends up in use,
    which `_run`'s degrade-to-False behavior already covers)."""
    r = _run(["amixer", "sset", "Master", f"{max(0, min(100, pct))}%"])
    return r.returncode == 0
