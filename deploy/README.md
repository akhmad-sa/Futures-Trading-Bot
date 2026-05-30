# Deployment — Futures Trading Bot

Recommended install path on VPS/cloud:

```text
/home/ubuntu/futures-trading-bot
```

## Rename an existing clone (`mexc-bot` → `futures-trading-bot`)

On the server (stop services first if running):

```bash
sudo systemctl stop futures-trading-bot-paper 2>/dev/null || true
mv ~/mexc-bot ~/futures-trading-bot
cd ~/futures-trading-bot
./deploy/install-systemd.sh "$(pwd)" "$(whoami)" paper
```

Update Git remote name locally if desired:

```bash
git remote -v   # no path change required for GitHub URL
```

## Systemd (paper / live)

1. Clone repo to `futures-trading-bot`, create venv, configure `.env` + `configs/`.
2. Smoke test:

```bash
cd ~/futures-trading-bot
source venv/bin/activate
python main.py --version
python main.py -m papertrade -s trendline_breakout --symbols BTCUSDT
```

3. Install unit:

```bash
chmod +x deploy/install-systemd.sh
./deploy/install-systemd.sh /home/ubuntu/futures-trading-bot ubuntu paper
sudo systemctl enable --now futures-trading-bot-paper
```

Edit `ExecStart` in `/etc/systemd/system/futures-trading-bot-paper.service` for `--symbols` or strategy, then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart futures-trading-bot-paper
```

## Cloud-init

See `deploy/cloud-init.example.yaml` for Oracle Cloud Always Free (Ubuntu 24.04 aarch64).
