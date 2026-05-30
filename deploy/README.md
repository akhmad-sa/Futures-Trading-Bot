# Deployment — Futures Trading Bot

GitHub: https://github.com/akhmad-sa/Futures-Trading-Bot

---

## Contabo VPS (recommended — 4 vCPU / 8 GB / 150 GB)

Spesifikasi Anda lebih dari cukup untuk **website retail + paper trade 24/7** (live trade kecil–sedang di VPS yang sama juga masuk akal).

**Shared VPS (website + bot):** baca [`VPS-SHARED.md`](VPS-SHARED.md) — nginx, user `trader`, paper→live checklist.

| Setting | Rekomendasi |
|---------|-------------|
| **OS** | Ubuntu **24.04 LTS** (x86_64) |
| **Login** | `root@<IP>` (default Contabo) |
| **Timezone** | UTC (`timedatectl set-timezone UTC`) |
| **Path install (bot saja)** | `/root/futures-trading-bot` atau `/home/trader/futures-trading-bot` (disarankan jika + website) |
| **Swap** | Tidak perlu (8 GB RAM) |

### Install (one-liner)

SSH sebagai **root**, lalu:

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/contabo-init.sh | bash
```

Atau step-by-step:

```bash
apt update && apt install -y git curl
git clone --branch main https://github.com/akhmad-sa/Futures-Trading-Bot.git /root/futures-trading-bot
bash /root/futures-trading-bot/deploy/contabo-init.sh
```

### Setelah init (~3–5 menit)

```bash
cat /root/FUTURES-TRADING-BOT-SETUP.txt
tail -f /root/futures-trading-bot-init.log

nano /root/futures-trading-bot/.env
nano /root/futures-trading-bot/configs/strategy.env

# Backtest portfolio
cd /root/futures-trading-bot && source venv/bin/activate
python main.py -m backtest -s trendline_breakout --symbols BTCUSDT TRBUSDT DOGEUSDT

# Paper 24/7
systemctl enable --now futures-trading-bot-paper
journalctl -u futures-trading-bot-paper -f
```

### Update ke commit terbaru

```bash
bash /root/futures-trading-bot/deploy/contabo-init.sh
```

### Contabo panel (opsional)

- Aktifkan **backup/snapshot** di Customer Control Panel
- Firewall Contabo: allow **22** (SSH); bot hanya butuh **outbound** HTTPS (MEXC, Telegram)
- 150 GB: `data/candles/` aman untuk sync dataset lama (`DATASET_SYNC_ON_BACKTEST=true`)

---

## Oracle Cloud Always Free

| Setting | Value |
|---------|--------|
| **Image** | Ubuntu 24.04 (aarch64) |
| **Shape** | A1 Flex 1 OCPU / 6 GB |
| **Init** | [`oracle-cloud-init.yaml`](oracle-cloud-init.yaml) |

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/oracle-init.sh | sudo bash
```

---

## Systemd (manual)

```bash
./deploy/install-systemd.sh /root/futures-trading-bot root paper   # Contabo root
./deploy/install-systemd.sh /home/ubuntu/futures-trading-bot ubuntu paper
systemctl enable --now futures-trading-bot-paper
```

Live: ganti `paper` → `live` (dana real).

---

## Scripts

| File | Use |
|------|-----|
| [`contabo-init.sh`](contabo-init.sh) | Contabo / root / no swap |
| [`vps-init.sh`](vps-init.sh) | Generic VPS (env overrides) |
| [`oracle-init.sh`](oracle-init.sh) | Oracle (ubuntu user, 2G swap) |
| [`install-systemd.sh`](install-systemd.sh) | Install systemd units |
