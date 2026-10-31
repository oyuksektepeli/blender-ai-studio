#!/usr/bin/env python3
"""
Blender AI Film Stüdyosu — Antigravity MCP Köprüsü (Zero-Dependency Stdio MCP Server)
Uzaktaki GCP GPU sunucusunda (blender-studio:9876) çalışan Blender ile konuşur,
uyku modundaysa otomatik uyandırır, fotoğraf (.png) ve film (.mp4) renderlarını
otomatik olarak gs://yuksektek-blender-films bucket'ına yükleyip direkt link döndürür.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT_ID = os.environ.get("BLENDER_GCP_PROJECT", "yuksektek")
INSTANCE_NAME = os.environ.get("BLENDER_INSTANCE_NAME", "blender-studio")
BUCKET_NAME = os.environ.get("BLENDER_BUCKET_NAME", "yuksektek-blender-films")
BLENDER_PORT = int(os.environ.get("BLENDER_PORT", "9876"))


def get_instance_info() -> Dict[str, str]:
    """GCP üzerindeki blender-studio makinesinin durumunu, bölgesini ve dış IP'sini sorgular."""
    try:
        cmd = [
            "gcloud", "compute", "instances", "list",
            f"--project={PROJECT_ID}",
            f"--filter=name={INSTANCE_NAME}",
            "--format=json(name,zone,status,networkInterfaces[0].accessConfigs[0].natIP)"
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=15)
        items = json.loads(out)
        if not items:
            return {"status": "NOT_FOUND", "ip": "", "zone": ""}
        item = items[0]
        zone = item.get("zone", "").split("/")[-1]
        status = item.get("status", "UNKNOWN")
        ip = ""
        nics = item.get("networkInterfaces", [])
        if nics and nics[0].get("accessConfigs"):
            ip = nics[0]["accessConfigs"][0].get("natIP", "")
        return {"status": status, "ip": ip, "zone": zone}
    except Exception as e:
        return {"status": f"ERROR: {e}", "ip": os.environ.get("BLENDER_HOST", "35.246.180.235"), "zone": "europe-west3-a"}


def send_blender_command(cmd_type: str, params: Dict[str, Any] = None, timeout: float = 180.0) -> Dict[str, Any]:
    """Uzaktaki Blender MCP soketine (port 9876) JSON komutu gönderir ve yanıtı alır."""
    info = get_instance_info()
    host = os.environ.get("BLENDER_HOST") or info.get("ip") or "35.246.180.235"

    if info.get("status") in ("TERMINATED", "STOPPED", "SUSPENDED"):
        wake_res = wake_studio(info)
        if not wake_res.get("ok"):
            return {"status": "error", "message": wake_res.get("message", "Stüdyo uyandırılamadı.")}
        info = get_instance_info()
        host = info.get("ip") or host

    payload = json.dumps({"type": cmd_type, "params": params or {}}).encode("utf-8")
    with socket.create_connection((host, BLENDER_PORT), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                try:
                    data = b"".join(chunks)
                    return json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
        raw = b"".join(chunks).decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {"status": "error", "message": "Empty response from Blender"}


def wake_studio(info: Dict[str, str] = None) -> Dict[str, Any]:
    """Uyku modundaki blender-studio makinesini başlatır ve Blender MCP hazır olana kadar bekler."""
    if not info:
        info = get_instance_info()
    zone = info.get("zone") or "europe-west3-a"
    status = info.get("status")
    if status != "RUNNING":
        try:
            subprocess.check_call(
                ["gcloud", "compute", "instances", "start", INSTANCE_NAME, f"--project={PROJECT_ID}", f"--zone={zone}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120
            )
        except Exception as e:
            return {"ok": False, "message": f"GCP instance start hatası: {e}"}

    # Wait up to 60s for Blender socket 9876
    for _ in range(30):
        info = get_instance_info()
        ip = info.get("ip")
        if ip:
            try:
                with socket.create_connection((ip, BLENDER_PORT), timeout=3):
                    return {
                        "ok": True,
                        "ip": ip,
                        "zone": zone,
                        "web_desktop_url": f"http://{ip}:6080/vnc.html?autoconnect=true&resize=scale",
                        "cinema_gallery_url": "https://blender-sinema-salonu-74454451681.europe-west3.run.app"
                    }
            except Exception:
                pass
        time.sleep(2)
    return {"ok": True, "ip": info.get("ip", ""), "zone": zone, "message": "Makine başlatıldı, Blender servisi hazırlanıyor."}


TOOLS = [
    {
        "name": "studio_status_and_wake",
        "description": "Buluttaki Blender GPU Stüdyosunun açık olup olmadığını kontrol eder. 120 dk uyku modundaysa otomatik olarak uyandırır ve Canlı Masaüstü ile Sinema Salonu linklerini döndürür.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_scene_info",
        "description": "Blender sahnesindeki mevcut objeleri, kameraları, ışıkları ve render ayarlarını getirir.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_object_info",
        "description": "Belirtilen 3D objenin konum, boyut, dönüş ve materyal detaylarını getirir.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Obje adı"}},
            "required": ["name"]
        }
    },
    {
        "name": "execute_blender_code",
        "description": "Uzaktaki Blender içinde Python (bpy) kodu çalıştırarak 3D sahne, model, ışık, materyal ve kamera animasyonu oluşturur.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Çalıştırılacak Blender Python (bpy) kodu"}},
            "required": ["code"]
        }
    },
    {
        "name": "render_preview_snapshot",
        "description": "Mevcut sahnenin hızlı bir HD önizleme fotoğrafını (.png) GPU ile render alır, Google Cloud Storage'a yükler ve doğrudan tıklanabilir fotoğraf linkini döndürür.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "shot_name": {"type": "string", "description": "Fotoğraf adı (örn: kristal_sato_onizleme)"},
                "samples": {"type": "integer", "description": "Render kalitesi (varsayılan 32)", "default": 32}
            },
            "required": ["shot_name"]
        }
    },
    {
        "name": "render_animation_mp4",
        "description": "Sahnedeki animasyonu NVIDIA GPU ile .mp4 film olarak render alır, otomatik olarak Google Cloud Storage (yuksektek-blender-films) bucket'ına yükler, Sinema Salonunu günceller ve kızınıza verilecek doğrudan izleme/indirme linkini döndürür.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "film_name": {"type": "string", "description": "Filmin dosya adı (örn: kristal_saray_filmi)"},
                "frame_start": {"type": "integer", "description": "Başlangıç karesi (varsayılan 1)", "default": 1},
                "frame_end": {"type": "integer", "description": "Bitiş karesi (örn: 4 saniye için 96, 5 saniye için 120)", "default": 96},
                "engine": {"type": "string", "description": "BLENDER_EEVEE_NEXT (çok hızlı) veya CYCLES (OptiX Ray-Tracing)", "default": "CYCLES"},
                "samples": {"type": "integer", "description": "Kare başı sample sayısı (varsayılan 32)", "default": 32}
            },
            "required": ["film_name"]
        }
    },
    {
        "name": "search_polyhaven_assets",
        "description": "Poly Haven ücretsiz kütüphanesinde gökyüzü (hdris), doku (textures) veya 3D model (models) arar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string", "description": "hdris, textures, models veya all", "default": "all"},
                "categories": {"type": "string", "description": "Kategori filtresi (opsiyonel)"}
            }
        }
    },
    {
        "name": "download_polyhaven_asset",
        "description": "Poly Haven'dan ücretsiz 3D model, 4K doku veya HDRI gökyüzü indirip sahneye uygular.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Asset ID"},
                "asset_type": {"type": "string", "description": "hdris, textures veya models"},
                "resolution": {"type": "string", "description": "Çözünürlük (1k, 2k, 4k)", "default": "2k"}
            },
            "required": ["asset_id", "asset_type"]
        }
    },
    {
        "name": "list_studio_films",
        "description": "Google Cloud Storage (yuksektek-blender-films) üzerindeki tüm çekilmiş filmleri ve fotoğrafları doğrudan indirme linkleriyle listeler.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "generate_character_voiceover",
        "description": "yuksektek projesindeki Gemini 3.1 Flash TTS (Aoede, Puck, Charon, Fenrir, Leda, Kore) veya Chirp3-HD ile Türkçe çizgi film karakter seslendirmesi üretir, ses değiştirme efekti (normal, peri_sincap, dev_kaptan, komik_robot, buyulu_magara) uygular ve 24 FPS dudak senkronu (mouth_envelope) verisini döndürür.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Karakterin Türkçe söyleyeceği replik"},
                "character_profile": {
                    "type": "string",
                    "description": "Karakter ses kimliği: PIRIL_GENC_KIZ (Aoede), TIKIR_KOMIK_YARDIMCI (Puck), BILGE_USTA (Charon), KAHRAMAN_KAPTAN (Fenrir), MASAL_PERISI (Leda), BILIM_REHBERI (Kore)",
                    "default": "PIRIL_GENC_KIZ"
                },
                "emotion_prompt": {"type": "string", "description": "Duygu ve oyunculuk yönergesi (örn: Heyecanlı ve neşeli bir çizgi film karakteri gibi Türkçe söyle)"},
                "voice_effect": {
                    "type": "string",
                    "description": "Ses değiştirme efekti: normal, hizli_cizgi_film, peri_sincap, dev_kaptan, komik_robot, buyulu_magara",
                    "default": "normal"
                },
                "output_wav_path": {"type": "string", "description": "Kaydedilecek WAV dosya yolu (opsiyonel)"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "generate_film_soundtrack",
        "description": "yuksektek projesindeki Lyria 3 Pro (lyria-3-pro-preview) modeli ile Studio Ghibli / Pixar tarzında orkestral çizgi film ve animasyon müziği üretir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Müzik tarzı ve enstrüman açıklaması (İngilizce veya Türkçe)"},
                "output_wav_path": {"type": "string", "description": "Kaydedilecek WAV dosya yolu (opsiyonel)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "generate_ai_skybox_or_texture",
        "description": "yuksektek projesindeki Gemini 3 Pro Image (gemini-3-pro-image) veya Gemini 3.1 Flash Image modeli ile Blender 3D sahneleri için boyalı gökyüzü kubbesi (skybox) veya 3D obje kaplama dokusu (UV texture) üretir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Üretilecek gökyüzü veya yüzey dokusunun açıklaması"},
                "output_png_path": {"type": "string", "description": "Kaydedilecek PNG dosya yolu"},
                "aspect_ratio": {"type": "string", "description": "En-boy oranı (16:9, 1:1)", "default": "16:9"}
            },
            "required": ["prompt", "output_png_path"]
        }
    },
    {
        "name": "dub_and_publish_film",
        "description": "Çekilmiş bir .mp4 filme birden fazla karakterin Türkçe dublajını, ses değiştirme efektlerini ve Lyria 3 Pro arka plan müziğini (konuşma anında müziği otomatik kısarak / auto-ducking) birleştirir ve Özel Sinema Salonuna (yuksektek-blender-films) yükleyip direkt izleme/indirme linkini döndürür.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "film_name": {"type": "string", "description": "Dublaj eklenecek filmin adı (örn: kristal_saray_tanitim_filmi)"},
                "dialogue_lines": {
                    "type": "array",
                    "description": "Sırasıyla konuşacak karakter replikleri listesi",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "character_profile": {"type": "string", "default": "PIRIL_GENC_KIZ"},
                            "emotion_prompt": {"type": "string"},
                            "voice_effect": {"type": "string", "default": "normal"}
                        },
                        "required": ["text"]
                    }
                },
                "music_prompt": {"type": "string", "description": "Arka plan için Lyria 3 Pro film müziği açıklaması (opsiyonel)"}
            },
            "required": ["film_name", "dialogue_lines"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "studio_status_and_wake":
        res = wake_studio()
        return res
    elif name == "list_studio_films":
        try:
            out = subprocess.check_output(
                ["gcloud", "storage", "ls", f"gs://{BUCKET_NAME}/**"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=15
            )
            cinema_url = "https://blender-sinema-salonu-74454451681.europe-west3.run.app"
            urls = [
                line.strip().replace(f"gs://{BUCKET_NAME}/", f"{cinema_url}/media/")
                for line in out.splitlines() if line.strip() and not line.strip().endswith("index.html")
            ]
            return {
                "cinema_gallery_url": cinema_url,
                "files": urls
            }
        except Exception as e:
            return {"error": str(e)}
    elif name in (
        "generate_character_voiceover",
        "generate_film_soundtrack",
        "generate_ai_skybox_or_texture",
        "dub_and_publish_film",
    ):
        import ai_dubbing_and_music as adm
        if name == "generate_character_voiceover":
            return adm.synthesize_character_speech(
                text=args["text"],
                character_profile=args.get("character_profile", "PIRIL_GENC_KIZ"),
                emotion_prompt=args.get("emotion_prompt"),
                voice_effect=args.get("voice_effect", "normal"),
                output_wav_path=args.get("output_wav_path"),
            )
        elif name == "generate_film_soundtrack":
            return adm.generate_lyria_music(
                prompt=args["prompt"],
                output_wav_path=args.get("output_wav_path"),
            )
        elif name == "generate_ai_skybox_or_texture":
            return adm.generate_ai_texture(
                prompt=args["prompt"],
                output_png_path=args["output_png_path"],
                aspect_ratio=args.get("aspect_ratio", "16:9"),
            )
        elif name == "dub_and_publish_film":
            return adm.dub_film_with_dialogue_and_music(
                film_name=args["film_name"],
                dialogue_lines=args["dialogue_lines"],
                music_prompt=args.get("music_prompt"),
            )
    else:
        return send_blender_command(name, args, timeout=1800.0)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "blender-ai-studio-mcp", "version": "1.0.0"}
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "tools/call":
            params = req.get("params", {})
            t_name = params.get("name")
            t_args = params.get("arguments", {})
            try:
                res_data = handle_tool_call(t_name, t_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res_data, ensure_ascii=False, indent=2)}]
                    }
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Hata: {e}"}]
                    }
                }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif req_id is not None:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
