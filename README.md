# FastAPI DevSecOps — Production Deployment

A production-ready FastAPI application fully containerized with Docker Compose, secured with a DevSecOps CI/CD pipeline, and deployed to AWS EC2 via GitHub Actions.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start (Local)](#quick-start-local)
- [Environment Variables](#environment-variables)
- [Docker Compose Services](#docker-compose-services)
- [NGINX Configuration](#nginx-configuration)
- [CI/CD Pipeline](#cicd-pipeline)
- [SSL Setup](#ssl-setup)
- [Security Measures](#security-measures)
- [Monitoring](#monitoring)
- [Logging Strategy](#logging-strategy)
- [Backup & Restart Strategy](#backup--restart-strategy)
- [Deployment Instructions](#deployment-instructions)
- [GitHub Secrets Reference](#github-secrets-reference)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
Internet
    │
    ▼
[AWS EC2 — Ubuntu 22.04]
    │
    ├── NGINX (port 80/443)          ← Reverse proxy, SSL termination
    │       │
    │       ├──► FastAPI app (internal :8000)   ← Business logic, /health, /metrics
    │       └──► Grafana /grafana/  (internal :3000)
    │
    ├── PostgreSQL (internal :5432)  ← Primary database, persisted volume
    ├── Redis      (internal :6379)  ← Cache layer, AOF persistence
    └── Prometheus (internal :9090)  ← Metrics scraper
```

**Key design decisions:**
- Only ports 80 and 443 are exposed to the internet. All other services communicate on Docker's internal network.
- The FastAPI app binds to `127.0.0.1:8000` on the host — it is never directly reachable from outside.
- All containers use `restart: unless-stopped` for automatic recovery.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Application | FastAPI + Uvicorn |
| Database | PostgreSQL 15 |
| Cache | Redis 7 |
| Reverse Proxy | NGINX Alpine |
| Monitoring | Prometheus + Grafana |
| Containerization | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| SAST | SonarQube |
| Container Scanning | Trivy |
| Registry | Docker Hub |
| Server | AWS EC2 (Ubuntu 22.04) |

---

## Project Structure

```
fastapi-devops/
├── app/
│   ├── main.py              # FastAPI app — routes, health check, metrics
│   ├── database.py          # SQLAlchemy engine and session factory
│   └── requirements.txt     # Python dependencies
├── nginx/
│   └── nginx.conf           # Reverse proxy config with security headers
├── monitoring/
│   └── prometheus.yml       # Prometheus scrape config
├── .github/
│   └── workflows/
│       └── deploy.yml       # 5-stage DevSecOps CI/CD pipeline
├── Dockerfile               # Multi-stage Python 3.11 image
├── docker-compose.yml       # Full service orchestration
├── sonar-project.properties # SonarQube project config
├── .dockerignore            # Excludes secrets and dev files from image
├── .gitignore
└── .env.example             # Template — copy to .env and fill in values
```

---

## Quick Start (Local)

```bash
# 1. Clone the repository
git clone https://github.com/Bhartendu08/fastapi-devops.git
cd fastapi-devops

# 2. Create your environment file
cp .env.example .env
# Edit .env with your values (see Environment Variables section)

# 3. Start all services
docker compose up -d

# 4. Verify everything is running
docker compose ps

# 5. Test the API
curl http://localhost/health
# Expected: {"status":"ok","redis":true,"db":true}

# 6. View API docs
open http://localhost/docs

# 7. View Grafana dashboard
open http://localhost/grafana/
# Default login: admin / <GRAFANA_PASSWORD from .env>
```

---

## Environment Variables

Create a `.env` file in the project root. **Never commit this file.**

```env
# ── PostgreSQL ────────────────────────────────
POSTGRES_USER=appuser
POSTGRES_PASSWORD=StrongPasswordHere123!
POSTGRES_DB=appdb
DATABASE_URL=postgresql://appuser:StrongPasswordHere123!@db:5432/appdb

# ── Redis ─────────────────────────────────────
REDIS_URL=redis://redis:6379

# ── Application ───────────────────────────────
SECRET_KEY=replace-with-64-char-random-string
ENVIRONMENT=production

# ── Grafana ───────────────────────────────────
GRAFANA_PASSWORD=AdminPasswordHere!
```

Generate a strong SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Docker Compose Services

| Service | Image | Internal Port | Exposed | Purpose |
|---|---|---|---|---|
| `app` | `bhartendu11/fastapi-devops:latest` | 8000 | `127.0.0.1:8000` | FastAPI application |
| `db` | `postgres:15-alpine` | 5432 | No | Primary database |
| `redis` | `redis:7-alpine` | 6379 | No | Cache / session store |
| `nginx` | `nginx:alpine` | 80 | `0:80`, `0:443` | Reverse proxy |
| `prometheus` | `prom/prometheus:latest` | 9090 | `0:9090` | Metrics collection |
| `grafana` | `grafana/grafana:latest` | 3000 | `0:3000` | Metrics dashboard |

**Health checks are defined on all critical services:**
- `app` — polls `/health` endpoint every 10 seconds
- `db` — runs `pg_isready` every 10 seconds
- `redis` — runs `redis-cli ping` every 10 seconds

The `app` service will not start until both `db` and `redis` pass their health checks (`condition: service_healthy`).

**Persistent volumes:**
- `postgres_data` — database files survive container restarts
- `redis_data` — Redis AOF log survives restarts (no data loss on crash)
- `grafana_data` — dashboard configurations persist

---

## NGINX Configuration

NGINX acts as the single entry point for all traffic:

- **Port 80** — accepts all HTTP traffic
- Proxies `/` → FastAPI at `app:8000`
- Proxies `/grafana/` → Grafana at `grafana:3000`
- Sets security headers on all responses:
  - `X-Frame-Options: DENY` — prevents clickjacking
  - `X-Content-Type-Options: nosniff` — prevents MIME sniffing
- Supports WebSocket upgrades (`Upgrade`, `Connection` headers forwarded)
- `client_max_body_size 20M` — allows reasonable payload sizes

---

## CI/CD Pipeline

The pipeline has **5 sequential stages**, each requiring the previous to pass:

```
push to main
     │
     ▼
[Stage 1] SonarQube SAST Scan
     │  Static code analysis + quality gate check
     ▼
[Stage 2] Build Docker Image
     │  docker build → save as .tar artifact
     ▼
[Stage 3] Trivy Container Scan
     │  Scans for CRITICAL + HIGH CVEs in OS + libraries
     │  Fails pipeline if unfixed vulnerabilities found
     ▼
[Stage 4] Push to Docker Hub
     │  Tags image with git SHA for traceability
     ▼
[Stage 5] Deploy to EC2 via SSH
          Pulls new image → docker compose up -d → prune old images
```

**Why this pipeline is production-grade:**
- Images are built once and passed between stages as artifacts — no duplicate builds
- Container scanning happens before push — vulnerable images never reach the registry
- Image is tagged with `git SHA` — every deployed version is fully traceable
- Deployment uses `docker compose up -d` — zero manual steps on the server

---

## SSL Setup

### Option A — With a domain (recommended, using Let's Encrypt)

```bash
# On your EC2 instance
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Certbot auto-edits nginx.conf to add SSL and redirect HTTP → HTTPS
# Certificates auto-renew via cron (verify with):
sudo certbot renew --dry-run
```

Update `nginx/nginx.conf` to listen on 443 with the cert paths Certbot provides.

### Option B — Without a domain (self-signed, for testing/demo)

```bash
# Generate self-signed certificate
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem \
  -subj "/C=IN/ST=Delhi/L=Delhi/O=DevOps/CN=localhost"
```

Add to `nginx.conf`:
```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ...
}
```

> In production, always use a real domain with Let's Encrypt. Self-signed certificates will show browser warnings.

---

## Security Measures

### Network
- All backend services (FastAPI, PostgreSQL, Redis, Prometheus) are on Docker's internal network — unreachable from outside
- NGINX is the only public-facing entry point
- FastAPI binds to `127.0.0.1:8000` — not accessible even on host directly

### AWS EC2 Security Group (firewall)

| Port | Protocol | Source | Reason |
|---|---|---|---|
| 22 | TCP | Your IP only | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

All other ports are blocked at the AWS level.

### Server hardening (run once on EC2)

```bash
# Disable root SSH login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Install and configure UFW
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Install fail2ban (blocks IPs after repeated SSH failures)
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### CI/CD Security
- All secrets stored in GitHub Secrets — never in code
- `.env` is in `.gitignore` and `.dockerignore`
- `*.pem` key files excluded from Docker image
- SonarQube scans for code vulnerabilities before every build
- Trivy blocks any image with CRITICAL or HIGH unfixed CVEs

---

## Monitoring

Prometheus scrapes the `/metrics` endpoint on the FastAPI app every 15 seconds. Grafana visualizes these metrics at `http://your-server/grafana/`.

**Available metrics (via prometheus-fastapi-instrumentator):**
- HTTP request count by route and status code
- Request duration histograms
- In-progress requests

**To set up Grafana dashboard:**
1. Log in to `http://your-server/grafana/` (admin / your GRAFANA_PASSWORD)
2. Add data source → Prometheus → URL: `http://prometheus:9090`
3. Import dashboard ID `17175` (FastAPI Observability) from Grafana.com

---

## Logging Strategy

All application logs use Python's `logging` module with structured format:

```
2025-01-15 10:23:45 INFO Root endpoint hit
2025-01-15 10:23:46 ERROR Redis ping failed: Connection refused
```

**Log format:** `%(asctime)s %(levelname)s %(message)s`  
**Log level:** `INFO` in production (change to `DEBUG` for troubleshooting)

**Viewing logs:**
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f nginx

# Last 100 lines
docker compose logs --tail=100 app
```

**Log persistence:** Docker default logging driver writes to `/var/lib/docker/containers/<id>/<id>-json.log`. For production, consider adding log rotation:

```yaml
# Add to each service in docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

---

## Backup & Restart Strategy

### Automatic restart
All services use `restart: unless-stopped`. Docker automatically restarts any container that crashes, unless you explicitly stop it with `docker compose stop`.

### Database backups

```bash
# Manual backup
docker exec fastapi-devops-db-1 pg_dump -U appuser appdb | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore from backup
gunzip < backup_20250115.sql.gz | docker exec -i fastapi-devops-db-1 psql -U appuser appdb
```

**Automated daily backups via cron** (`crontab -e` on EC2):

```bash
# Daily backup at 2:00 AM, keep last 7 days
0 2 * * * docker exec fastapi-devops-db-1 pg_dump -U appuser appdb | gzip > /opt/backups/db_$(date +\%Y\%m\%d).sql.gz
0 3 * * * find /opt/backups -name "*.sql.gz" -mtime +7 -delete
```

```bash
# Create backup directory
sudo mkdir -p /opt/backups
sudo chown ubuntu:ubuntu /opt/backups
```

---

## Deployment Instructions

### Prerequisites
- AWS EC2 instance (Ubuntu 22.04, t3.small recommended)
- Elastic IP attached to EC2
- GitHub repository with secrets configured (see below)
- Docker Hub account

### Step 1 — Launch EC2

1. AWS Console → EC2 → Launch Instance
2. Choose **Ubuntu Server 22.04 LTS**
3. Instance type: **t3.small**
4. Create key pair → download `.pem` file
5. Security Group: allow ports 22 (your IP), 80, 443
6. Launch → attach an Elastic IP

### Step 2 — Set up the server

```bash
# SSH into EC2
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<your-elastic-ip>

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Install security tools
sudo apt install fail2ban ufw -y
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable
sudo systemctl enable fail2ban && sudo systemctl start fail2ban

# Create app directory
mkdir -p /home/ubuntu/fastapi-devops

# Create backup directory
sudo mkdir -p /opt/backups && sudo chown ubuntu:ubuntu /opt/backups
```

### Step 3 — Copy compose files to EC2

```bash
# From your local machine
scp -i your-key.pem docker-compose.yml ubuntu@<elastic-ip>:/home/ubuntu/fastapi-devops/
scp -i your-key.pem -r nginx/ ubuntu@<elastic-ip>:/home/ubuntu/fastapi-devops/
scp -i your-key.pem -r monitoring/ ubuntu@<elastic-ip>:/home/ubuntu/fastapi-devops/
```

### Step 4 — Configure GitHub Secrets

Go to your GitHub repo → Settings → Secrets and Variables → Actions → New repository secret:

| Secret Name | Value |
|---|---|
| `DOCKER_USERNAME` | Your Docker Hub username |
| `DOCKER_PASSWORD` | Your Docker Hub password or access token |
| `EC2_HOST` | Your EC2 Elastic IP address |
| `EC2_USER` | `ubuntu` |
| `ECR_SSH_KEY` | Contents of your `.pem` key file |
| `PROD_ENV_FILE` | Full contents of your `.env` file |
| `SONAR_TOKEN` | SonarQube project token |
| `SONAR_HOST_URL` | Your SonarQube server URL |

### Step 5 — Trigger first deployment

```bash
# Push to main branch — pipeline runs automatically
git add .
git commit -m "feat: initial production deployment"
git push origin main
```

Watch the pipeline at: `https://github.com/Bhartendu08/fastapi-devops/actions`

### Step 6 — Verify deployment

```bash
# On EC2
docker compose ps                      # All services should show "healthy"
curl http://localhost/health           # {"status":"ok","redis":true,"db":true}
curl http://localhost/                 # {"message":"API is running"}
curl http://localhost/docs             # FastAPI Swagger UI
curl http://localhost/grafana/         # Grafana dashboard
```

---

## GitHub Secrets Reference

| Secret | Used In | Description |
|---|---|---|
| `SONAR_TOKEN` | Stage 1 | SonarQube authentication token |
| `SONAR_HOST_URL` | Stage 1 | SonarQube server URL |
| `DOCKER_USERNAME` | Stage 4 | Docker Hub username |
| `DOCKER_PASSWORD` | Stage 4 | Docker Hub password / access token |
| `EC2_HOST` | Stage 5 | EC2 Elastic IP |
| `EC2_USER` | Stage 5 | EC2 SSH username (`ubuntu`) |
| `ECR_SSH_KEY` | Stage 5 | Private SSH key for EC2 access |
| `PROD_ENV_FILE` | Stage 5 | Full `.env` file contents |

---

## Troubleshooting

**Container won't start — check logs:**
```bash
docker compose logs app
docker compose logs db
```

**Health check failing:**
```bash
# Test directly inside the container
docker exec fastapi-devops-app-1 curl http://localhost:8000/health
```

**Database connection error:**
```bash
# Verify DB is healthy
docker compose ps db
# Check DB logs
docker compose logs db
# Test connection
docker exec fastapi-devops-db-1 pg_isready -U appuser
```

**Redis connection error:**
```bash
docker exec fastapi-devops-redis-1 redis-cli ping
# Should return: PONG
```

**NGINX 502 Bad Gateway:**
```bash
# App container probably crashed — check
docker compose logs app
docker compose restart app
```

**Port 80 already in use on EC2:**
```bash
sudo lsof -i :80
sudo systemctl stop apache2   # if Apache is running
```
