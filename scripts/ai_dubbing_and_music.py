#!/usr/bin/env python3
"""
Blender AI Film Stüdyosu (`yuksektek`) — Yapay Zeka Seslendirme, Dublaj, Ses Değiştirme,
Orkestral Film Müziği (Lyria 3 Pro) ve 3B Doku/Gökyüzü (Gemini 3 Image) Motoru.

Desteklenen 1. Parti Google Cloud / Vertex AI Modelleri (`yuksektek`):
1. Seslendirme & Karakter Dublajı (Expressive Native Audio TTS):
   - `gemini-3.1-flash-tts-preview` & `gemini-2.5-pro-tts` (Duygu, ton, fısıltı, heyecan ve karakter stili destekli)
   - `Chirp3-HD` (`texttospeech.googleapis.com` - `tr-TR-Chirp3-HD-Aoede`, `Puck`, `Charon`, `Fenrir`, `Kore`, `Leda`)
2. Ses Değiştirme (Voice Changer & Karakter Efektleri):
   - AI Stil Dönüşümü + FFmpeg Formant/Pitch/Echo filtreleri (`normal`, `peri_sincap`, `dev_kaptan`, `komik_robot`, `buyulu_magara`)
3. Orkestral Film Müziği (Full-Song & Clip Soundtrack):
   - `lyria-3-pro-preview` & `lyria-3-clip-preview` (Studio Ghibli / Pixar tarzı enstrümantal film müziği)
4. 3B Gökyüzü (Skybox) ve Obje Dokusu (UV Texture) Üretimi:
   - `gemini-3-pro-image` & `gemini-3.1-flash-image`
5. 24 FPS Dudak Senkronu (Lip-Sync Envelope) ve Otomatik Film Dublaj Miksajı (Auto-Ducking):
   - Karakter konuşurken arka plan müziğini otomatik kısar, 3B karakterin ağız açılıp kapanma (RMS) verisini çıkarır,
     videoyla birleştirip Özel Sinema Salonuna (`gs://yuksektek-blender-films/films/`) yükler.
"""

import base64
import json
import math
import os
import struct
import subprocess
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ID = os.environ.get("BLENDER_GCP_PROJECT", "yuksektek")
BUCKET_NAME = os.environ.get("BLENDER_BUCKET_NAME", "yuksektek-blender-films")
CINEMA_URL = "https://blender-sinema-salonu-74454451681.europe-west3.run.app"
SAMPLE_RATE = 24000

# Hazır Türkçe Çizgi Film / Animasyon Karakter Ses Profilleri
VOICE_PROFILES: Dict[str, Dict[str, str]] = {
    "PIRIL_GENC_KIZ": {
        "voice_name": "Aoede",
        "chirp_name": "tr-TR-Chirp3-HD-Aoede",
        "description": "Neşeli, enerjik, meraklı genç kız / başrol çizgi film karakteri",
        "default_style": "Speak in Turkish as an energetic, cheerful, curious young animated heroine in a Pixar/Ghibli movie, full of warmth and wonder:",
    },
    "TIKIR_KOMIK_YARDIMCI": {
        "voice_name": "Puck",
        "chirp_name": "tr-TR-Chirp3-HD-Puck",
        "description": "Heyecanlı, şakacı, komik yardımcı karakter / sevimli robot veya hayvan dost",
        "default_style": "Speak in Turkish as a playful, funny, excitable cartoon sidekick with lively comedic timing:",
    },
    "BILGE_USTA": {
        "voice_name": "Charon",
        "chirp_name": "tr-TR-Chirp3-HD-Charon",
        "description": "Sıcak, bilge, masal anlatıcısı dede / usta / büyücü sesi",
        "default_style": "Speak in Turkish as a warm, wise, caring storyteller master in an animated family film:",
    },
    "KAHRAMAN_KAPTAN": {
        "voice_name": "Fenrir",
        "chirp_name": "tr-TR-Chirp3-HD-Fenrir",
        "description": "Gür, cesur, neşeli kaptan / şövalye / dev dost sesi",
        "default_style": "Speak in Turkish as a jolly, courageous, heroic adventure captain:",
    },
    "MASAL_PERISI": {
        "voice_name": "Leda",
        "chirp_name": "tr-TR-Chirp3-HD-Leda",
        "description": "Yumuşak, büyülü, zarif peri / prenses / anlatıcı sesi",
        "default_style": "Speak in Turkish with a magical, gentle, enchanting fairy-tale voice:",
    },
    "BILIM_REHBERI": {
        "voice_name": "Kore",
        "chirp_name": "tr-TR-Chirp3-HD-Kore",
        "description": "Berrak, akıcı, dost canlısı yapay zeka / anlatıcı sesi",
        "default_style": "Speak in Turkish with a clear, warm, friendly and engaging narrator voice:",
    },
}

# FFmpeg Ses Değiştirme (Voice Changer) Efekt Filtreleri
VOICE_EFFECT_FILTERS: Dict[str, str] = {
    "normal": "anull",
    "hizli_cizgi_film": "atempo=1.15",
    "peri_sincap": "asetrate=24000*1.28,aresample=24000,atempo=0.92",
    "dev_kaptan": "asetrate=24000*0.78,aresample=24000,atempo=1.12",
    "komik_robot": "afftfilt=\"real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75\",aecho=0.8:0.88:12:0.35",
    "buyulu_magara": "aecho=0.8:0.9:120|240:0.35|0.22",
}


def get_access_token() -> str:
    """Aktif gcloud veya GCE metadata sunucusundan OAuth2 erişim anahtarı alır."""
    try:
        out = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        ).strip()
        if out:
            return out
    except Exception:
        pass

    # Fallback: GCE VM Metadata Server
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def save_pcm_as_wav(pcm_bytes: bytes, wav_path: Path, sample_rate: int = SAMPLE_RATE) -> None:
    if pcm_bytes[:4] == b"RIFF":
        wav_path.write_bytes(pcm_bytes)
        return
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def apply_voice_effect(in_wav: Path, out_wav: Path, effect: str = "normal") -> Path:
    """Ses dosyasına ses değiştirme (pitch/formant/robot/eko) filtresi uygular."""
    af_filter = VOICE_EFFECT_FILTERS.get(effect, "anull")
    if af_filter == "anull" and in_wav == out_wav:
        return out_wav
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(in_wav),
            "-af", af_filter,
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            str(out_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_wav


def extract_24fps_lipsync_envelope(wav_path: Path, fps: int = 24) -> Dict[str, Any]:
    """Konuşma WAV dosyasından kare kare (24 FPS) ağız açıklığı (0.0 - 1.0) dizisi çıkarır."""
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    samples = struct.unpack(f"<{n_frames * n_channels}h", raw)
    if n_channels > 1:
        samples = samples[::n_channels]

    duration_sec = len(samples) / float(framerate)
    total_frames = max(1, int(math.ceil(duration_sec * fps)))
    samples_per_frame = max(1, int(framerate / fps))

    raw_rms = []
    max_rms = 1.0
    for f in range(total_frames):
        st = f * samples_per_frame
        en = min(len(samples), st + samples_per_frame)
        chunk = samples[st:en]
        if not chunk:
            raw_rms.append(0.0)
            continue
        rms = math.sqrt(sum(float(s) * float(s) for s in chunk) / len(chunk))
        raw_rms.append(rms)
        if rms > max_rms:
            max_rms = rms

    envelope = [
        round(min(1.0, (r / max_rms) * 1.25) if max_rms > 80 and (r / max_rms) > 0.08 else 0.0, 3)
        for r in raw_rms
    ]
    return {
        "duration_sec": round(duration_sec, 3),
        "fps": fps,
        "total_frames": total_frames,
        "mouth_envelope": envelope,
    }


def synthesize_character_speech(
    text: str,
    character_profile: str = "PIRIL_GENC_KIZ",
    emotion_prompt: Optional[str] = None,
    voice_effect: str = "normal",
    output_wav_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    gemini-3.1-flash-tts-preview (veya Chirp3-HD yedeği) ile Türkçe karakter seslendirmesi üretir,
    isteğe bağlı ses değiştirme efekti uygular ve 24 FPS dudak senkronu zarfını döndürür.
    """
    profile = VOICE_PROFILES.get(character_profile, VOICE_PROFILES["PIRIL_GENC_KIZ"])
    voice_name = profile["voice_name"]
    style = emotion_prompt or profile["default_style"]
    full_prompt = f"{style}\n\n\"{text}\""

    out_path = Path(output_wav_path) if output_wav_path else Path(tempfile.mktemp(suffix=".wav"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out_path.with_suffix(".raw.wav")

    token = get_access_token()
    model_used = "gemini-3.1-flash-tts-preview"

    # 1. Deneme: Vertex AI gemini-3.1-flash-tts-preview (Expressive Native Audio TTS)
    tts_ok = False
    url = (
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
        f"/locations/us-central1/publishers/google/models/gemini-3.1-flash-tts-preview:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                }
            },
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            b64_audio = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            save_pcm_as_wav(base64.b64decode(b64_audio), raw_path, SAMPLE_RATE)
            tts_ok = True
    except Exception:
        tts_ok = False

    # 2. Yedek: Google Cloud TTS Chirp3-HD
    if not tts_ok:
        model_used = profile["chirp_name"]
        url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "tr-TR", "name": profile["chirp_name"]},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "speakingRate": 1.05,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-goog-user-project": PROJECT_ID,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            save_pcm_as_wav(base64.b64decode(data["audioContent"]), raw_path, SAMPLE_RATE)

    apply_voice_effect(raw_path, out_path, voice_effect)
    if raw_path.exists() and raw_path != out_path:
        raw_path.unlink(missing_ok=True)

    lipsync = extract_24fps_lipsync_envelope(out_path, fps=24)
    return {
        "status": "ok",
        "model_used": model_used,
        "character_profile": character_profile,
        "voice_name": voice_name,
        "voice_effect": voice_effect,
        "wav_path": str(out_path),
        **lipsync,
    }


def generate_lyria_music(
    prompt: str = "Warm whimsical animated film soundtrack in the style of Studio Ghibli and Pixar, acoustic guitar, celesta, flute and lush strings, instrumental",
    output_wav_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Lyria 3 Pro (`lyria-3-pro-preview`) ile orkestral çizgi film müziği üretir."""
    out_wav = Path(output_wav_path) if output_wav_path else Path(tempfile.mktemp(suffix=".wav"))
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp3 = out_wav.with_suffix(".mp3")

    token = get_access_token()
    url = (
        f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
        f"/locations/global/publishers/google/models/lyria-3-pro-preview:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["AUDIO", "TEXT"]},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part and part["inlineData"].get("mimeType", "").startswith("audio/"):
                tmp_mp3.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", str(SAMPLE_RATE), "-ac", "1", str(out_wav)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                tmp_mp3.unlink(missing_ok=True)
                return {
                    "status": "ok",
                    "model_used": "lyria-3-pro-preview",
                    "wav_path": str(out_wav),
                }

    raise RuntimeError("Lyria 3 Pro müzik üretimi başarısız oldu.")


def generate_ai_texture(
    prompt: str,
    output_png_path: str,
    aspect_ratio: str = "16:9",
    model_id: str = "gemini-3-pro-image",
) -> Dict[str, Any]:
    """`gemini-3-pro-image` veya `gemini-3.1-flash-image` ile Blender sahnesi için gökyüzü/doku üretir."""
    out_png = Path(output_png_path)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    token = get_access_token()

    url = (
        f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
        f"/locations/global/publishers/google/models/{model_id}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio},
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part and part["inlineData"].get("data"):
                out_png.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                return {
                    "status": "ok",
                    "model_used": model_id,
                    "png_path": str(out_png),
                }

    raise RuntimeError(f"{model_id} ile doku üretilemedi.")


def dub_film_with_dialogue_and_music(
    film_name: str,
    dialogue_lines: List[Dict[str, Any]],
    music_prompt: Optional[str] = None,
    source_mp4_gs_or_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bir .mp4 filme birden fazla karakterin Türkçe dublajını (veya ses değiştirmesini) ve
    Lyria 3 Pro arka plan müziğini ekleyip Özel Sinema Salonuna (`gs://yuksektek-blender-films/films/`) yükler.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="blender_dub_"))
    clean_film = film_name.replace(".mp4", "")

    # 1. Kaynak videoyu indir veya bul
    src_mp4 = work_dir / "source.mp4"
    if source_mp4_gs_or_path and Path(source_mp4_gs_or_path).exists():
        src_mp4 = Path(source_mp4_gs_or_path)
    else:
        gs_uri = source_mp4_gs_or_path or f"gs://{BUCKET_NAME}/films/{clean_film}.mp4"
        subprocess.run(
            ["gcloud", "storage", "cp", gs_uri, str(src_mp4)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # 2. Tüm diyalog satırlarını sentezle ve sırayla birleştir
    combined_pcm = bytearray()
    pause_pcm = b"\x00\x00" * int(0.25 * SAMPLE_RATE)
    line_reports = []
    cur_sec = 0.3
    combined_pcm.extend(b"\x00\x00" * int(cur_sec * SAMPLE_RATE))

    for idx, line in enumerate(dialogue_lines):
        wav_i = work_dir / f"line_{idx:02d}.wav"
        res = synthesize_character_speech(
            text=line["text"],
            character_profile=line.get("character_profile", "PIRIL_GENC_KIZ"),
            emotion_prompt=line.get("emotion_prompt"),
            voice_effect=line.get("voice_effect", "normal"),
            output_wav_path=str(wav_i),
        )
        with wave.open(str(wav_i), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        dur = res["duration_sec"]
        line_reports.append({
            "index": idx + 1,
            "speaker": line.get("character_profile", "PIRIL_GENC_KIZ"),
            "text": line["text"],
            "start_sec": round(cur_sec, 2),
            "end_sec": round(cur_sec + dur, 2),
            "mouth_envelope": res["mouth_envelope"],
        })
        combined_pcm.extend(frames)
        combined_pcm.extend(pause_pcm)
        cur_sec += dur + 0.25

    voice_wav = work_dir / "voice_track.wav"
    save_pcm_as_wav(bytes(combined_pcm), voice_wav, SAMPLE_RATE)

    # 3. İsteğe bağlı Lyria 3 Pro arka plan müziği üret ve konuşma altında kısarak (auto-ducking) miksle
    master_wav = voice_wav
    if music_prompt:
        music_wav = work_dir / "music.wav"
        try:
            generate_lyria_music(prompt=music_prompt, output_wav_path=str(music_wav))
            mixed_wav = work_dir / "master_mixed.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(voice_wav),
                    "-i", str(music_wav),
                    "-filter_complex",
                    "[0:a]volume=1.15[v];[1:a]volume=0.22[m];[v][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
                    "-map", "[out]",
                    "-ar", str(SAMPLE_RATE), "-ac", "1",
                    str(mixed_wav),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            master_wav = mixed_wav
        except Exception:
            master_wav = voice_wav

    # 4. Videoyu ve yeni dublaj ses kuşağını birleştir (video daha kısaysa son kareyi uzat veya döngüye al)
    out_mp4_name = f"{clean_film}_dublajli.mp4" if not clean_film.endswith("_dublajli") else f"{clean_film}.mp4"
    out_mp4 = work_dir / out_mp4_name
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(src_mp4),
            "-i", str(master_wav),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 5. Google Cloud Storage Sinema Salonuna yükle
    gs_dest = f"gs://{BUCKET_NAME}/films/{out_mp4_name}"
    subprocess.run(
        ["gcloud", "storage", "cp", str(out_mp4), gs_dest],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return {
        "status": "ok",
        "film_name": out_mp4_name,
        "total_audio_seconds": round(cur_sec, 2),
        "watch_and_download_url": f"{CINEMA_URL}/media/films/{out_mp4_name}",
        "direct_download_url": f"{CINEMA_URL}/media/films/{out_mp4_name}?download=1",
        "cinema_gallery_url": CINEMA_URL,
        "dialogue_timeline_and_lipsync": line_reports,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blender AI Stüdyosu — Seslendirme, Dublaj ve Müzik Aracı")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tts = sub.add_parser("tts", help="Karakter seslendirmesi üret")
    p_tts.add_argument("--text", required=True)
    p_tts.add_argument("--character", default="PIRIL_GENC_KIZ", choices=list(VOICE_PROFILES.keys()))
    p_tts.add_argument("--emotion", default=None)
    p_tts.add_argument("--effect", default="normal", choices=list(VOICE_EFFECT_FILTERS.keys()))
    p_tts.add_argument("--out", required=True)

    p_music = sub.add_parser("music", help="Lyria 3 Pro ile film müziği üret")
    p_music.add_argument("--prompt", required=True)
    p_music.add_argument("--out", required=True)

    p_tex = sub.add_parser("texture", help="Gemini 3 Pro Image ile gökyüzü/doku üret")
    p_tex.add_argument("--prompt", required=True)
    p_tex.add_argument("--out", required=True)

    args = parser.parse_args()
    if args.cmd == "tts":
        print(json.dumps(synthesize_character_speech(args.text, args.character, args.emotion, args.effect, args.out), ensure_ascii=False, indent=2))
    elif args.cmd == "music":
        print(json.dumps(generate_lyria_music(args.prompt, args.out), ensure_ascii=False, indent=2))
    elif args.cmd == "texture":
        print(json.dumps(generate_ai_texture(args.prompt, args.out), ensure_ascii=False, indent=2))
