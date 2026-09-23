"""ES8388 audio codec driver (raw I2C register writes) - playback path only.

No mainline Linux codec driver is shipped for this chip on this kernel build
(checked live: no es8328/es8388 .ko under /lib/modules) - see CLAUDE.md. Audio
instead reaches the codec as a raw I2S PCM stream via `dtoverlay=i2s-dac`, a
codec-less ALSA machine driver originally meant for passive DACs like the
PCM1794A - it hands ALSA a PCM sink with the Pi as I2S bus master and does zero
chip control of its own, while this module does everything the codec itself
needs: power-up, output routing, and mute/volume.

Register map and init sequence adapted from Espressif's ESP-ADF reference
driver (MIT licensed - github.com/espressif/esp-adf, components/audio_hal/
driver/es8388/es8388.c) - not guessed, same reasoning as rt9466.py's datasheet
citation: getting the DAC power-up sequence wrong risks a stuck-mute chip or an
audible pop. Register addresses cross-checked against the ES8388 User Guide
(https://dl.radxa.com/rock2/docs/hw/ds/ES8388%20user%20Guide.pdf). ADC/mic
registers are skipped entirely - this device is playback-only.

Board-specific: Projekt 1.net (KiCad netlist) confirms LOUT1/ROUT1 (ES8388
pins 12/11) are unconnected on this board - only LOUT2/ROUT2 (pins 15/14) are
wired out to the 3.5mm jack (via C8/R5 and C10/R2 to AUDIO1). DACPOWER's write
below enables only those two outputs, not the datasheet-typical "all four".
"""
from smbus2 import SMBus

ADDR = 0x10  # 7-bit; CE=GND -> the datasheet's 0x20 is 8-bit-with-R/W-bit (0x20 >> 1), see CLAUDE.md
BUS = 1

REG_CONTROL1 = 0x00
REG_CONTROL2 = 0x01
REG_CHIPPOWER = 0x02
REG_ADCPOWER = 0x03
REG_DACPOWER = 0x04
REG_MASTERMODE = 0x08
REG_DACCONTROL1 = 0x17
REG_DACCONTROL2 = 0x18
REG_DACCONTROL3 = 0x19
REG_DACCONTROL4 = 0x1a
REG_DACCONTROL5 = 0x1b
REG_DACCONTROL16 = 0x26
REG_DACCONTROL17 = 0x27
REG_DACCONTROL20 = 0x2a
REG_DACCONTROL21 = 0x2b
REG_DACCONTROL23 = 0x2d
REG_DACCONTROL24 = 0x2e
REG_DACCONTROL25 = 0x2f
REG_DACCONTROL26 = 0x30
REG_DACCONTROL27 = 0x31

DACPOWER_OFF = 0xC0  # DAC + all line outs disabled - used while (re)configuring
DACPOWER_LOUT2_ROUT2 = 0x0C  # DAC on, only LOUT2/ROUT2 enabled - the pair this board wires to the jack
MUTE_BIT = 0x04  # DACCONTROL3 bit2


class ES8388:
    def __init__(self, bus=BUS, address=ADDR):
        self._bus = SMBus(bus)
        self._addr = address

    def _write(self, reg, value):
        self._bus.write_byte_data(self._addr, reg, value)

    def init_playback(self, volume=70):
        """Power up the DAC path muted, route it to LOUT2/ROUT2, set volume, then
        unmute last - avoids a pop through half-configured registers. Assumes the
        Pi is I2S bus master (dtoverlay=i2s-dac) and MCLK is already running
        (dtoverlay=gpclk,gpclk1_5,freq=12288000); registers can be written over
        I2C without either per the datasheet, but no audio will actually flow
        until both are present.
        """
        self._write(REG_DACCONTROL3, MUTE_BIT)  # mute, soft-ramp off, before touching anything else
        self._write(REG_CONTROL2, 0x50)
        self._write(REG_CHIPPOWER, 0x00)         # power up all chip blocks
        self._write(REG_MASTERMODE, 0x00)        # I2S slave - the Pi drives BCLK/LRCK
        self._write(REG_DACPOWER, DACPOWER_OFF)
        # 0x12 (play & record mode) | bit5 (DACMCLK_DAC, confirmed against mainline
        # Linux's es8328.h): the DAC's sample clock comes from its own generation
        # path instead of being derived through the ADC block - matters because
        # ADCPOWER below fully powers the ADC down (playback-only device), and
        # without this bit the DAC would be silently starved of a working clock
        # despite every other register looking correct (mute/pop still happens -
        # that's pure analog bias, not proof the DAC core is actually converting).
        self._write(REG_CONTROL1, 0x12 | (1 << 5))
        self._write(REG_DACCONTROL1, 0x18)       # 16-bit I2S
        self._write(REG_DACCONTROL2, 0x02)       # single-speed, 256x MCLK ratio (12.288MHz / 48kHz)
        self._write(REG_DACCONTROL16, 0x00)      # analog-bypass mixer input select - unused, LIN1 isn't wired on this board
        self._write(REG_DACCONTROL17, 0x90)      # left DAC -> left mixer
        self._write(REG_DACCONTROL20, 0x90)      # right DAC -> right mixer
        self._write(REG_DACCONTROL21, 0x80)      # DAC follows ADC's LRCK internally (datasheet-recommended even with ADC unused)
        self._write(REG_DACCONTROL23, 0x00)      # VROI = 0
        self._write(REG_DACCONTROL4, 0x00)       # right DAC digital volume: 0dB
        self._write(REG_DACCONTROL5, 0x00)       # left DAC digital volume: 0dB
        self._write(REG_DACPOWER, DACPOWER_LOUT2_ROUT2)
        self._write(REG_ADCPOWER, 0xFF)          # power down ADC/mic entirely - playback-only device
        self.set_volume(volume)
        self._write(REG_DACCONTROL3, 0x00)       # unmute

    def set_volume(self, volume):
        """volume: 0-100. DACCONTROL24/25 (0x2e/0x2f) are LOUT1VOL/ROUT1VOL and
        DACCONTROL26/27 (0x30/0x31) are LOUT2VOL/ROUT2VOL (confirmed against
        mainline Linux's es8328.h, which covers the same register map) - this
        board only wires out LOUT2/ROUT2 (see DACPOWER_LOUT2_ROUT2 above), so
        only 26/27 matter here. Both pairs use 0=min/mute .. 0x24=max, not
        attenuation-from-0dB like the earlier ESP-ADF reference code assumed
        (that code targeted a board using LOUT1/ROUT1, and left 26/27 at a
        hardcoded 0 - i.e. muted - which would have silently killed playback
        on this board if copied verbatim, as it briefly did before this fix)."""
        reg_value = round(max(0, min(100, volume)) / 100 * 0x24)
        self._write(REG_DACCONTROL26, reg_value)
        self._write(REG_DACCONTROL27, reg_value)

    def mute(self, enable):
        current = self._bus.read_byte_data(self._addr, REG_DACCONTROL3)
        self._write(REG_DACCONTROL3, (current & ~MUTE_BIT & 0xFF) | (MUTE_BIT if enable else 0))


def demo():
    """Self-check: DACPOWER bit math, then (on real hardware) init playback at a
    conservative volume so a first-ever run doesn't blast whatever's plugged in."""
    assert DACPOWER_LOUT2_ROUT2 == 0b00001100
    print("Bit math self-check OK.")

    codec = ES8388()
    codec.init_playback(volume=40)
    print("ES8388 initialized: DAC unmuted, LOUT2/ROUT2 enabled, volume 40.")


if __name__ == "__main__":
    demo()
