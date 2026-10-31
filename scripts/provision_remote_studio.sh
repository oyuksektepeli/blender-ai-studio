#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/6] Sistem paketleri, XFCE4 Masaüstü, NoVNC ve XRDP kuruluyor ==="
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y \
  xfce4 xfce4-goodies dbus-x11 x11-xserver-utils xvfb \
  x11vnc novnc python3-websockify xrdp \
  ffmpeg mesa-utils libxi6 libxrender1 libxkbcommon0 libxkbcommon-x11-0 \
  libsm6 libice6 libgl1 libegl1 libxxf86vm1 libxfixes3 \
  curl wget xz-utils jq

echo "=== [2/6] Blender 4.3 LTS indiriliyor ve /opt/blender altına kuruluyor ==="
if [ ! -f /opt/blender/blender ]; then
  cd /tmp
  wget -q --show-progress https://download.blender.org/release/Blender4.3/blender-4.3.2-linux-x64.tar.xz
  sudo mkdir -p /opt/blender
  sudo tar -xf blender-4.3.2-linux-x64.tar.xz -C /opt/blender --strip-components=1
  sudo ln -sf /opt/blender/blender /usr/local/bin/blender
  rm -f blender-4.3.2-linux-x64.tar.xz
fi
/opt/blender/blender --version

echo "=== [3/6] NVIDIA GPU Sanal Ekran (Headless Xorg 1920x1080) yapılandırılıyor ==="
sudo nvidia-xconfig --use-display-device=None --virtual=1920x1080 || true
sudo sed -i 's/allowed_users=console/allowed_users=anybody/' /etc/X11/Xwrapper.config 2>/dev/null || \
  echo "allowed_users=anybody" | sudo tee /etc/X11/Xwrapper.config

echo "=== [4/6] Studio kullanıcısı ve dizinleri hazırlanıyor ==="
if ! id -u studio >/dev/null 2>&1; then
  sudo useradd -m -s /bin/bash -G sudo,video,render studio
  echo "studio:BlenderStudio2026!" | sudo chpasswd
  echo "studio ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/studio
fi
sudo mkdir -p /opt/studio /home/studio/projects
sudo chown -R studio:studio /opt/studio /home/studio/projects

echo "=== [5/6] Systemd servisleri (Xorg, XFCE4, Web Desktop :6080, Blender MCP :9876) kuruluyor ==="
cat << 'EOF' | sudo tee /etc/systemd/system/studio-xorg.service >/dev/null
[Unit]
Description=Studio Virtual X11 Server (:0)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :0 -screen 0 1920x1080x24 +extension GLX +extension RANDR +render -noreset
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat << 'EOF' | sudo tee /etc/systemd/system/studio-desktop.service >/dev/null
[Unit]
Description=Studio XFCE4 Desktop Session (:0)
After=studio-xorg.service
Requires=studio-xorg.service

[Service]
Type=simple
User=studio
Environment=DISPLAY=:0
Environment=HOME=/home/studio
WorkingDirectory=/home/studio
ExecStartPre=/bin/sleep 2
ExecStart=/usr/bin/dbus-launch --exit-with-session /usr/bin/startxfce4
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat << 'EOF' | sudo tee /etc/systemd/system/studio-vnc.service >/dev/null
[Unit]
Description=Studio X11VNC & NoVNC Web Desktop (:6080)
After=studio-desktop.service
Requires=studio-desktop.service

[Service]
Type=simple
User=studio
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 3
ExecStart=/bin/bash -c '/usr/bin/x11vnc -display :0 -forever -shared -nopw -rfbport 5900 -bg && exec /usr/bin/websockify --web=/usr/share/novnc/ 6080 localhost:5900'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat << 'EOF' | sudo tee /etc/systemd/system/studio-blender.service >/dev/null
[Unit]
Description=Blender 4.3 LTS Live Studio & MCP Server (:9876)
After=studio-desktop.service
Requires=studio-desktop.service

[Service]
Type=simple
User=studio
Environment=DISPLAY=:0
Environment=HOME=/home/studio
WorkingDirectory=/home/studio/projects
ExecStartPre=/bin/sleep 4
ExecStart=/opt/blender/blender --python /opt/studio/blender_studio_server_addon.py
Restart=always
RestartSec=4

[Install]
WantedBy=multi-user.target
EOF

echo "=== [6/6] 120 Dakika Otomatik Uyku Kalkanı (Auto-Shutdown) kuruluyor ==="
cat << 'EOF' | sudo tee /opt/studio/check_idle_shutdown.sh >/dev/null
#!/usr/bin/env bash
IDLE_LIMIT_SEC=7200 # 120 dakika (7200 saniye)
NOW=$(date +%s)

# Aktif Web Desktop (:6080) veya RDP (:3389) bağlantısı varsa uyutma
ACTIVE_CONN=$(ss -tn state established '( sport = :6080 or sport = :3389 or sport = :9876 )' | tail -n +2 | wc -l)
if [ "$ACTIVE_CONN" -gt 0 ]; then
  echo "$NOW" > /tmp/blender_last_activity
  exit 0
fi

# Blender render yapıyorsa (GPU kullanımı > %10) uyutma
GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ' || echo 0)
if [ "${GPU_UTIL:-0}" -gt 10 ]; then
  echo "$NOW" > /tmp/blender_last_activity
  exit 0
fi

if [ ! -f /tmp/blender_last_activity ]; then
  echo "$NOW" > /tmp/blender_last_activity
  exit 0
fi

LAST=$(cat /tmp/blender_last_activity 2>/dev/null || echo "$NOW")
DIFF=$((NOW - LAST))

if [ "$DIFF" -ge "$IDLE_LIMIT_SEC" ]; then
  logger -t studio-autoshutdown "Stüdyo 120 dakikadır boşta ($DIFF sn). Maliyet koruma kalkanı makineyi kapatıyor."
  /sbin/shutdown -h now
fi
EOF
sudo chmod +x /opt/studio/check_idle_shutdown.sh

cat << 'EOF' | sudo tee /etc/systemd/system/studio-autoshutdown.service >/dev/null
[Unit]
Description=Check Blender Studio Idle Time (120m Auto-Shutdown)

[Service]
Type=oneshot
ExecStart=/opt/studio/check_idle_shutdown.sh
EOF

cat << 'EOF' | sudo tee /etc/systemd/system/studio-autoshutdown.timer >/dev/null
[Unit]
Description=Run Blender Studio Idle Check every 5 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now studio-xorg.service
sudo systemctl enable --now studio-desktop.service
sudo systemctl enable --now studio-vnc.service
sudo systemctl enable --now studio-blender.service
sudo systemctl enable --now studio-autoshutdown.timer
sudo systemctl enable --now xrdp.service

echo "✅ Kurulum Tamamlandı!"
