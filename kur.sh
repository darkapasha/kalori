#!/bin/bash
# Kalori uygulamasını kurar ya da günceller. Caddy'de yalnızca kendi bloğunu ekler.
set -e
cd ~/kalori
mkdir -p veri && chmod 700 veri
if [ ! -x venv/bin/uvicorn ]; then
  python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
fi
venv/bin/pip install -q fastapi 'uvicorn[standard]' pywebpush
# Gemini anahtarı botun .env dosyasından kopyalanır (ekrana yazılmaz)
if [ ! -s veri/.env ]; then
  grep '^GEMINI_API_KEY=' ~/mma_bot/.env > veri/.env || true
  chmod 600 veri/.env
fi
sudo cp kalori.service /etc/systemd/system/kalori.service
sudo systemctl daemon-reload
sudo systemctl enable kalori >/dev/null 2>&1
sudo systemctl restart kalori
if ! grep -q "kalori.SUNUCU-IP.sslip.io" /etc/caddy/Caddyfile; then
  sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.kalori-oncesi
  sudo tee -a /etc/caddy/Caddyfile >/dev/null <<'BLOK'

kalori.SUNUCU-IP.sslip.io {
	encode zstd gzip
	request_body {
		max_size 8MB
	}
	reverse_proxy 127.0.0.1:8096
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options nosniff
		Referrer-Policy no-referrer
		-Server
	}
}
BLOK
  if sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    sudo systemctl reload caddy; echo "caddy blogu eklendi"
  else
    sudo cp /etc/caddy/Caddyfile.kalori-oncesi /etc/caddy/Caddyfile; echo "CADDY HATASI: eski dosya geri konuldu"; exit 1
  fi
fi
sleep 3
systemctl is-active kalori caddy
K=$(cat veri/anahtar.txt)
echo "durum: $(curl -s -H "X-Anahtar: $K" http://127.0.0.1:8096/api/durum)"
echo "anahtarsiz: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8096/api/durum)"
