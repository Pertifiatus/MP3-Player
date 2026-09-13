"""Pure-logic tests for connectivity.py's output parsing - no hardware needed.
Mocks subprocess.run so this runs on any machine, unlike the actual nmcli/
bluetoothctl calls which only work on the real Pi.

python3 test_connectivity.py
"""
import subprocess

import connectivity


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_wifi_is_enabled_parses_nmcli_output():
    subprocess.run = lambda *a, **k: _FakeResult(stdout="enabled\n")
    assert connectivity.wifi_is_enabled() is True
    subprocess.run = lambda *a, **k: _FakeResult(stdout="disabled\n")
    assert connectivity.wifi_is_enabled() is False


def test_wifi_is_enabled_returns_none_on_failure():
    subprocess.run = lambda *a, **k: _FakeResult(returncode=1, stderr="nmcli not found")
    assert connectivity.wifi_is_enabled() is None


def test_bluetooth_is_enabled_parses_show_output():
    show_on = "Controller AA:BB\n\tName: MP3\n\tPowered: yes\n\tDiscoverable: no\n"
    subprocess.run = lambda *a, **k: _FakeResult(stdout=show_on)
    assert connectivity.bluetooth_is_enabled() is True

    show_off = "Controller AA:BB\n\tName: MP3\n\tPowered: no\n"
    subprocess.run = lambda *a, **k: _FakeResult(stdout=show_off)
    assert connectivity.bluetooth_is_enabled() is False


def test_parse_devices_extracts_mac_and_name():
    stdout = (
        "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\n"
        "Device 11:22:33:44:55:66 JBL Flip 5\n"
    )
    devices = connectivity._parse_devices(stdout)
    assert devices == [
        {"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4"},
        {"mac": "11:22:33:44:55:66", "name": "JBL Flip 5"},
    ]


def test_parse_devices_handles_empty_output():
    assert connectivity._parse_devices("") == []


def test_bluetooth_scan_marks_known_devices():
    scan_stdout = (
        "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\n"
        "Device 11:22:33:44:55:66 JBL Flip 5\n"
    )
    trusted_stdout = "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\n"

    def fake_run(cmd, **kwargs):
        if "devices" in cmd and "Trusted" in cmd:
            return _FakeResult(stdout=trusted_stdout)
        if "devices" in cmd:
            return _FakeResult(stdout=scan_stdout)
        return _FakeResult(stdout="")  # the scan-on call itself

    subprocess.run = fake_run
    devices = connectivity.bluetooth_scan(duration=1)
    by_mac = {d["mac"]: d["paired"] for d in devices}
    assert by_mac == {"AA:BB:CC:DD:EE:FF": True, "11:22:33:44:55:66": False}


def test_bluetooth_pair_skips_pair_step_if_already_known():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "devices" in cmd:
            return _FakeResult(stdout="Device AA:BB:CC:DD:EE:FF Sony\n")
        return _FakeResult(returncode=0)

    subprocess.run = fake_run
    success, error = connectivity.bluetooth_pair("AA:BB:CC:DD:EE:FF")
    assert success and error is None
    assert not any("pair" == c[1] for c in calls if len(c) > 1)
    assert any("connect" in c for c in calls)


def test_bluetooth_known_devices_marks_connected():
    trusted_stdout = (
        "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\n"
        "Device 11:22:33:44:55:66 JBL Flip 5\n"
    )
    connected_stdout = "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\n"

    def fake_run(cmd, **kwargs):
        if "Connected" in cmd:
            return _FakeResult(stdout=connected_stdout)
        return _FakeResult(stdout=trusted_stdout)

    subprocess.run = fake_run
    devices = connectivity.bluetooth_known_devices()
    by_mac = {d["mac"]: d["connected"] for d in devices}
    assert by_mac == {"AA:BB:CC:DD:EE:FF": True, "11:22:33:44:55:66": False}


def test_bluetooth_known_devices_survives_bluez_dropping_paired_flag():
    # Regression guard: confirmed live that BlueZ flips a device's own "Paired"
    # property back to false the moment it disconnects (AirPods specifically),
    # even though the device is still trusted and reconnects fine with a plain
    # `connect` - no re-pairing needed. Querying by "Paired" would silently drop
    # such a device from the known-devices list the instant it disconnects.
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert "Paired" not in cmd, "must not filter by the flaky Paired property"
        if "Trusted" in cmd:
            return _FakeResult(stdout="Device 18:3F:70:5C:C6:3F AirPods Pro\n")
        return _FakeResult(stdout="")  # Connected - nothing connected right now

    subprocess.run = fake_run
    devices = connectivity.bluetooth_known_devices()
    assert devices == [{"mac": "18:3F:70:5C:C6:3F", "name": "AirPods Pro", "connected": False}]


def test_bluetooth_connect_disconnect_remove_report_success_and_failure():
    subprocess.run = lambda *a, **k: _FakeResult(returncode=0)
    assert connectivity.bluetooth_connect("AA:BB:CC:DD:EE:FF") == (True, None)
    assert connectivity.bluetooth_disconnect("AA:BB:CC:DD:EE:FF") == (True, None)
    assert connectivity.bluetooth_remove("AA:BB:CC:DD:EE:FF") == (True, None)

    subprocess.run = lambda *a, **k: _FakeResult(returncode=1, stderr="Failed: org.bluez.Error.Failed")
    success, error = connectivity.bluetooth_connect("AA:BB:CC:DD:EE:FF")
    assert not success and "Failed" in error


def test_bluetooth_pair_reports_error_on_failure():
    def fake_run(cmd, **kwargs):
        if "devices" in cmd:
            return _FakeResult(stdout="")  # not yet paired
        if "pair" in cmd:
            return _FakeResult(returncode=1, stderr="Failed to pair: org.bluez.Error.AuthenticationFailed")
        return _FakeResult(returncode=0)

    subprocess.run = fake_run
    success, error = connectivity.bluetooth_pair("AA:BB:CC:DD:EE:FF")
    assert not success
    assert "AuthenticationFailed" in error


def test_wifi_known_connections_filters_to_wireless_and_marks_active():
    show_stdout = "Heimnetz:802-11-wireless\nEth0 Wired:802-3-ethernet\nCafe WLAN:802-11-wireless\n"
    active_stdout = "Heimnetz\n"

    def fake_run(cmd, **kwargs):
        if "--active" in cmd:
            return _FakeResult(stdout=active_stdout)
        if "802-11-wireless.ssid" in cmd:
            return _FakeResult(stdout="")  # ssid lookup fails -> falls back to the profile name
        return _FakeResult(stdout=show_stdout)

    subprocess.run = fake_run
    networks = connectivity.wifi_known_connections()
    by_ssid = {n["ssid"]: n["connected"] for n in networks}
    assert by_ssid == {"Heimnetz": True, "Cafe WLAN": False}


def test_wifi_known_connections_uses_real_ssid_when_profile_name_differs():
    # e.g. this project's own cloud-init/netplan setup names the profile
    # "netplan-wlan0-TILTEDTOWERS" while the actual SSID is "TILTEDTOWERS" -
    # confirmed live on the Pi, see connectivity.wifi_known_connections docstring.
    show_stdout = "netplan-wlan0-TILTEDTOWERS:802-11-wireless\n"

    def fake_run(cmd, **kwargs):
        if "--active" in cmd:
            return _FakeResult(stdout="netplan-wlan0-TILTEDTOWERS\n")
        if "802-11-wireless.ssid" in cmd:
            return _FakeResult(stdout="TILTEDTOWERS\n")
        return _FakeResult(stdout=show_stdout)

    subprocess.run = fake_run
    networks = connectivity.wifi_known_connections()
    assert networks == [{"name": "netplan-wlan0-TILTEDTOWERS", "ssid": "TILTEDTOWERS", "connected": True}]


def test_wifi_scan_collapses_duplicate_ssids_to_strongest_signal():
    stdout = (
        "Heimnetz:40:WPA2\n"
        "Heimnetz:75:WPA2\n"
        "Open Cafe:60:\n"
    )
    subprocess.run = lambda *a, **k: _FakeResult(stdout=stdout)
    networks = connectivity.wifi_scan()
    assert networks[0] == {"ssid": "Heimnetz", "signal": 75, "secured": True}
    assert networks[1] == {"ssid": "Open Cafe", "signal": 60, "secured": False}


def test_wifi_connect_variants_report_success_and_failure():
    subprocess.run = lambda *a, **k: _FakeResult(returncode=0)
    assert connectivity.wifi_connect("Heimnetz", "hunter2") == (True, None)
    assert connectivity.wifi_connect_known("Heimnetz") == (True, None)
    assert connectivity.wifi_disconnect("Heimnetz") == (True, None)
    assert connectivity.wifi_forget("Heimnetz") == (True, None)

    subprocess.run = lambda *a, **k: _FakeResult(returncode=1, stderr="Error: No network with SSID found.")
    success, error = connectivity.wifi_connect("Ghost", "pw")
    assert not success and "SSID" in error


def test_wifi_is_metered_parses_nmcli_general_output():
    subprocess.run = lambda *a, **k: _FakeResult(stdout="yes\n")
    assert connectivity.wifi_is_metered() is True
    subprocess.run = lambda *a, **k: _FakeResult(stdout="no\n")
    assert connectivity.wifi_is_metered() is False
    subprocess.run = lambda *a, **k: _FakeResult(stdout="unknown\n")
    assert connectivity.wifi_is_metered() is None
    subprocess.run = lambda *a, **k: _FakeResult(returncode=1, stderr="device not found")
    assert connectivity.wifi_is_metered() is None


if __name__ == "__main__":
    original_run = subprocess.run
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        subprocess.run = original_run  # reset between tests, each one patches its own fake
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
