# Deploy runbook — Anamnesis on Alibaba Cloud ECS ($0 path)

The judged backend must run on Alibaba Cloud. This deploys the agent to a fresh **Alibaba ECS**
with a **self-hosted MongoDB** (managed ApsaraDB-for-MongoDB ≈ $200/mo — use it only if you have
the free trial). Alibaba-stack proof = **`qwen-max` via DashScope (an Alibaba API) running on
Alibaba ECS**. Target cost: **$0** via the free-trial / new-user credit.

Once the ECS exists and you can SSH in, this is ~10 copy-paste steps. Artifacts referenced:
`Dockerfile`, `docker-compose.yml`, `deploy/nginx/anamnesis.conf`.

## 0. Prerequisites (local)

- Alibaba Cloud account (`rheza10@gmail.com`) with an active free-trial / new-user credit.
- The three secrets ready: `ANAMNESIS_DASHSCOPE_API_KEY`, `ANAMNESIS_HELIUS_API_KEY` (DashScope is
  the Alibaba-stack proof), and a strong `MONGO_PASSWORD` you choose now.
- A domain/subdomain for the public URL (e.g. `anamnesis.<your-domain>`).

## 1. Provision the ECS

- Region: any with the free tier (e.g. Singapore). Image: **Ubuntu 22.04/24.04 LTS**.
- Smallest burstable instance (1–2 vCPU / 2 GB is enough; the build downloads wheels, no heavy
  compilation). Assign a public IP.
- **Security Group**: allow inbound **22, 80, 443** only. Nothing else.
- Add your SSH public key during creation (key-only; no password).

## 2. DNS

At your registrar, add an **A record**: `anamnesis.<your-domain>` → the ECS public IP. Verify
before requesting SSL (certbot fails if DNS doesn't resolve yet):

```bash
dig anamnesis.<your-domain> +short    # must return the ECS IP
```

## 3. SSH in + harden

```bash
ssh root@<ecs-ip>            # or your sudo user

# key-only SSH (Alibaba cloud-init can re-enable passwords via a drop-in — verify effective)
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo rm -f /etc/ssh/sshd_config.d/*cloud-init*.conf 2>/dev/null || true
sudo systemctl restart ssh && sudo sshd -T | grep -i passwordauthentication   # -> no

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
MONGO_PASSWORD=<a strong password>
# public URL for cluster-graph links (matches the nginx /graphs/ location)
ANAMNESIS_GRAPHS_BASE_URL=https://anamnesis.<your-domain>/graphs
```

`ANAMNESIS_MONGODB_URI` is **not** needed here — compose builds it from `MONGO_USER/PASSWORD` and
points the app at the self-hosted `mongo` service.

## 6. Launch

```bash
docker compose up -d --build
docker compose ps              # app + mongo (mongo healthy)
docker compose logs -f app     # watch for "Running on ... :7860"
docker image prune -f          # reclaim the dangling build layer
```

Confirm the security boundary — **mongo must NOT be on `0.0.0.0`** (it should have no host port):

```bash
docker ps --format '{{.Names}}\t{{.Ports}}' | grep -E '27017|7860|7866'
# app ports show 127.0.0.1:7860/7866 ; mongo shows no published port
```

## 7. nginx + SSL

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx/anamnesis.conf /etc/nginx/sites-available/anamnesis
sudo sed -i 's/ANAMNESIS_DOMAIN/anamnesis.<your-domain>/g' /etc/nginx/sites-available/anamnesis
sudo ln -sf /etc/nginx/sites-available/anamnesis /etc/nginx/sites-enabled/anamnesis
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d anamnesis.<your-domain>   # provisions + auto-renews the cert
```

## 8. Seed the demo + verify

```bash
# seed the reproducible serial-rugger memory into the hosted Mongo
docker compose exec app python scripts/seed_demo.py
docker compose exec app python scripts/seed_demo.py --metric   # capture the hosted N× number
```

Open `https://anamnesis.<your-domain>`, click the **GYaS…** suggestion → expect an instant **HIGH
from memory**, then ask for the cluster graph (link resolves under `/graphs/`).

## 9. Capture submission proof (S.4)

- Alibaba console: the ECS instance (region, public IP) + the DashScope/Model-Studio key page.
- Terminal: `docker compose ps` on the ECS; the `--metric` output (hosted N×).
- Browser: the hosted WebUI showing the HIGH-from-memory verdict + cluster graph at your domain.

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
