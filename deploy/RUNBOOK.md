# Deploy runbook — Anamnesis on Alibaba Cloud ECS ($0 path)

The judged backend must run on Alibaba Cloud. This deploys the agent to a fresh **Alibaba ECS**
with a **self-hosted MongoDB** (managed ApsaraDB-for-MongoDB ≈ $200/mo — use it only if you have
the free trial). Alibaba-stack proof = **`qwen-max` via DashScope (an Alibaba API) running on
Alibaba ECS**. Target cost: **$0** via the free-trial / new-user credit.

Once the ECS exists and you can SSH in, this is ~10 copy-paste steps. Artifacts referenced:
`Dockerfile`, `docker-compose.yml`, and one nginx vhost — `deploy/nginx/anamnesis-cloudflare.conf`
(Cloudflare Origin CA, step 7A) or `deploy/nginx/anamnesis.conf` (Let's Encrypt, step 7B). One
container serves the React dashboard at `/` and the API at `/api/*` (`uvicorn api.main:app`).

## 0. Prerequisites (local)

- Alibaba Cloud account (`rheza10@gmail.com`) with an active free-trial / new-user credit.
- The three secrets ready: `ANAMNESIS_DASHSCOPE_API_KEY`, `ANAMNESIS_HELIUS_API_KEY` (DashScope is
  the Alibaba-stack proof), and a strong `MONGO_PASSWORD` you choose now.
- A **dedicated** SSH keypair for this box (don't reuse your personal key):
  ```bash
  ssh-keygen -t ed25519 -C anamnesis-ecs-deploy -f ~/.ssh/anamnesis_ecs
  ```
  Its public key (`~/.ssh/anamnesis_ecs.pub`) gets bound to the instance in step 1.
- A domain/subdomain for the public URL (e.g. `anamnesis.<your-domain>`).

## 1. Provision the ECS

- Region: any with the free tier (e.g. Singapore). Image: **Ubuntu 22.04/24.04 LTS**.
- Burstable instance with **≥ 2 GB RAM** (e.g. 2 vCPU / 2 GB). The 1 GB free-tier option OOMs
  during the image build (pip wheels); use the 2 vCPU / 2 GB free-trial tier — step 4 also adds
  swap as a safety net. Assign a public IP.
- **Security Group**: allow inbound **22, 80, 443** only. Nothing else.
- Bind the dedicated key pair: ECS console → **Key Pairs** → import `~/.ssh/anamnesis_ecs.pub`,
  then attach it during instance creation (key-only; no password).

## 2. DNS

Add an **A record** `anamnesis.<your-domain>` → the ECS public IP.

- **Cloudflare-proxied (recommended, step 7A):** keep the record **Proxied** (orange cloud).
  `dig` returns Cloudflare IPs, not the ECS IP — that is expected.
- **Let's Encrypt / certbot (step 7B):** the record must be **DNS-only** (grey cloud) so the
  HTTP-01 challenge reaches the origin; verify it resolves to the ECS first:
  ```bash
  dig anamnesis.<your-domain> +short    # grey-cloud path: must return the ECS IP
  ```

## 3. SSH in + harden

```bash
ssh -i ~/.ssh/anamnesis_ecs root@<ecs-ip>    # or your sudo user

# key-only SSH (Alibaba cloud-init can re-enable passwords via a drop-in — verify effective)
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sudo rm -f /etc/ssh/sshd_config.d/*cloud-init*.conf 2>/dev/null || true
sudo systemctl restart ssh
sudo sshd -T | grep -iE 'passwordauthentication|permitrootlogin'   # -> no / prohibit-password

# firewall: only 22/80/443
sudo apt-get update && sudo apt-get install -y ufw fail2ban
sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw --force enable
sudo systemctl enable --now fail2ban
```

## 4. Install Docker + compose plugin

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # re-login (or `newgrp docker`) to take effect
docker compose version           # confirm the v2 plugin is present

# 2 GB swap so the image build (pip wheels) doesn't OOM on a 2 GB instance (idempotent on re-run)
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                          # confirm Swap: ~2.0Gi
```

## 5. Clone + configure

```bash
git clone https://github.com/RECTOR-LABS/anamnesis.git && cd anamnesis
cp .env.example .env && nano .env
```

Fill `.env` (it is gitignored — never commit real values):

```
ANAMNESIS_DASHSCOPE_API_KEY=<your dashscope key>
ANAMNESIS_HELIUS_API_KEY=<your helius key>
ANAMNESIS_DB=anamnesis
QWEN_MODEL=qwen-max
# self-hosted Mongo (compose creates this root user; the app URI is built from it)
MONGO_USER=anamnesis
MONGO_PASSWORD=<a strong ALPHANUMERIC password — @ : / # ? break the mongodb:// URI>
```

`ANAMNESIS_MONGODB_URI` is **not** needed here — compose builds it from `MONGO_USER/PASSWORD` and
points the app at the self-hosted `mongo` service.

## 6. Launch

```bash
docker compose up -d --build
docker compose ps              # app + mongo (mongo healthy)
docker compose logs -f app     # watch for "Uvicorn running on http://0.0.0.0:8000"
docker image prune -f          # reclaim the dangling build layer
```

Confirm the security boundary — **mongo must NOT be on `0.0.0.0`** (it should have no host port):

```bash
docker ps --format '{{.Names}}\t{{.Ports}}' | grep -E '27017|8000'
# app shows 127.0.0.1:8000 ; mongo shows no published port
```

## 7. nginx + TLS

Install nginx and drop the distro default, then pick **one** TLS path (7A or 7B):

```bash
sudo apt-get install -y nginx
sudo rm -f /etc/nginx/sites-enabled/default       # drop the distro default site
```

### 7A. Cloudflare Origin CA (recommended — the domain is a proxied `rectorspace.com` subdomain)

Let's Encrypt's HTTP-01 cannot validate behind Cloudflare's orange cloud; a Cloudflare Origin CA
cert is a 15-year, no-renewal cert trusted by Cloudflare's edge.

1. Cloudflare → **SSL/TLS → Origin Server → Create Certificate** (defaults are fine). Paste the
   **Origin Certificate** and **Private Key** onto the ECS:
   ```bash
   sudo mkdir -p /etc/ssl/cloudflare
   sudo nano /etc/ssl/cloudflare/anamnesis.pem    # the Origin Certificate
   sudo nano /etc/ssl/cloudflare/anamnesis.key    # the Private Key
   sudo chmod 600 /etc/ssl/cloudflare/anamnesis.key
   ```
2. Cloudflare → **SSL/TLS → Overview → Full (strict)**; keep the A record **Proxied** (orange).
3. Install the proxied vhost:
   ```bash
   sudo cp deploy/nginx/anamnesis-cloudflare.conf /etc/nginx/sites-available/anamnesis
   sudo sed -i 's/ANAMNESIS_DOMAIN/anamnesis.<your-domain>/g' /etc/nginx/sites-available/anamnesis
   sudo ln -sf /etc/nginx/sites-available/anamnesis /etc/nginx/sites-enabled/anamnesis
   sudo nginx -t && sudo systemctl reload nginx
   ```

### 7B. Let's Encrypt / certbot (only if the domain is **not** Cloudflare-proxied — grey cloud)

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo cp deploy/nginx/anamnesis.conf /etc/nginx/sites-available/anamnesis
sudo sed -i 's/ANAMNESIS_DOMAIN/anamnesis.<your-domain>/g' /etc/nginx/sites-available/anamnesis
sudo ln -sf /etc/nginx/sites-available/anamnesis /etc/nginx/sites-enabled/anamnesis
sudo nginx -t && sudo systemctl reload nginx      # passes: the shipped config is plain HTTP
# certbot clones the HTTP block into a TLS (443) vhost, installs the cert, and adds the redirect:
sudo certbot --nginx -d anamnesis.<your-domain>   # provisions + auto-renews the cert
```

## 8. Seed the demo + verify

```bash
# seed the reproducible serial-rugger memory into the hosted Mongo
docker compose exec app python scripts/seed_demo.py
docker compose exec app python scripts/seed_demo.py --metric   # capture the hosted N× number
```

Open `https://anamnesis.<your-domain>`, paste the **GYaS…** mint and hit **Scan** → expect an
instant **HIGH from memory** (the verdict hero) alongside the cluster graph, evidence cards, and the
memory-aware chat — all on the dashboard.

## 9. Capture submission proof (S.4)

- Alibaba console: the ECS instance (region, public IP) + the DashScope/Model-Studio key page.
- Terminal: `docker compose ps` on the ECS; the `--metric` output (hosted N×).
- Browser: the hosted dashboard showing the HIGH-from-memory verdict + cluster graph at your domain.

## 10. Ongoing deploys

Manual: `cd anamnesis && git pull && docker compose up -d --build && docker image prune -f`.

Optional CI (set repo secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_PATH`): see
`.github/workflows/deploy.yml` — it SSHes in via `appleboy/ssh-action` and runs the same.

## Notes / gotchas

- The dev Mongo on reclabs3 (SSH tunnel) is for local dev only; this deploy is fully self-contained.
- Re-running `seed_demo.py` is idempotent; use `--reset --force` (shows the target db+host first)
  only to wipe the hosted memory for a clean take.
- After any ECS rebuild/reimage, re-check `sudo sshd -T | grep passwordauthentication` (cloud-init
  drop-ins silently re-enable password auth).
- `docker image prune -f` after each deploy — never `docker system prune` (it nukes unrelated data).
```
