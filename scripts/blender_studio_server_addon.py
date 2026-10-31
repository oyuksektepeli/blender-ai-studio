"""
Blender AI Film Stüdyosu — Sunucu İçi Blender MCP + Otomatik Render/GCS Upload Servisi
Blender 4.x başlangıcında otomatik çalışır, 0.0.0.0:9876 portundan gelen MCP komutlarını
Blender ana thread'inde (bpy.app.timers) güvenli şekilde çalıştırır.
"""

import bpy
import io
import json
import os
import queue
import socket
import subprocess
import threading
import time
import traceback
import urllib.request
from contextlib import redirect_stdout

HOST = "0.0.0.0"
PORT = 9876
BUCKET_NAME = "yuksektek-blender-films"
ACTIVITY_FILE = "/tmp/blender_last_activity"

cmd_queue = queue.Queue()


def touch_activity():
    try:
        with open(ACTIVITY_FILE, "w") as f:
            f.write(str(int(time.time())))
    except Exception:
        pass


def enable_gpu_rendering():
    """NVIDIA GPU (OptiX / CUDA) donanım hızlandırmasını Blender'da aktif eder."""
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                cprefs.compute_device_type = dev_type
                cprefs.get_devices()
                gpus = [d for d in cprefs.devices if d.type in ("OPTIX", "CUDA")]
                if gpus:
                    for d in cprefs.devices:
                        d.use = (d.type in ("OPTIX", "CUDA"))
                    bpy.context.scene.cycles.device = "GPU"
                    print(f"[Studio] GPU Hızlandırma Aktif: {dev_type} ({[g.name for g in gpus]})")
                    return dev_type
            except Exception:
                continue
    except Exception as e:
        print(f"[Studio] GPU ayar uyarısı: {e}")
    return "CPU"


def upload_to_gcs(local_path: str, dest_blob: str, content_type: str) -> str:
    """Dosyayı gs://yuksektek-blender-films içine yükler ve public URL döndürür."""
    gcs_uri = f"gs://{BUCKET_NAME}/{dest_blob}"
    subprocess.check_call([
        "gcloud", "storage", "cp", local_path, gcs_uri,
        f"--content-type={content_type}",
        "--cache-control=no-cache,max-age=0"
    ])
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{dest_blob}"


def handle_get_scene_info():
    scn = bpy.context.scene
    objs = []
    for o in scn.objects:
        objs.append({
            "name": o.name,
            "type": o.type,
            "location": [round(x, 3) for x in o.location],
            "rotation_euler": [round(x, 3) for x in o.rotation_euler],
            "scale": [round(x, 3) for x in o.scale],
        })
    return {
        "status": "success",
        "scene": scn.name,
        "render_engine": scn.render.engine,
        "resolution": [scn.render.resolution_x, scn.render.resolution_y],
        "frame_start": scn.frame_start,
        "frame_end": scn.frame_end,
        "fps": scn.render.fps,
        "active_camera": scn.camera.name if scn.camera else None,
        "objects": objs
    }


def handle_get_object_info(params):
    name = params.get("name", "")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"status": "error", "message": f"Obje bulunamadı: {name}"}
    mats = [m.name for m in obj.data.materials if m] if hasattr(obj.data, "materials") else []
    return {
        "status": "success",
        "name": obj.name,
        "type": obj.type,
        "location": [round(x, 3) for x in obj.location],
        "rotation_euler": [round(x, 3) for x in obj.rotation_euler],
        "scale": [round(x, 3) for x in obj.scale],
        "dimensions": [round(x, 3) for x in obj.dimensions],
        "materials": mats
    }


def handle_execute_code(params):
    code = params.get("code", "")
    buf = io.StringIO()
    ns = {"bpy": bpy, "__builtins__": __builtins__}
    with redirect_stdout(buf):
        exec(code, ns)
    try:
        os.makedirs("/home/studio/projects", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath="/home/studio/projects/latest_autosave.blend")
    except Exception:
        pass
    # Redraw viewport if GUI is active
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        pass
    return {
        "status": "success",
        "output": buf.getvalue(),
        "scene_summary": handle_get_scene_info()
    }


def handle_render_preview_snapshot(params):
    shot_name = params.get("shot_name", f"snapshot_{int(time.time())}")
    shot_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in shot_name)
    samples = int(params.get("samples", 32))

    enable_gpu_rendering()
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "GPU"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    try:
        scn.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scn.render.resolution_x = 1280
    scn.render.resolution_y = 720
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = "PNG"

    local_out = f"/tmp/{shot_name}.png"
    scn.render.filepath = local_out
    bpy.ops.render.render(write_still=True)

    url = upload_to_gcs(local_out, f"previews/{shot_name}.png", "image/png")
    return {
        "status": "success",
        "shot_name": shot_name,
        "preview_url": url,
        "cinema_gallery_url": f"https://storage.googleapis.com/{BUCKET_NAME}/index.html"
    }


def handle_render_animation_mp4(params):
    film_name = params.get("film_name", f"film_{int(time.time())}")
    film_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in film_name)
    frame_start = int(params.get("frame_start", 1))
    frame_end = int(params.get("frame_end", 48))
    samples = int(params.get("samples", 16))

    enable_gpu_rendering()
    scn = bpy.context.scene
    scn.frame_start = frame_start
    scn.frame_end = frame_end
    scn.render.fps = 24
    scn.render.resolution_x = 1280
    scn.render.resolution_y = 720
    scn.render.resolution_percentage = 100

    # Her zaman NVIDIA OptiX/CUDA donanım hızlandırmalı CYCLES kullan
    scn.render.engine = "CYCLES"
    scn.cycles.device = "GPU"
    scn.cycles.samples = samples
    scn.cycles.max_bounces = 4
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.use_denoising = True
    try:
        scn.cycles.denoiser = "OPTIX"
    except Exception:
        scn.cycles.use_denoising = False

    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.ffmpeg.format = "MPEG4"
    scn.render.ffmpeg.codec = "H264"
    scn.render.ffmpeg.constant_rate_factor = "HIGH"
    scn.render.ffmpeg.ffmpeg_preset = "GOOD"

    local_mp4 = f"/tmp/{film_name}.mp4"
    scn.render.filepath = local_mp4
    bpy.ops.render.render(animation=True)

    url = upload_to_gcs(local_mp4, f"films/{film_name}.mp4", "video/mp4")
    return {
        "status": "success",
        "film_name": film_name,
        "frames_rendered": (frame_end - frame_start + 1),
        "duration_seconds": round((frame_end - frame_start + 1) / 24.0, 2),
        "film_download_and_watch_url": url,
        "cinema_gallery_url": f"https://storage.googleapis.com/{BUCKET_NAME}/index.html"
    }


def handle_search_polyhaven(params):
    asset_type = params.get("asset_type", "all")
    url = f"https://api.polyhaven.com/assets?t={asset_type}"
    if params.get("categories"):
        url += f"&c={params['categories']}"
    req = urllib.request.Request(url, headers={"User-Agent": "BlenderAIStudio/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    top_items = list(data.keys())[:25]
    return {"status": "success", "count": len(data), "sample_assets": top_items}


def handle_download_polyhaven(params):
    asset_id = params["asset_id"]
    asset_type = params["asset_type"]
    res = params.get("resolution", "2k")
    req = urllib.request.Request(f"https://api.polyhaven.com/files/{asset_id}", headers={"User-Agent": "BlenderAIStudio/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        files = json.loads(resp.read().decode("utf-8"))

    os.makedirs("/tmp/polyhaven", exist_ok=True)
    if asset_type == "hdris":
        dl_url = files["hdri"][res]["hdr"]["url"]
        local_hdr = f"/tmp/polyhaven/{asset_id}_{res}.hdr"
        urllib.request.urlretrieve(dl_url, local_hdr)
        world = bpy.context.scene.world or bpy.data.worlds.new("StudioWorld")
        bpy.context.scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        nt.nodes.clear()
        bg = nt.nodes.new(type="ShaderNodeBackground")
        env = nt.nodes.new(type="ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(local_hdr)
        out = nt.nodes.new(type="ShaderNodeOutputWorld")
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
        return {"status": "success", "message": f"HDRI gökyüzü yüklendi: {asset_id}"}
    return {"status": "success", "message": f"Asset bilgisi alındı: {asset_id}"}


def execute_command_on_main_thread(cmd_type: str, params: dict):
    touch_activity()
    try:
        if cmd_type == "get_scene_info":
            return handle_get_scene_info()
        elif cmd_type == "get_object_info":
            return handle_get_object_info(params)
        elif cmd_type == "execute_blender_code":
            return handle_execute_code(params)
        elif cmd_type == "render_preview_snapshot":
            return handle_render_preview_snapshot(params)
        elif cmd_type == "render_animation_mp4":
            return handle_render_animation_mp4(params)
        elif cmd_type == "search_polyhaven_assets":
            return handle_search_polyhaven(params)
        elif cmd_type == "download_polyhaven_asset":
            return handle_download_polyhaven(params)
        else:
            return {"status": "error", "message": f"Bilinmeyen komut: {cmd_type}"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


def timer_pump():
    while not cmd_queue.empty():
        cmd_type, params, res_q = cmd_queue.get()
        res = execute_command_on_main_thread(cmd_type, params)
        res_q.put(res)
    return 0.1


def client_handler(conn: socket.socket):
    try:
        data = conn.recv(262144)
        if not data:
            return
        req = json.loads(data.decode("utf-8"))
        cmd_type = req.get("type")
        params = req.get("params", {})
        res_q = queue.Queue()
        cmd_queue.put((cmd_type, params, res_q))
        result = res_q.get(timeout=1800)
        conn.sendall(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        try:
            conn.sendall(json.dumps(err).encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


def server_loop():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(8)
    print(f"[Studio] Blender MCP Sunucusu {HOST}:{PORT} üzerinde dinliyor...")
    while True:
        conn, _ = srv.accept()
        t = threading.Thread(target=client_handler, args=(conn,), daemon=True)
        t.start()


def start_studio_server():
    touch_activity()
    enable_gpu_rendering()
    t = threading.Thread(target=server_loop, daemon=True)
    t.start()
    bpy.app.timers.register(timer_pump, persistent=True)


if __name__ == "__main__":
    start_studio_server()
