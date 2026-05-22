# Deploy via Portainer

## 1) Build image

Gunakan repo ini sebagai source build di Portainer atau build manual:

```bash
docker build -t fb-reels-telegram-bot:latest .
```

## 2) Jalankan container

Set environment variables berikut:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_USER_ID`
- `TELEGRAM_BANNER_URL` (opsional)
- `TELEGRAM_DEFAULT_WORKERS` (opsional)
- `TELEGRAM_DEFAULT_TARGET` (opsional)
- `FB_REELS_SESSION_FILE` (opsional)
- `FB_REELS_OUTPUT_DIR` (opsional)

## 3) Mount volume (direkomendasikan)

Persist session dan output scan:

- Host path: `/data/fb-reels-cli`  
  Container path: `/app/fb_reels_cli`

Dengan ini `session.json` dan folder `output/` tidak hilang saat restart.

## 4) Test cepat

1. Chat bot: `/start`
2. Login session Facebook via menu `🔐 Login Session Facebook`
3. Jalankan `🔎 Scan Reels Page`
4. Pilih nomor hasil untuk buka layer-2 detail
5. Di detail, pilih `🎬 Kirim Video (Best)` atau resolusi tertentu untuk kirim video+audio
