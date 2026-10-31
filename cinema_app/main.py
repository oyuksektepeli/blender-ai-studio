import os
from flask import Flask, Response, abort, jsonify, render_template_string, request
from google.cloud import storage

app = Flask(__name__)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "yuksektek-blender-films")
ALLOWED_EMAILS = {
    email.strip().lower()
    for email in os.environ.get(
        "ALLOWED_EMAILS", "nyletitgo@gmail.com,onur@mamentis.com"
    ).split(",")
    if email.strip()
}

storage_client = storage.Client()


def get_authenticated_email() -> str:
    raw = request.headers.get("X-Goog-Authenticated-User-Email", "")
    # IAP format: "accounts.google.com:nyletitgo@gmail.com"
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    return raw.strip().lower()


def verify_user():
    email = get_authenticated_email()
    if email and email not in ALLOWED_EMAILS:
        abort(403, description=f"Bu özel sinema salonuna erişim yetkiniz yok ({email}).")
    return email or "Özel Yönetmen (Google Auth)"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>🎬 Özel Animasyon & Film Sinema Salonu</title>
  <style>
    :root {
      --bg: #0b0c14;
      --card: #15192b;
      --accent: #ff5e97;
      --accent2: #7c5cff;
      --text: #f3f4f8;
      --muted: #9ba1b7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: radial-gradient(circle at top, #1b1e38 0%, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem;
    }
    header {
      max-width: 1200px;
      margin: 0 auto 2.5rem auto;
      text-align: center;
      padding: 2rem;
      background: rgba(21, 25, 43, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      backdrop-filter: blur(12px);
    }
    .user-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.4rem 0.9rem;
      border-radius: 999px;
      background: rgba(124, 92, 255, 0.18);
      border: 1px solid rgba(124, 92, 255, 0.45);
      color: #d7ceff;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 0.9rem;
    }
    h1 {
      font-size: 2.3rem;
      background: linear-gradient(90deg, #ff7eb3, #a18cd1, #fbc2eb);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.5rem;
    }
    p.subtitle { color: var(--muted); font-size: 1.05rem; }
    .controls {
      margin-top: 1.2rem;
      display: flex;
      gap: 1rem;
      justify-content: center;
      flex-wrap: wrap;
    }
    button.btn {
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: white;
      border: none;
      padding: 0.7rem 1.4rem;
      border-radius: 999px;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.95rem;
    }
    main { max-width: 1200px; margin: 0 auto; }
    h2.section-title {
      font-size: 1.4rem;
      margin: 2rem 0 1rem 0;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 1.5rem;
    }
    .card {
      background: var(--card);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 18px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
    }
    .card video, .card img {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      background: #000;
    }
    .card-body {
      padding: 1rem 1.2rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .card-title { font-weight: 700; font-size: 1.05rem; word-break: break-all; }
    .card-meta { color: var(--muted); font-size: 0.85rem; }
    .card-actions { display: flex; gap: 0.6rem; margin-top: 0.4rem; }
    .card-actions a {
      flex: 1;
      text-align: center;
      text-decoration: none;
      padding: 0.55rem 0.8rem;
      border-radius: 10px;
      font-size: 0.9rem;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.08);
      color: var(--text);
    }
    .card-actions a.primary {
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #fff;
    }
    .empty {
      padding: 2rem;
      text-align: center;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.03);
      border-radius: 16px;
    }
  </style>
</head>
<body>
  <header>
    <div class="user-badge">🔒 Google Auth Korumalı Özel Salon • {{ user_email }}</div>
    <h1>🎬 Özel Animasyon & Film Sinema Salonu</h1>
    <p class="subtitle">Blender 5.2 AI Stüdyosu'nda çektiğin tüm filmler ve sahne fotoğrafları yalnızca senin Google hesabına özel olarak burada yayınlanır.</p>
    <div class="controls">
      <button class="btn" onclick="loadGallery()">🔄 Yeni Çekimleri Yenile</button>
    </div>
  </header>

  <main>
    <h2 class="section-title">🍿 Çekilen Kısa Filmler (.mp4)</h2>
    <div id="films-grid" class="grid"><div class="empty">Filmler yükleniyor...</div></div>

    <h2 class="section-title">📸 Sahne Önizleme Fotoğrafları (.png)</h2>
    <div id="previews-grid" class="grid"><div class="empty">Fotoğraflar yükleniyor...</div></div>
  </main>

  <script>
    function formatSize(bytes) {
      const n = Number(bytes || 0);
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      return (n / (1024 * 1024)).toFixed(2) + ' MB';
    }
    function formatDate(iso) {
      if (!iso) return '';
      return new Date(iso).toLocaleString('tr-TR');
    }
    async function loadGallery() {
      const filmsGrid = document.getElementById('films-grid');
      const previewsGrid = document.getElementById('previews-grid');
      try {
        const res = await fetch('/api/items');
        const data = await res.json();
        const films = data.films || [];
        const previews = data.previews || [];

        if (films.length === 0) {
          filmsGrid.innerHTML = '<div class="empty">Henüz bir .mp4 film çekilmedi. Antigravity\'ye "Kamerayı döndür ve 5 saniyelik film çek!" diyebilirsin.</div>';
        } else {
          filmsGrid.innerHTML = films.map(item => {
            const cleanName = item.name.replace('films/', '');
            return `
              <div class="card">
                <video controls preload="metadata" src="/media/${encodeURIComponent(item.name)}"></video>
                <div class="card-body">
                  <div class="card-title">🎞️ ${cleanName}</div>
                  <div class="card-meta">📅 ${formatDate(item.updated)} • 📦 ${formatSize(item.size)}</div>
                  <div class="card-actions">
                    <a class="primary" href="/media/${encodeURIComponent(item.name)}?download=1">⬇️ Filmi İndir</a>
                    <a href="/media/${encodeURIComponent(item.name)}" target="_blank">🔍 Tam Ekran</a>
                  </div>
                </div>
              </div>
            `;
          }).join('');
        }

        if (previews.length === 0) {
          previewsGrid.innerHTML = '<div class="empty">Henüz bir sahne fotoğrafı çekilmedi. Antigravity\'ye "Sahnemin fotoğrafını çek!" diyebilirsin.</div>';
        } else {
          previewsGrid.innerHTML = previews.map(item => {
            const cleanName = item.name.replace('previews/', '');
            return `
              <div class="card">
                <a href="/media/${encodeURIComponent(item.name)}" target="_blank">
                  <img loading="lazy" src="/media/${encodeURIComponent(item.name)}" alt="${cleanName}" />
                </a>
                <div class="card-body">
                  <div class="card-title">🖼️ ${cleanName}</div>
                  <div class="card-meta">📅 ${formatDate(item.updated)} • 📦 ${formatSize(item.size)}</div>
                  <div class="card-actions">
                    <a class="primary" href="/media/${encodeURIComponent(item.name)}?download=1">⬇️ Fotoğrafı İndir</a>
                    <a href="/media/${encodeURIComponent(item.name)}" target="_blank">🔍 Büyüt</a>
                  </div>
                </div>
              </div>
            `;
          }).join('');
        }
      } catch (err) {
        filmsGrid.innerHTML = `<div class="empty">Galeri yüklenirken hata oluştu: ${err.message}</div>`;
      }
    }
    loadGallery();
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    user_email = verify_user()
    return render_template_string(HTML_TEMPLATE, user_email=user_email)


@app.route("/api/items")
def api_items():
    verify_user()
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = list(bucket.list_blobs())
    blobs.sort(key=lambda b: b.updated or 0, reverse=True)

    films = []
    previews = []
    for b in blobs:
        entry = {
            "name": b.name,
            "size": b.size,
            "updated": b.updated.isoformat() if b.updated else "",
        }
        if b.name.endswith(".mp4"):
            films.append(entry)
        elif b.name.endswith(".png") or b.name.endswith(".jpg"):
            previews.append(entry)

    return jsonify({"films": films, "previews": previews})


@app.route("/media/<path:blob_path>")
def serve_media(blob_path: str):
    verify_user()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_path)
    if not blob.exists():
        abort(404)
    blob.reload()
    data = blob.download_as_bytes()
    content_type = blob.content_type or (
        "video/mp4" if blob_path.endswith(".mp4") else "image/png"
    )
    headers = {}
    filename = os.path.basename(blob_path)
    if request.args.get("download") == "1":
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return Response(data, mimetype=content_type, headers=headers)
