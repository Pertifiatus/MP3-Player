"""Pure-logic tests for the RT9466 register encoding - no hardware needed.
smbus2 only exists on Linux (imports fcntl), so it's stubbed out here to let
this run on the Windows dev machine too. Run directly: python3 test_rt9466.py
"""
import sys
import types

if "smbus2" not in sys.modules:
    stub = types.ModuleType("smbus2")
    stub.SMBus = object
    sys.modules["smbus2"] = stub

from rt9466 import _voreg_code, _ichg_code


def test_voreg_matches_datasheet_table():
    assert _voreg_code(3.9) == 0b0000000
    assert _voreg_code(3.91) == 0b0000001
    assert _voreg_code(4.2) == 0b0011110  # default
    assert _voreg_code(4.71) == 0b1010001


def test_voreg_clamps_to_datasheet_range():
    assert _voreg_code(3.0) == 0  # below range - never write a negative/wrapping code
    assert _voreg_code(5.0) == 0b1010001  # above range - clamp down, never over-volt


def test_ichg_matches_datasheet_table():
    assert _ichg_code(0.1) == 0b000000
    assert _ichg_code(0.2) == 0b000001
    assert _ichg_code(2.0) == 0b010011  # default
    assert _ichg_code(5.0) == 0b110001


def test_ichg_clamps_to_datasheet_range():
    assert _ichg_code(0.0) == 0  # never encode a negative/wrapping code
    assert _ichg_code(6.0) == 0b110001  # above range - clamp down, never over-current


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"{len(tests)} tests passed.")
