# 🍿 04. Stüdyo, Canlı Ekran ve Sinema Salonu Nasıl Çalışır?

Bu rehberde buluttaki **Blender AI Film Stüdyomuzun** nasıl çalıştığını, canlı ekranı nasıl izleyebileceğini ve çektiğin filmleri nasıl indirip arkadaşlarınla paylaşabileceğini tek bakışta göreceksin!

---

## ⚡ 1. Buluttaki Süper Bilgisayarın (`blender-studio`)
Senin kendi bilgisayarını hiç yormamak ve fanlarını bile çalıştırmamak için Google Cloud üzerinde dev bir stüdyo bilgisayarımız var:
* **Ekran Kartı (GPU):** NVIDIA L4 (24 GB VRAM) / RTX Ray-Tracing Hızlandırmalı
* **Program:** Blender 4.3 LTS (Stüdyo Sürümü)

### 💤 Otomatik Uyku Kalkanı (120 Dakika)
* Stüdyo bilgisayarımız **120 dakika (2 saat)** boyunca hiç kullanılmazsa doğayı ve bütçemizi korumak için kendi kendine **Uyku Moduna** geçer.
* Tekrar film yapmak istediğinde hiçbir tuşa basmana gerek yok! Antigravity'ye *"Stüdyoyu uyandır"* veya doğrudan *"Bana yeni bir sahne kur"* dediğinde Antigravity stüdyoyu **30 saniye içinde otomatik uyandırır**.

---

## 🖥️ 2. Canlı Stüdyo Ekranını İzleme (Remote Desktop)
Antigravity sahneyi kurarken nesnelerin Blender ekranında kendi kendine nasıl belirdiğini canlı izlemek veya fareyle kendin dokunmak istersen:

* 🌐 **Tarayıcıdan Tek Tıkla Canlı Ekran:**  
  👉 **[Canlı Blender Stüdyo Ekranını Aç (Port 6080)](http://35.246.180.235:6080/vnc.html?autoconnect=true&resize=scale)**  
  *(Hiçbir program indirmene gerek yok, doğrudan Chrome tarayıcında açılır! Güvenlik için sadece bizim ev internetimizden girilebilir.)*

---

## 🎬 3. Çekilen Filmleri İzleme ve İndirme (`yuksektek-blender-films`)
Antigravity her fotoğraf (`.png`) veya film (`.mp4`) çektiğinde bunu otomatik olarak Google Cloud üzerindeki **Özel Sinema Salonuna** yükler ve sohbet ekranında sana linkini verir:

* 🍿 **Sinema Salonu (Tüm Filmlerin ve Fotoğrafların):**  
  👉 **[Stüdyo Sinema Salonunu Aç](https://storage.googleapis.com/yuksektek-blender-films/index.html)**
* **Tek Tıkla İndir:** Linke tıkladığında filmin doğrudan tarayıcıda oynar; sağ alttaki **İndir** düğmesine basarak bilgisayarında veya telefonunda saklayabilir, arkadaşlarına gönderebilirsin!
