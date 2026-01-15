# WorkSight Deployment Guide

## Prerequisites

1. **GCP VM (e2-medium or higher recommended)**
   - Ubuntu 22.04 LTS
   - At least 2GB RAM
   - External IP address

2. **Domain** configured with DNS A records:
   - `worksight.app` → VM External IP
   - `api.worksight.app` → VM External IP
   - `www.worksight.app` → VM External IP

3. **PostgreSQL Database** (Supabase or self-hosted)

## GitHub Secrets Setup

Go to your repository → Settings → Secrets and variables → Actions → New repository secret

Add the following secrets:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `VM_HOST` | VM external IP address | `35.123.45.67` |
| `VM_USER` | SSH username | `your-username` |
| `VM_SSH_KEY` | Private SSH key (full content) | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `VM_DEPLOY_PATH` | Deployment directory | `/home/your-username/worksight` |
| `DOMAIN` | Your domain name | `worksight.app` |
| `SSL_EMAIL` | Email for Let's Encrypt | `admin@worksight.app` |
| `NEXT_PUBLIC_BACKEND_URL` | Backend API URL | `https://api.worksight.app` |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Google Maps API key | `AIzaSy...` |

## First Deployment

1. **Generate SSH Key** (if not using existing):
   ```bash
   ssh-keygen -t ed25519 -C "github-actions"
   ```
   
2. **Add public key to VM**:
   ```bash
   # On your local machine
   cat ~/.ssh/id_ed25519.pub
   
   # SSH to VM and add to authorized_keys
   echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
   ```

3. **Configure GCP Firewall**:
   - Allow TCP ports: 22, 80, 443
   - Apply to your VM instance

4. **Push to main branch**:
   ```bash
   git add .
   git commit -m "Initial deployment"
   git push origin main
   ```

5. **After first deployment**, SSH to VM and configure backend:
   ```bash
   cd ~/worksight/backend
   nano .env  # Edit with your actual API keys and database URL
   sudo systemctl restart worksight-backend
   ```

## Environment Variables (Backend)

Edit `/home/your-username/worksight/backend/.env`:

```env
# Database (Supabase or PostgreSQL with PostGIS)
DATABASE_URL=postgresql://postgres:password@db.xxx.supabase.co:5432/postgres
DB_SCHEMA=worksightdev

# Security
SECRET_KEY=your-secure-random-string-here
ENVIRONMENT=production

# API Keys
OPENROUTER_API_KEY=sk-or-v1-...
GOOGLE_PLACES_KEY=AIzaSy...
GOOGLE_MAPS_KEY=AIzaSy...
REGRID_API_KEY=your-regrid-api-key
APOLLO_API_KEY=your-apollo-key
```

## Useful Commands

```bash
# Check service status
sudo systemctl status worksight-backend
sudo systemctl status worksight-frontend

# View logs
sudo journalctl -u worksight-backend -f
sudo journalctl -u worksight-frontend -f

# Restart services
sudo systemctl restart worksight-backend
sudo systemctl restart worksight-frontend

# Check nginx
sudo nginx -t
sudo systemctl reload nginx

# SSL certificate renewal (automatic via certbot)
sudo certbot renew --dry-run
```

## Troubleshooting

### Backend not starting
1. Check `.env` file exists and has correct values
2. Check database connection: `psql $DATABASE_URL`
3. Check logs: `sudo journalctl -u worksight-backend -n 50`

### Frontend not starting
1. Check if `.next` folder exists
2. Check logs: `sudo journalctl -u worksight-frontend -n 50`

### SSL issues
1. Ensure DNS records point to VM IP
2. Run: `sudo certbot --nginx -d worksight.app -d www.worksight.app -d api.worksight.app`

### Permission issues
1. Check file ownership: `ls -la ~/worksight`
2. Fix if needed: `sudo chown -R $USER:$USER ~/worksight`
