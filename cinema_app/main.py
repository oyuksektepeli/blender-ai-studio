import json
import os
import urllib.error
import urllib.request
from datetime import timedelta
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from google.cloud import storage

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY", "yuksektek-blender-cinema-secret-2026-key"
)
app.permanent_session_lifetime = timedelta(days=365)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "yuksektek-blender-films")
IDENTITY_API_KEY = os.environ.get(
    "IDENTITY_API_KEY", "AIzaSyASad5v35wA39G0dlWzYIpyk0oLoek-aBQ"
)
ALLOWED_EMAILS = {
    "nyletitgo@gmail.com",
    "onur@mamentis.com",
}

storage_client = storage.Client()


def get_logged_in_user():
    email = session.get("user_email", "").strip().lower()
    if email in ALLOWED_EMAILS:
        return email
    return None


def format_size_tr(size_bytes):
    n = float(size_bytes or 0)
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def list_gallery_items():
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = list(bucket.list_blobs())
    blobs.sort(key=lambda b: b.updated.timestamp() if b.updated else 0, reverse=True)

    films = []
    previews = []
    for b in blobs:
        clean_name = b.name.split("/")[-1]
        updated_str = b.updated.strftime("%d.%m.%Y %H:%M") if b.updated else ""
        entry = {
            "name": b.name,
            "clean_name": clean_name,
            "size": b.size or 0,
            "size_human": format_size_tr(b.size),
            "updated": b.updated.isoformat() if b.updated else "",
            "updated_human": updated_str,
        }
        if b.name.endswith(".mp4"):
            films.append(entry)
        elif b.name.endswith(".png") or b.name.endswith(".jpg"):
            previews.append(entry)
    return films, previews


LOGIN_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>🎬 Özel Sinema Salonu — Yönetmen Girişi</title>
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
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .login-card {
      width: 100%;
      max-width: 430px;
      background: rgba(21, 25, 43, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 24px;
      padding: 2.2rem 2rem;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
      text-align: center;
    }
    .badge {
      display: inline-block;
      padding: 0.35rem 0.85rem;
      border-radius: 999px;
      background: rgba(124, 92, 255, 0.2);
      border: 1px solid rgba(124, 92, 255, 0.45);
      color: #d7ceff;
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 1rem;
    }
    h1 {
      font-size: 1.75rem;
      background: linear-gradient(90deg, #ff7eb3, #a18cd1, #fbc2eb);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.5rem;
    }
    p.sub { color: var(--muted); font-size: 0.95rem; margin-bottom: 1.5rem; }
    form { display: flex; flex-direction: column; gap: 1rem; text-align: left; }
    label { font-size: 0.85rem; color: var(--muted); font-weight: 600; }
    input {
      width: 100%;
      padding: 0.8rem 1rem;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.15);
      background: rgba(11, 12, 20, 0.8);
      color: var(--text);
      font-size: 1rem;
      margin-top: 0.35rem;
    }
    input:focus { outline: 2px solid var(--accent2); border-color: transparent; }
    button {
      margin-top: 0.5rem;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #fff;
      border: none;
      padding: 0.85rem;
      border-radius: 12px;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
    }
    .error {
      background: rgba(255, 75, 75, 0.15);
      border: 1px solid rgba(255, 75, 75, 0.4);
      color: #ffb3b3;
      padding: 0.75rem;
      border-radius: 12px;
      font-size: 0.9rem;
      margin-bottom: 1rem;
    }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="badge">🔒 Google Cloud Identity Korumalı</div>
    <h1>🎬 Özel Sinema Salonu</h1>
    <p class="sub">Filmleri izlemek ve indirmek için yönetmen hesabınla giriş yap.</p>
    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST" action="/login">
      <input type="hidden" name="next" value="{{ next_url }}" />
      <div>
        <label>Google E-Posta Adresi</label>
        <input type="email" name="email" placeholder="nyletitgo@gmail.com" value="nyletitgo@gmail.com" required />
      </div>
      <div>
        <label>Stüdyo Şifresi</label>
        <input type="password" name="password" placeholder="••••••••" required autofocus />
      </div>
      <button type="submit">🍿 Sinema Salonuna Gir</button>
    </form>
  </div>
</body>
</html>
"""

GALLERY_HTML = """<!DOCTYPE html>
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
      gap: 0.6rem;
      padding: 0.4rem 0.9rem;
      border-radius: 999px;
      background: rgba(124, 92, 255, 0.18);
      border: 1px solid rgba(124, 92, 255, 0.45);
      color: #d7ceff;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 0.9rem;
    }
    .user-badge a { color: #ff9ec4; text-decoration: none; margin-left: 0.4rem; }
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
    a.btn, button.btn {
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: white;
      border: none;
      padding: 0.7rem 1.4rem;
      border-radius: 999px;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.95rem;
      text-decoration: none;
      display: inline-block;
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
    <div class="user-badge">
      🔒 Özel Yönetmen Oturumu: {{ user_email }}
      <a href="/logout">(Çıkış)</a>
    </div>
    <h1>🎬 Özel Animasyon & Film Sinema Salonu</h1>
    <p class="subtitle">Blender 5.2 AI Stüdyosu'nda çektiğin tüm filmler ve sahne fotoğrafları yalnızca senin hesabına özel olarak burada yayınlanır.</p>
    <div class="controls">
      <a class="btn" href="/">🔄 Yeni Çekimleri Yenile</a>
    </div>
  </header>

  <main>
    <h2 class="section-title">🍿 Çekilen Kısa Filmler (.mp4)</h2>
    <div id="films-grid" class="grid">
      {% if films %}
        {% for item in films %}
          <div class="card">
            <video controls preload="metadata" src="/media/{{ item.name }}"></video>
            <div class="card-body">
              <div class="card-title">🎞️ {{ item.clean_name }}</div>
              <div class="card-meta">📅 {{ item.updated_human }} • 📦 {{ item.size_human }}</div>
              <div class="card-actions">
                <a class="primary" href="/media/{{ item.name }}?download=1">⬇️ Filmi İndir</a>
                <a href="/media/{{ item.name }}" target="_blank">🔍 Tam Ekran</a>
              </div>
            </div>
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">Henüz bir .mp4 film çekilmedi.</div>
      {% endif %}
    </div>

    <h2 class="section-title">📸 Sahne Önizleme Fotoğrafları (.png)</h2>
    <div id="previews-grid" class="grid">
      {% if previews %}
        {% for item in previews %}
          <div class="card">
            <a href="/media/{{ item.name }}" target="_blank">
              <img loading="lazy" src="/media/{{ item.name }}" alt="{{ item.clean_name }}" />
            </a>
            <div class="card-body">
              <div class="card-title">🖼️ {{ item.clean_name }}</div>
              <div class="card-meta">📅 {{ item.updated_human }} • 📦 {{ item.size_human }}</div>
              <div class="card-actions">
                <a class="primary" href="/media/{{ item.name }}?download=1">⬇️ Fotoğrafı İndir</a>
                <a href="/media/{{ item.name }}" target="_blank">🔍 Büyüt</a>
              </div>
            </div>
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">Henüz bir sahne fotoğrafı çekilmedi.</div>
      {% endif %}
    </div>
  </main>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next") or "/"
    if request.method == "GET":
        if get_logged_in_user():
            return redirect(next_url)
        return render_template_string(LOGIN_HTML, error=None, next_url=next_url)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if email not in ALLOWED_EMAILS:
        return render_template_string(
            LOGIN_HTML,
            error="Bu e-posta adresinin özel sinema salonuna giriş yetkisi yok.",
            next_url=next_url,
        )

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={IDENTITY_API_KEY}"
    payload = json.dumps(
        {"email": email, "password": password, "returnSecureToken": True}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            auth_data = json.loads(resp.read().decode("utf-8"))
            verified_email = auth_data.get("email", "").lower()
            if verified_email in ALLOWED_EMAILS:
                session.permanent = True
                session["user_email"] = verified_email
                return redirect(next_url)
    except urllib.error.HTTPError:
        pass

    return render_template_string(
        LOGIN_HTML,
        error="E-posta veya şifre hatalı. Lütfen tekrar dene.",
        next_url=next_url,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    user_email = get_logged_in_user()
    if not user_email:
        return redirect(url_for("login", next="/"))
    films, previews = list_gallery_items()
    return render_template_string(
        GALLERY_HTML, user_email=user_email, films=films, previews=previews
    )


@app.route("/api/items")
def api_items():
    user_email = get_logged_in_user()
    if not user_email:
        abort(401)
    films, previews = list_gallery_items()
    return jsonify({"films": films, "previews": previews})


@app.route("/media/<path:blob_path>")
def serve_media(blob_path: str):
    user_email = get_logged_in_user()
    if not user_email:
        return redirect(url_for("login", next=request.full_path))
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
