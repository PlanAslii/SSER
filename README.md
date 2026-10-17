# PlanAsli SSH Manager

Professional SSH account administration panel for Ubuntu 24.04 LTS.

**Features**

- SSH account lifecycle management (create, edit, disable, expire, delete)
- Active connections, connection history, authentication logs
- Server monitoring with real CPU / memory / disk metrics and charts
- GitHub Releases–based update system with checksum verification, backups, and rollback
- Professional minimal UI with light / dark / system themes
- Full Persian (فارسی) RTL interface with Vazirmatn font
- One-command installer with menu (install, update, repair, backup, uninstall)
- Restricted privileged helper (no arbitrary root command execution from the web UI)

## Requirements

- Ubuntu 24.04 LTS (recommended)
- Root privileges for installation
- Python 3.12+
- OpenSSH server

## Installation

**Always audit the installer before running it as root.**

```bash
curl -fsSL https://raw.githubusercontent.com/PlanAsli/planasli-ssh/main/install.sh -o install.sh
less install.sh
sudo bash install.sh
```

Or from a cloned repository:

```bash
git clone https://github.com/PlanAsli/planasli-ssh.git
cd planasli-ssh
sudo bash install.sh
```

The installer presents a menu:

1. Fresh installation  
2. Update existing installation  
3. Repair installation  
4. Check installation status  
5. Backup configuration and database  
6. Restore a backup  
7. Uninstall panel  
8. Exit  

After installation, open **http://127.0.0.1:8080** and complete first-time administrator setup.

The panel binds to **localhost** by default. For public access, place it behind a reverse proxy with HTTPS.

### Reverse proxy (nginx example)

```nginx
server {
    listen 443 ssl http2;
    server_name panel.example.com;
    # ssl_certificate / ssl_certificate_key …

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Configuration

Environment file: `/etc/planasli-ssh/planasli.env`

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Session / JWT secret | generated at install |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:////var/lib/planasli-ssh/planasli.db` |
| `HOST` / `PORT` | Bind address | `127.0.0.1` / `8080` |
| `GITHUB_OWNER` | GitHub org/user for updates | `PlanAsli` |
| `GITHUB_REPO` | Repository name | `planasli-ssh` |
| `RELEASE_CHANNEL` | `stable` / `beta` / `nightly` | `stable` |

## Updates

1. Publish a GitHub Release with tag `vX.Y.Z`.
2. Attach `planasli-ssh-X.Y.Z.tar.gz` and `planasli-ssh-X.Y.Z.tar.gz.sha256`.
3. In the panel **Updates** page, click **Check for updates**, then **Install**.

The update procedure:

- Acquires an exclusive lock  
- Downloads over HTTPS  
- Verifies SHA-256 checksum  
- Rejects path traversal and unexpected archive contents  
- Backs up the current version and database  
- Installs into a versioned directory under `/opt/planasli-ssh/releases/`  
- Switches the `current` symlink only after health checks  
- Rolls back on failure when possible  

**Automatic checks** run via a systemd timer (default every 24h). Unattended installation is **disabled** by default.

### Creating the GitHub repository

1. Create a repository (e.g. `PlanAsli/planasli-ssh`).
2. Push this codebase to the `main` branch.
3. Configure `GITHUB_OWNER` and `GITHUB_REPO` in `/etc/planasli-ssh/planasli.env` (or the installer defaults).
4. Push a version tag: `git tag v1.0.0 && git push origin v1.0.0`.
5. The Release workflow builds the archive, generates the checksum, and publishes the release.

Until Releases exist, the Updates page shows a clear setup message instead of fabricated data.

## Security notes

- The web application does **not** accept arbitrary commands, paths, or download URLs for privileged operations.
- Privileged actions go through `/usr/local/sbin/planasli-update-helper` with a strict allowlist.
- Secrets, database, backups, and logs live outside version-controlled source trees.
- A checksum from the same source as the archive is **not** a substitute for signing; for high-security deployments, pin trusted release keys or use artifact signing.
- GitHub repository maintainers and release artifacts are part of your software supply chain.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./dev.db"
export SECRET_KEY="dev-secret"
export DATA_DIR="./data"
mkdir -p data
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

```bash
pytest tests/ -q
ruff check app
```

## License

Proprietary / All rights reserved unless otherwise stated by the repository owner.
