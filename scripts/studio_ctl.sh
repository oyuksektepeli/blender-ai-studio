#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="yuksektek"
INSTANCE_NAME="blender-studio"
BUCKET_NAME="yuksektek-blender-films"

get_zone_and_ip() {
  gcloud compute instances list --project="$PROJECT_ID" --filter="name=$INSTANCE_NAME" \
    --format="value(zone,status,networkInterfaces[0].accessConfigs[0].natIP)"
}

case "${1:-status}" in
  status)
    echo "🎬 Blender AI Film Stüdyosu Durumu Kontrol Ediliyor..."
    read -r ZONE STATUS IP <<< "$(get_zone_and_ip)"
    echo "  • Sunucu: $INSTANCE_NAME ($ZONE)"
    echo "  • Durum:  $STATUS"
    echo "  • IP:     ${IP:-Uyku Modunda}"
    echo "  • Canlı Masaüstü: http://${IP:-35.246.180.235}:6080/vnc.html?autoconnect=true&resize=scale"
    echo "  • Sinema Salonu:  https://storage.googleapis.com/$BUCKET_NAME/index.html"
    ;;
  start|wake)
    read -r ZONE STATUS IP <<< "$(get_zone_and_ip)"
    if [[ "$STATUS" != "RUNNING" ]]; then
      echo "🚀 Stüdyo uyandırılıyor ($ZONE)..."
      gcloud compute instances start "$INSTANCE_NAME" --project="$PROJECT_ID" --zone="$ZONE"
    fi
    read -r ZONE STATUS IP <<< "$(get_zone_and_ip)"
    echo "✅ Stüdyo Açık! IP: $IP"
    echo "🌐 Canlı Ekran: http://$IP:6080/vnc.html?autoconnect=true&resize=scale"
    ;;
  stop|sleep)
    read -r ZONE STATUS IP <<< "$(get_zone_and_ip)"
    echo "💤 Stüdyo uyku moduna alınıyor..."
    gcloud compute instances stop "$INSTANCE_NAME" --project="$PROJECT_ID" --zone="$ZONE"
    echo "✅ Stüdyo güvenli şekilde uyutuldu."
    ;;
  films)
    echo "🍿 Sinema Salonundaki Filmler ve Fotoğraflar:"
    gcloud storage ls "gs://$BUCKET_NAME/**" | sed "s|gs://$BUCKET_NAME/|https://storage.googleapis.com/$BUCKET_NAME/|g"
    ;;
esac
