#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_SCRIPT="${REPO_DIR}/scripts/blender_studio_mcp_bridge.py"
chmod +x "${BRIDGE_SCRIPT}"

echo "🎬 Blender AI Film Stüdyosu — Antigravity MCP Kurulumu Başlıyor..."
echo "📂 Stüdyo Dizini: ${REPO_DIR}"

python3 - "${REPO_DIR}" "${BRIDGE_SCRIPT}" << 'PYEOF'
import json
import os
import sys

repo_dir = sys.argv[1]
bridge_script = sys.argv[2]

mcp_entry = {
    "command": "python3",
    "args": [bridge_script],
    "env": {
        "BLENDER_GCP_PROJECT": "yuksektek",
        "BLENDER_INSTANCE_NAME": "blender-studio",
        "BLENDER_BUCKET_NAME": "yuksektek-blender-films",
        "BLENDER_PORT": "9876",
        "BLENDER_HOST": "35.246.180.235"
    }
}

# 1. Workspace .gemini/settings.json güncelle
ws_settings_path = os.path.join(repo_dir, ".gemini", "settings.json")
os.makedirs(os.path.dirname(ws_settings_path), exist_ok=True)
ws_data = {}
if os.path.exists(ws_settings_path):
    try:
        with open(ws_settings_path, "r", encoding="utf-8") as f:
            ws_data = json.load(f)
    except Exception:
        ws_data = {}

ws_data.setdefault("mcpServers", {})["blender-studio"] = mcp_entry
with open(ws_settings_path, "w", encoding="utf-8") as f:
    json.dump(ws_data, f, indent=2, ensure_ascii=False)
print(f"✅ Workspace MCP ayarları güncellendi: {ws_settings_path}")

# 2. Global Antigravity MCP config güncelle (~/.gemini/config/mcp_config.json veya ~/.gemini/antigravity/mcp_config.json)
home = os.path.expanduser("~")
config_dir = os.path.join(home, ".gemini", "config")
agy_dir = os.path.join(home, ".gemini", "antigravity")
os.makedirs(config_dir, exist_ok=True)
os.makedirs(agy_dir, exist_ok=True)

target_cfg = os.path.join(config_dir, "mcp_config.json")
agy_cfg = os.path.join(agy_dir, "mcp_config.json")

global_data = {}
if os.path.exists(target_cfg):
    try:
        with open(target_cfg, "r", encoding="utf-8") as f:
            global_data = json.load(f)
    except Exception:
        global_data = {}
elif os.path.exists(agy_cfg):
    try:
        with open(agy_cfg, "r", encoding="utf-8") as f:
            global_data = json.load(f)
    except Exception:
        global_data = {}

global_data.setdefault("mcpServers", {})["blender-studio"] = mcp_entry
with open(target_cfg, "w", encoding="utf-8") as f:
    json.dump(global_data, f, indent=2, ensure_ascii=False)

if not os.path.exists(agy_cfg):
    try:
        os.symlink(target_cfg, agy_cfg)
    except Exception:
        with open(agy_cfg, "w", encoding="utf-8") as f:
            json.dump(global_data, f, indent=2, ensure_ascii=False)

print(f"✅ Global Antigravity MCP ayarları güncellendi: {target_cfg}")
PYEOF

echo "🎉 Kurulum tamamlandı! Artık Antigravity içerisinden doğrudan uzaktaki Blender 5.2 Stüdyosuna bağlanabilirsiniz."
