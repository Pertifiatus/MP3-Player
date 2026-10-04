# MP3-Player

A compact **DIY music player**, smaller than an iPod Touch, built around a Raspberry Pi Compute Module 4 on a custom PCB. It syncs your **YouTube Music** library straight to the device, no home server needed.

## Concept

- **Front:** round GC9A01 display for menus and navigation
- **Back:** monochrome SSD1306 OLED for music visualizations
- **Audio:** mainly Bluetooth A2DP, plus a 3.5 mm headphone jack (ES8388 codec)
- **Controls:** button box (SX1509 GPIO expander) + IMU (QMI8658A) for orientation and shake gestures
- **Power:** Li-ion battery, USB-C charging (RT9466) with an 80% charge limit, fuel gauge (MAX17048), soft power button
- **Lighting:** SK6812 status ring

## Hardware

| Part | Details |
|---|---|
| Compute | Raspberry Pi CM4 Lite Wireless (boots from microSD), on 2× Hirose mezzanine connectors |
| Power | TPS63020 buck-boost, RT9466 charger, MAX17048 fuel gauge |
| Audio | ES8388 codec over I2S |
| Displays | GC9A01 (SPI0), SSD1306 (SPI4) |
| PCBs | Main board + ButtonBox, designed in KiCad (`KiCad/Projekt 1`) |
| Case | Fusion 360 (`CAD/Player.f3z`) |

## Software (`Software/`)

Python on Raspberry Pi OS, running as systemd services:

| File | Purpose |
|---|---|
| `main.py` | Main UI loop (front display, buttons, IMU) |
| `player.py` | Playback |
| `sync_youtube.py` | YouTube Music library sync |
| `connectivity.py` | WiFi / Bluetooth connections |
| `ui_state.py`, `ui_render.py` | UI state machine and rendering |
| `buttonbox.py`, `qmi8658.py`, `es8388.py`, `max17048.py`, `rt9466.py` | Hardware drivers |
| `charge_control.py`, `power_button.py` | Charging logic and soft shutdown |
| `led_control.py`, `led_service.py` | Status ring LEDs |
| `setup_pi.sh`, `*.service`, `sdcard-boot-*` | Pi setup and boot configuration |
| `test_*.py` | Tests |

## Status

Work in progress. Board 2 boots reliably; the software bring-up and debugging of battery operation are ongoing. Detailed notes on hardware, pinout, `config.txt` and lessons learned are in [`CLAUDE.md`](CLAUDE.md) and [`Software/NOTES_FOR_PER.md`](Software/NOTES_FOR_PER.md).

## Repository structure

```
CAD/        Fusion 360 case
KiCad/      Main board + ButtonBox (schematics, PCB, 3D models)
Software/   Python application, drivers, services, tests
docs/       Design specs and plans (status ring, quick connect)
```
