# VPS shared: website retail + Futures Trading Bot

Contabo **4 vCPU / 8 GB / 150 GB** cukup untuk **website retail ringan–sedang** + **paper trade 24/7**. Live trade di VPS yang sama **bisa**, asal isolasi dan checklist diikuti.

---

## Arsitektur (satu VPS)

```text
Internet
   │
   ├── :443 / :80  ──► nginx ──► website retail (/var/www/retail)
   │                      └── certbot (Let's Encrypt)
   │
   └── outbound HTTPS ──► MEXC/ccxt, Telegram (bot — tidak perlu port publik)

systemd (internal):
   ├── nginx
   ├── php-fpm / node (jika CMS/e-commerce)
   ├── futures-trading-bot-paper   ← fase uji
   └── futures-trading-bot-live    ← hanya satu yang active (jangan keduanya)
```

Bot **tidak** diekspos ke internet. Hanya website yang punya inbound 80/443.

---

## Alokasi resource (8 GB RAM)

| Layanan | Perkiraan RAM | Catatan |
|---------|---------------|---------|
| nginx + website (WordPress/WooCommerce ringan) | 512 MB – 1.5 GB | Cache plugin, jangan terlalu banyak plugin |
| PHP-FPM / Node | 256 MB – 1 GB | batasi `pm.max_children` |
| **Paper bot** | 300 – 600 MB | polling bar + MTF |
| **Live bot** | sama + sedikit DB I/O | jangan jalankan paper + live bersamaan |
| Backtest manual | spike 1–2 GB | jalankan off-peak atau `nice` |
| OS + headroom | ~1.5 GB | |

**Praktis:** website + **satu** mode bot (paper **atau** live) = aman di 8 GB. Hindari backtest portfolio besar saat traffic website puncak.

---

## Layout direktori (disarankan)

```text
/var/www/retail/              # website (owner: www-data atau deploy user)
/home/trader/futures-trading-bot/   # bot (owner: user trader, bukan root)
/home/trader/futures-trading-bot/.env          # secrets — chmod 600
/home/trader/futures-trading-bot/data/candles/ # dataset (bisa besar, 150 GB OK)
```

Buat user khusus bot (lebih aman untuk live):

```bash
adduser --disabled-password --gecos "" trader
# deploy bot ke /home/trader/futures-trading-bot
# RUN_USER=trader INSTALL_DIR=/home/trader/futures-trading-bot bash deploy/vps-init.sh
```

---

## Website retail (nginx)

Contoh site minimal (`/etc/nginx/sites-available/retail`):

```nginx
server {
    listen 80;
    server_name tokoku.example.com;
    root /var/www/retail/public;
    index index.html index.php;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    # PHP (jika WordPress/Laravel):
    # location ~ \.php$ {
    #     include snippets/fastcgi-php.conf;
    #     fastcgi_pass unix:/run/php/php8.3-fpm.sock;
    # }
}

# Setelah DNS mengarah ke VPS:
# certbot --nginx -d tokoku.example.com
```

Firewall:

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

---

## Bot: paper → live (workflow)

### Fase 1 — Paper (mingguan, parallel dengan website)

```bash
# Hanya paper service
systemctl disable --now futures-trading-bot-live 2>/dev/null || true
systemctl enable --now futures-trading-bot-paper
journalctl -u futures-trading-bot-paper -f
```

Pantau: Telegram, `journalctl`, drawdown virtual, frekuensi trade, error API.

### Fase 2 — Kriteria naik live

- [ ] Paper ≥ 2–4 minggu tanpa crash systemd
- [ ] PnL virtual & drawdown sesuai toleransi (`configs/risk.env`)
- [ ] Symbol & config sama dengan yang ingin dipakai live
- [ ] API key MEXC: **permission trade only**, withdraw disabled, IP whitelist jika ada
- [ ] Modal live kecil dulu (`BACKTEST_INITIAL_CAPITAL` / sizing di risk)
- [ ] Backup `.env` + `configs/` + snapshot VPS Contabo

### Fase 3 — Switch ke live

```bash
systemctl stop futures-trading-bot-paper
systemctl disable futures-trading-bot-paper

# pastikan .env & configs final
nano /home/trader/futures-trading-bot/.env

./deploy/install-systemd.sh /home/trader/futures-trading-bot trader live
systemctl enable --now futures-trading-bot-live
journalctl -u futures-trading-bot-live -f
```

**Jangan** enable paper dan live bersamaan — keduanya bisa buka posisi ganda.

---

## Keamanan (website + uang real)

| Area | Rekomendasi |
|------|-------------|
| User bot | Dedicated `trader`, bukan `root` |
| `.env` | `chmod 600`, tidak di web root |
| Website | Update CMS/plugin; fail2ban untuk SSH + nginx |
| MEXC API | Key terpisah paper vs live jika exchange mengizinkan; no withdraw |
| SSH | Key only, disable password login |
| Monitoring | Telegram alert + Contabo snapshot mingguan |

---

## Kapan pisah ke VPS kedua?

Pertimbangkan VPS bot terpisah jika:

- Website traffic tinggi (RAM > 70% stabil)
- Live trade modal besar / banyak symbol
- Butuh uptime bot 99.9% terpisah dari maintenance website

Untuk retail kecil + 1–3 symbol futures, **satu VPS Contabo 8 GB masih masuk akal**.

---

## Cron opsional

```bash
# Backup config harian
0 3 * * * tar czf /root/backup/fbot-$(date +\%F).tar.gz \
  /home/trader/futures-trading-bot/.env \
  /home/trader/futures-trading-bot/configs \
  /home/trader/futures-trading-bot/storage/trade_history.db 2>/dev/null
```

---

## Init bot di VPS shared

```bash
# sebagai root
export RUN_USER=trader
export INSTALL_DIR=/home/trader/futures-trading-bot
adduser --disabled-password --gecos "" trader 2>/dev/null || true
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/vps-init.sh | bash
```

Website setup terpisah (nginx, `/var/www/retail`) — tidak bentrok dengan path bot.
