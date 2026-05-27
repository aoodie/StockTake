# Deploying To `stock.aoodie.xyz`

If your current network blocks SSH, run these from a home connection, mobile hotspot, or directly in the VPS provider console.

## 1. Create the directory

```bash
ssh aoodie@194.164.127.139
sudo mkdir -p /opt/stocktake
sudo chown aoodie:aoodie /opt/stocktake
exit
```

## 2. Copy the project

From your local machine:

```bash
scp -r backend deploy README.md aoodie@194.164.127.139:/opt/stocktake/
```

## 3. Bootstrap the app

```bash
ssh aoodie@194.164.127.139
cd /opt/stocktake
bash deploy/bootstrap_vps.sh
```

## 4. Configure HTTPS

Example with Nginx and Certbot:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp /opt/stocktake/deploy/nginx.stock.aoodie.xyz.conf /etc/nginx/sites-available/stock.aoodie.xyz
sudo ln -sf /etc/nginx/sites-available/stock.aoodie.xyz /etc/nginx/sites-enabled/stock.aoodie.xyz
sudo nginx -t
sudo certbot --nginx -d stock.aoodie.xyz
sudo systemctl reload nginx
```

Then open:

```text
https://stock.aoodie.xyz
```

