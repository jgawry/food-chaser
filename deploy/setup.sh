#!/usr/bin/env bash
# One-time setup script — run as root (or with sudo) on the GCP e2-micro VM.
# Usage: sudo bash setup.sh
set -euo pipefail

APP_USER="food-chaser"
APP_DIR="/opt/food-chaser"
STAGING_DIR="/opt/food-chaser-staging"
REPO_URL="https://github.com/jgawry/food-chaser.git"
BRANCH="master"
STAGING_BRANCH="develop"

# ── 1. System packages ────────────────────────────────────────────────────────
apt-get update -q
apt-get install -y python3 python3-pip python3-venv nginx git

# ── 2. Dedicated system user ──────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# ── 3. Clone repositories ─────────────────────────────────────────────────────
if [ -z "$REPO_URL" ]; then
    echo "ERROR: Set REPO_URL at the top of this script before running." >&2
    exit 1
fi

if [ -d "$APP_DIR/.git" ]; then
    echo "Production repo already cloned — skipping."
else
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [ -d "$STAGING_DIR/.git" ]; then
    echo "Staging repo already cloned — skipping."
else
    git clone --branch "$STAGING_BRANCH" "$REPO_URL" "$STAGING_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$STAGING_DIR"

# ── Helper: set up venv + deps for a given app dir ───────────────────────────
setup_venv() {
    local dir="$1"
    python3 -m venv "$dir/venv"
    "$dir/venv/bin/pip" install --quiet --upgrade pip
    "$dir/venv/bin/pip" install --quiet -r "$dir/backend/requirements.txt"
    "$dir/venv/bin/pip" install --quiet gunicorn
}

# ── Helper: set up .env file for a given app dir ─────────────────────────────
setup_env() {
    local dir="$1"
    local service="$2"
    local env_file="$dir/backend/.env"
    if [ ! -f "$env_file" ]; then
        cp "$dir/backend/.env.example" "$env_file"
        echo ""
        echo "ACTION REQUIRED: Edit $env_file and fill in your secrets, then restart the service."
        echo "  sudo nano $env_file"
        echo "  sudo systemctl restart $service"
    fi
}

# ── 4. Python virtual environments ───────────────────────────────────────────
setup_venv "$APP_DIR"
setup_venv "$STAGING_DIR"

# ── 5. Environment files ──────────────────────────────────────────────────────
setup_env "$APP_DIR" "food-chaser"
setup_env "$STAGING_DIR" "food-chaser-staging"

# ── 6. SQLite instance directories ───────────────────────────────────────────
mkdir -p "$APP_DIR/backend/instance"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/backend/instance"

mkdir -p "$STAGING_DIR/backend/instance"
chown -R "$APP_USER:$APP_USER" "$STAGING_DIR/backend/instance"

# ── 7. Systemd services ───────────────────────────────────────────────────────
cp "$APP_DIR/deploy/food-chaser.service" /etc/systemd/system/food-chaser.service
cp "$APP_DIR/deploy/food-chaser-staging.service" /etc/systemd/system/food-chaser-staging.service
systemctl daemon-reload

systemctl enable food-chaser food-chaser-staging
systemctl start food-chaser food-chaser-staging

echo "Production service status:"
systemctl status food-chaser --no-pager
echo "Staging service status:"
systemctl status food-chaser-staging --no-pager

# ── 8. nginx ──────────────────────────────────────────────────────────────────
cp "$APP_DIR/deploy/nginx-site.conf" /etc/nginx/sites-available/food-chaser
ln -sf /etc/nginx/sites-available/food-chaser /etc/nginx/sites-enabled/food-chaser
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

echo ""
VM_IP=$(curl -s ifconfig.me)
echo "Setup complete."
echo "  Production: http://$VM_IP"
echo "  Staging:    http://$VM_IP:8080"
