# Deployment — Futures Trading Bot

GitHub: https://github.com/akhmad-sa/Futures-Trading-Bot

## Path layout (default — no `/root`)

| Variable | Default path |
|----------|----------------|
| `FTB_SERVICE_USER` | `fbot` |
| `FTB_INSTALL_DIR` | `/opt/futures-trading-bot` |
| `FTB_LOG_DIR` | `/var/log/futures-trading-bot` |
| `FTB_STATE_DIR` | `/var/lib/futures-trading-bot` |

Override on VPS: copy `deploy/deploy.env.example` → `/etc/futures-trading-bot/env`

After init, read: **`/opt/futures-trading-bot/deploy/SETUP-NOTES.txt`**

---

## Contabo VPS (4 vCPU / 8 GB / 150 GB)

SSH as **root** (first install only), then:

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/contabo-init.sh | bash
```

Or patch update (git pull + deps + restart active services):

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/patch-update.sh | sudo bash -s
# with options:
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/patch-update.sh | sudo bash -s -- --restart paper
```

Configure & start:

```bash
sudo nano /opt/futures-trading-bot/.env
sudo systemctl enable --now futures-trading-bot-paper
journalctl -u futures-trading-bot-paper -f
```

---

## Oracle Cloud Always Free

Paste [`oracle-cloud-init.yaml`](oracle-cloud-init.yaml) as initialization script, or:

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/oracle-init.sh | sudo bash
```

Uses **2G swap**; same `/opt` layout and user `fbot`.

---

## Shared VPS (website + bot)

See [`VPS-SHARED.md`](VPS-SHARED.md) — website in `/var/www/…`, bot stays under `/opt/futures-trading-bot`.

---

## Scripts

| File | Role |
|------|------|
| [`lib/defaults.sh`](lib/defaults.sh) | Dynamic paths (sourced by other scripts) |
| [`deploy.env.example`](deploy.env.example) | Template for `/etc/futures-trading-bot/env` |
| [`vps-init.sh`](vps-init.sh) | Core installer |
| [`contabo-init.sh`](contabo-init.sh) | Contabo (no swap) |
| [`oracle-init.sh`](oracle-init.sh) | Oracle (2G swap) |
| [`install-systemd.sh`](install-systemd.sh) | systemd units |
| [`patch-update.sh`](patch-update.sh) | Git pull, pip, restart services |
| [`adopt-git.sh`](adopt-git.sh) | One-time: turn existing install into git clone |

---

## Non-git install (`/opt/futures-trading-bot` tanpa `.git`)

Jika folder bot di-copy manual (bukan `git clone`), `git pull` dan `patch-update.sh` gagal.

**Sekali saja** (backup otomatis ke `/var/lib/futures-trading-bot/backups/`):

```bash
sudo bash /opt/futures-trading-bot/deploy/adopt-git.sh
```

Atau jika skrip belum ada di VPS, unduh dari GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/adopt-git.sh | sudo bash -s
```

Lalu update rutin:

```bash
sudo bash /opt/futures-trading-bot/deploy/patch-update.sh
```

**Manual tanpa skrip** (setelah backup `.env` dan `configs/`):

```bash
sudo systemctl stop futures-trading-bot-paper futures-trading-bot-telegram 2>/dev/null || true
sudo cp -a /opt/futures-trading-bot/.env /tmp/ftb-env.bak
sudo cp -a /opt/futures-trading-bot/configs /tmp/ftb-configs.bak

# Wajib: fbot harus bisa menulis di folder app
sudo chown -R fbot:fbot /opt/futures-trading-bot

sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && git init -b main'
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && git remote add origin https://github.com/akhmad-sa/Futures-Trading-Bot.git'
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && git fetch --depth 1 origin main'
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && git checkout -f -B main origin/main'

sudo cp -a /tmp/ftb-env.bak /opt/futures-trading-bot/.env
sudo cp -a /tmp/ftb-configs.bak/. /opt/futures-trading-bot/configs/
sudo chown -R fbot:fbot /opt/futures-trading-bot

sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && ./venv/bin/pip install -r requirements.txt'
sudo systemctl start futures-trading-bot-paper
```

Jika `pip` masih gagal, **venv** dibuat sebagai root — buat ulang sebagai `fbot`:

```bash
sudo rm -rf /opt/futures-trading-bot/venv
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && python3.12 -m venv venv'
sudo -u fbot bash -lc 'cd /opt/futures-trading-bot && ./venv/bin/pip install -r requirements.txt'
```

Cek ownership venv:

```bash
ls -la /opt/futures-trading-bot/venv/lib/python3.12/site-packages | head -3
```

---

```bash
# Patch update (preferred for code changes)
sudo /opt/futures-trading-bot/deploy/patch-update.sh
sudo /opt/futures-trading-bot/deploy/patch-update.sh --restart paper
sudo /opt/futures-trading-bot/deploy/patch-update.sh --systemd telegram --no-restart

# Manual systemd (uses defaults from lib/defaults.sh)
sudo /opt/futures-trading-bot/deploy/install-systemd.sh
sudo systemctl enable --now futures-trading-bot-paper
```

Live: `install-systemd.sh '' '' live` or third arg `live`.

Telegram control: `install-systemd.sh '' '' telegram` (installs sudoers + `futures-trading-bot-telegram.service`).
