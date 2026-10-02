#!/bin/bash
# One-time provisioning script for a freshly flashed Raspberry Pi OS card.
# Run on the Pi itself (not cross-compiled/executed remotely) - needs sudo,
# so run it interactively: bash setup_pi.sh
set -e

# Resolve paths relative to this script's own location, not the caller's CWD -
# so it works whether invoked as ./setup_pi.sh, bash Software/setup_pi.sh, or
# via an absolute path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- system packages ---
sudo apt update

# Add a temporary raw swapfile before the big install below - this CM4 only
# has ~905MB RAM (confirmed via `free -h`) and Raspberry Pi OS's default
# zram swap competes with that same physical RAM pool instead of adding
# real headroom. Installing nodejs/bluez/pipewire/wireplumber/ffmpeg in one
# go OOM-killed apt without this. Uses plain fallocate/mkswap/swapon
# (util-linux, always present) instead of a swap-manager package - works
# the same regardless of whether the OS ships dphys-swapfile or zram-only.
SETUP_SWAPFILE=/var/tmp/setup-swap
sudo fallocate -l 1G "$SETUP_SWAPFILE"
sudo chmod 600 "$SETUP_SWAPFILE"
sudo mkswap "$SETUP_SWAPFILE" > /dev/null
sudo swapon "$SETUP_SWAPFILE"

# nodejs: yt-dlp needs a JS runtime for signature-protected YouTube formats
# (sync_youtube.py's js_runtimes option) - without it ~40% of a real
# playlist's downloads fail silently.
# mpv: player.py's actual playback backend (see its own docstring) - without
# it AudioPlayer can't even spawn, so nothing plays at all, BT or jack.
# pipewire/pipewire-audio/wireplumber/libspa-0.2-bluetooth: player.py forces
# mpv's --ao=pipewire (confirmed live the only backend that actually reaches a
# Bluetooth A2DP sink here - plain ALSA has no route to one, no hardware
# sound card exists). libspa-0.2-bluetooth is the actual piece that lets
# PipeWire/WirePlumber register the A2DP profile with BlueZ - without it,
# bluetoothctl never advertises an Audio Sink/Source UUID at all.
# Split into smaller installs (not one big list) - keeps peak concurrent
# dpkg postinst/trigger memory pressure down, same end result.
sudo apt install -y python3-pip python3-pil python3-numpy i2c-tools rfkill
sudo apt install -y ffmpeg mpv
sudo apt install -y bluez bluez-firmware
sudo apt install -y nodejs
sudo apt install -y pipewire pipewire-audio wireplumber libspa-0.2-bluetooth

# Remove the temporary swapfile again now that the heavy installs are done -
# leaves the system back on its default (zram-only) setup.
sudo swapoff "$SETUP_SWAPFILE"
sudo rm -f "$SETUP_SWAPFILE"

# --- i2c-dev module ---
sudo modprobe i2c-dev
echo "i2c-dev" | sudo tee /etc/modules-load.d/i2c-dev.conf

# --- python packages ---
pip3 install --break-system-packages \
  luma.lcd luma.oled \
  adafruit-circuitpython-gc9a01a adafruit-blinka adafruit-blinka-displayio \
  adafruit-circuitpython-neopixel smbus2

# yt-dlp specifically: --upgrade, and separate from the install above - piwheels
# (the ARM wheel cache pip resolves against here) lags PyPI's source releases,
# observed live installing a 17-month-old yt-dlp that silently extracted 0
# videos from every playlist (YouTube changed its playlist page's internal
# format; old yt-dlp warns "Unsupported lockup view model content type" and
# just returns nothing instead of erroring). --upgrade forces pip to check for
# and take a newer release instead of treating an already-satisfied old one as
# done.
pip3 install --break-system-packages --upgrade yt-dlp

# --- GPIO16 soft-power-hold ---
sudo tee /etc/systemd/system/gpio16-hold.service > /dev/null <<'EOF'
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
EOF

sudo tee /etc/systemd/system/gpio16-poweroff.service > /dev/null <<'EOF'
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
EOF

sudo tee /etc/systemd/system/gpio9-pullup.service > /dev/null <<'EOF'
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
EOF

# --- Bluetooth soft-rfkill unblock (hci0 comes up soft-blocked on this board
# by default - confirmed via /sys/class/rfkill/rfkill0/soft=1, hard=0 - not a
# hardware switch, just needs clearing once per boot). See connectivity.py's
# module docstring, which already assumed this service's existence. ---
sudo tee /etc/systemd/system/bluetooth-unblock.service > /dev/null <<'EOF'
[Unit]
Description=Clear the Bluetooth radio's soft rfkill block at boot
Before=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/rfkill unblock bluetooth
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo cp "$SCRIPT_DIR/mp3player.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/charge_control.service" /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now gpio16-hold.service
sudo systemctl enable gpio16-poweroff.service
sudo systemctl enable --now gpio9-pullup.service
sudo systemctl enable --now bluetooth-unblock.service
sudo systemctl enable mp3player.service
sudo systemctl enable charge_control.service

# --- PipeWire/WirePlumber Bluetooth audio (user services, see connectivity.py's
# setup notes and player.py's --ao=pipewire) ---
# enable-linger: mp3player.service itself runs as a plain system unit (no
# login session), so without this, PipeWire/WirePlumber's *user* services
# would never start at boot - only while pkenner is actually logged in.
sudo loginctl enable-linger pkenner
#
# WirePlumber's default "main" profile gates its Bluetooth monitor on a
# logind "seat active" state (see wireplumber.lua bluez.lua's
# startStopMonitor()) that a headless SSH-only device never reaches - it
# gets stuck at "online", so the bluez5 SPA monitor (and therefore A2DP
# registration with BlueZ) silently never starts, confirmed live via
# WIREPLUMBER_DEBUG=4 (bluetoothctl never gets an Audio Sink/Source UUID).
# WirePlumber ships a ready-made "main-embedded" profile for exactly this
# (systemwide/headless, no logind seat-gating, no runtime-state persistence)
# - it just needs to actually be selected, which is a -p CLI flag, not an
# env var (WIREPLUMBER_PROFILE does nothing on 0.5.x - confirmed live).
mkdir -p ~/.config/systemd/user/wireplumber.service.d
cat > ~/.config/systemd/user/wireplumber.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/wireplumber -p main-embedded
EOF
systemctl --user daemon-reload
systemctl --user enable --now pipewire pipewire-pulse wireplumber

# --- NOPASSWD sudoers rule for the power-button shutdown path only ---
echo 'pkenner ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff' | sudo tee /etc/sudoers.d/mp3player-poweroff > /dev/null
sudo chmod 440 /etc/sudoers.d/mp3player-poweroff
sudo visudo -c

# --- boot speed: cloud-init and NetworkManager-wait-online cost ~8.5s
# combined (measured via systemd-analyze blame) and serve no purpose once the
# device's network-config/user-data are applied - cloud-init's own config
# doesn't change again after the first boot, and mp3player.service doesn't
# need confirmed network connectivity to start (it has no such dependency).
sudo systemctl disable cloud-init-local.service cloud-init-main.service cloud-init-network.service cloud-config.service cloud-final.service
sudo systemctl disable NetworkManager-wait-online.service
sudo touch /etc/cloud/cloud-init.disabled

echo "--- done ---"
