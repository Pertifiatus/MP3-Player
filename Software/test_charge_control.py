"""Pure-logic tests for the SOC-to-charge-current band selection - no hardware needed.
smbus2 only exists on Linux (imports fcntl), so it's stubbed out here to let
this run on the Windows dev machine too. Run directly: python3 test_charge_control.py
"""
import sys
import types

if "smbus2" not in sys.modules:
    stub = types.ModuleType("smbus2")
    stub.SMBus = object
    stub.i2c_msg = object
    sys.modules["smbus2"] = stub

from charge_control import band_current_ma, SLOW_MA, NORMAL_MA


def test_low_soc_is_slow():
    assert band_current_ma(0) == SLOW_MA
    assert band_current_ma(19.9) == SLOW_MA


def test_high_soc_is_slow():
    assert band_current_ma(80.1) == SLOW_MA
    assert band_current_ma(100) == SLOW_MA


def test_mid_soc_is_normal():
    assert band_current_ma(20) == NORMAL_MA  # boundary itself belongs to the normal band
    assert band_current_ma(50) == NORMAL_MA
    assert band_current_ma(80) == NORMAL_MA  # boundary itself belongs to the normal band


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"{len(tests)} tests passed.")
