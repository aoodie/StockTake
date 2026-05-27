#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/stocktake"
APP_USER="${APP_USER:-www-data}"

sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

if [ ! -d "$APP_DIR/backend" ]; then
  echo "Copy the project files into $APP_DIR before running install steps."
  echo "Example from your local machine:"
  echo "  scp -r backend deploy README.md aoodie@194.164.127.139:$APP_DIR/"
  exit 0
fi

cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

sudo cp deploy/stocktake.service /etc/systemd/system/stocktake.service
sudo sed -i "s|WorkingDirectory=/opt/stocktake/backend|WorkingDirectory=$APP_DIR/backend|" /etc/systemd/system/stocktake.service
sudo sed -i "s|ExecStart=/opt/stocktake/.venv/bin/python|ExecStart=$APP_DIR/.venv/bin/python|" /etc/systemd/system/stocktake.service
sudo sed -i "s|User=www-data|User=$APP_USER|" /etc/systemd/system/stocktake.service

sudo systemctl daemon-reload
sudo systemctl enable stocktake
sudo systemctl restart stocktake

echo "StockTake service started."
echo "Next: install the Nginx config and issue TLS for stock.aoodie.xyz."

