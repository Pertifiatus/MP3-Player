#!/bin/bash
# One-time provisioning script for a freshly flashed Raspberry Pi OS card.
# Run on the Pi itself (not cross-compiled/executed remotely) - needs sudo,
# so run it interactively: bash setup_pi.sh
set -e

# --- system packages ---
sudo apt update
sudo apt install -y python3-pip python3-pil python3-numpy i2c-tools ffmpeg rfkill bluez bluez-firmware

# --- i2c-dev module ---
sudo modprobe i2c-dev
echo "i2c-dev" | sudo tee /etc/modules-load.d/i2c-dev.conf

# --- python packages ---
pip3 install --break-system-packages \
  luma.lcd luma.oled \
  adafruit-circuitpython-gc9a01a adafruit-blinka adafruit-blinka-displayio \
  adafruit-circuitpython-neopixel smbus2 yt-dlp

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

sudo cp Software/mp3player.service /etc/systemd/system/
sudo cp Software/charge_control.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now gpio16-hold.service
sudo systemctl enable gpio16-poweroff.service
sudo systemctl enable gpio9-pullup.service
sudo systemctl enable --now bluetooth-unblock.service
sudo systemctl enable mp3player.service
sudo systemctl enable charge_control.service

# --- NOPASSWD sudoers rule for the power-button shutdown path only ---
echo 'pkenner ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff' | sudo tee /etc/sudoers.d/mp3player-poweroff > /dev/null
sudo chmod 440 /etc/sudoers.d/mp3player-poweroff
sudo visudo -c

echo "--- done ---"
