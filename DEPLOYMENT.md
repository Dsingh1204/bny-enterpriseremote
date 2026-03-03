# Cross-Network Deployment Guide

## Architecture for Cross-Network Access

```
┌─────────────────┐                                    ┌─────────────────┐
│  HOME / VPN     │                                    │    OFFICE       │
│                 │                                    │                 │
│  ┌───────────┐  │      ┌─────────────────────┐      │  ┌───────────┐  │
│  │  CLIENT   │──┼─────►│   RELAY SERVER      │◄─────┼──│   ADMIN   │  │
│  │  AGENT    │  │      │   (Public Cloud)    │      │  │  CONSOLE  │  │
│  └───────────┘  │      └─────────────────────┘      │  └───────────┘  │
│                 │              ▲                     │                 │
└─────────────────┘              │                     └─────────────────┘
                          Public IP/Domain
                          (HTTPS Port 443)
```

## Option 1: Quick Test with ngrok (Free)

ngrok creates a public tunnel to your local server.

### Steps:
1. Install ngrok: https://ngrok.com/download
2. Start the server locally:
   ```bash
   cd server && npm start
   ```
3. Create tunnel:
   ```bash
   ngrok http 3000
   ```
4. Use the ngrok URL (e.g., `https://abc123.ngrok.io`) for:
   - Admin Console: Open in browser
   - Client Agent: `python3 client.py https://abc123.ngrok.io`

---

## Option 2: Deploy to Cloud (Production)

### A. DigitalOcean / AWS / Azure

1. Create a VM (Ubuntu 22.04 recommended)
2. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
3. Clone and deploy:
   ```bash
   git clone <your-repo>
   cd EnterpriseRemoteSupport
   
   # Generate SSL certificates (or use Let's Encrypt)
   mkdir ssl
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout ssl/key.pem -out ssl/cert.pem
   
   # Start services
   docker-compose up -d
   ```

### B. Using Let's Encrypt (Free SSL)

```bash
# Install certbot
apt install certbot

# Get certificate
certbot certonly --standalone -d your-domain.com

# Copy certs
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/cert.pem
cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/key.pem
```

---

## Option 3: Deploy to Railway/Render (Easy)

### Railway.app (Free tier available)

1. Push code to GitHub
2. Connect Railway to your repo
3. Deploy automatically
4. Get public URL

### Render.com

1. Create Web Service
2. Connect GitHub repo
3. Set build command: `cd server && npm install`
4. Set start command: `cd server && npm start`

---

## Client Agent Configuration

The client agent can connect to any server URL:

```bash
# Local testing
python3 client.py http://localhost:3000

# Production server
python3 client.py https://your-server.com

# With environment variable
export SERVER_URL=https://your-server.com
python3 client.py
```

---

## Firewall Requirements

### Server (Cloud)
- Inbound: Port 443 (HTTPS) or 3000 (HTTP)
- Outbound: All (for responses)

### Client (Home/VPN)
- Outbound: Port 443 to server (usually allowed)
- No inbound ports needed!

### Admin (Office)
- Outbound: Port 443 to server (usually allowed)
- No inbound ports needed!

---

## Security Recommendations

1. **Use HTTPS** - Always use SSL/TLS in production
2. **Change default passwords** - Update admin/tech1 accounts
3. **JWT Secret** - Set strong `JWT_SECRET` environment variable
4. **Firewall** - Only expose port 443
5. **Access Codes** - Codes expire with sessions

---

## Network Diagram

```
                    INTERNET
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
    ┌──────────┐               ┌──────────┐
    │  HOME    │               │  OFFICE  │
    │  Network │               │  Network │
    │          │               │          │
    │ ┌──────┐ │               │ ┌──────┐ │
    │ │Client│ │               │ │Admin │ │
    │ │Agent │ │               │ │Web   │ │
    │ └──┬───┘ │               │ └──┬───┘ │
    │    │     │               │    │     │
    │    ▼     │               │    ▼     │
    │  NAT/FW  │               │  NAT/FW  │
    └────┬─────┘               └────┬─────┘
         │                          │
         │    ┌────────────────┐    │
         └───►│  RELAY SERVER  │◄───┘
              │  (Cloud/Public)│
              │                │
              │  - Receives    │
              │    connections │
              │  - Relays data │
              │  - No direct   │
              │    P2P needed  │
              └────────────────┘
```

Both Client and Admin make **OUTBOUND** connections to the server.
No inbound ports need to be opened on either side!
