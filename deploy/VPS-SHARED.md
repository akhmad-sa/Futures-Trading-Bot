# VPS shared: website retail + Futures Trading Bot

Contabo **4 vCPU / 8 GB / 150 GB** — website + paper/live bot on one machine.

---

## Directory layout

```text
/var/www/retail/                 # website (nginx, www-data or deploy user)
/opt/futures-trading-bot/        # bot app (user: fbot) — NOT /root
/var/log/futures-trading-bot/    # init log
/var/lib/futures-trading-bot/    # fbot home / state
/etc/futures-trading-bot/env     # optional path overrides
```

Install bot first (or after website — order does not matter):

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/contabo-init.sh | bash
```

Custom paths (example):

```bash
sudo mkdir -p /etc/futures-trading-bot
sudo cp /opt/futures-trading-bot/deploy/deploy.env.example /etc/futures-trading-bot/env
sudo nano /etc/futures-trading-bot/env
# FTB_INSTALL_DIR=/opt/futures-trading-bot
# FTB_SERVICE_USER=fbot
sudo bash /opt/futures-trading-bot/deploy/vps-init.sh
```

---

## nginx (website only — ports 80/443)

```nginx
server {
    listen 80;
    server_name tokoku.example.com;
    root /var/www/retail/public;
    index index.html index.php;
    location / { try_files $uri $uri/ /index.php?$query_string; }
}
```

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

Bot uses **outbound HTTPS only** — no public port for trading.

---

## Paper → live

```bash
# Paper only
sudo systemctl enable --now futures-trading-bot-paper

# Switch to live (stop paper first)
sudo systemctl stop futures-trading-bot-paper
sudo systemctl disable futures-trading-bot-paper
sudo /opt/futures-trading-bot/deploy/install-systemd.sh '' '' live
sudo systemctl enable --now futures-trading-bot-live
```

Edit secrets:

```bash
sudo nano /opt/futures-trading-bot/.env
sudo nano /opt/futures-trading-bot/configs/risk.env
```

---

## Resource budget (8 GB)

| Service | RAM |
|---------|-----|
| nginx + retail CMS | ~0.5–1.5 GB |
| bot (paper or live) | ~0.3–0.6 GB |
| headroom | ~1.5 GB+ |

Run heavy **portfolio backtest** off-peak:

```bash
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && source venv/bin/activate && python main.py -m backtest -s trendline_breakout --symbols BTCUSDT TRBUSDT'
```

---

## Backup

```bash
sudo mkdir -p /var/backups/futures-trading-bot
sudo tar czf /var/backups/futures-trading-bot/config-$(date +%F).tar.gz \
  /opt/futures-trading-bot/.env \
  /opt/futures-trading-bot/configs \
  /opt/futures-trading-bot/storage/trade_history.db 2>/dev/null || true
```
