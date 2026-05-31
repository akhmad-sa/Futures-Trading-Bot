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

Or re-run update:

```bash
sudo bash /opt/futures-trading-bot/deploy/contabo-init.sh
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

```bash
# Manual systemd (uses defaults from lib/defaults.sh)
sudo /opt/futures-trading-bot/deploy/install-systemd.sh
sudo systemctl enable --now futures-trading-bot-paper
```

Live: `install-systemd.sh '' '' live` or third arg `live`.

Telegram control: `install-systemd.sh '' '' telegram` (installs sudoers + `futures-trading-bot-telegram.service`).
