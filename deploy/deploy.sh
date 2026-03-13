#!/usr/bin/env bash
# Redeploy script — pull latest code and restart the service.
# Usage: sudo bash /opt/food-chaser/deploy/deploy.sh [staging|production]
set -euo pipefail

ENV="${1:-production}"

case "$ENV" in
    staging)
        APP_USER="food-chaser"
        APP_DIR="/opt/food-chaser-staging"
        BRANCH="develop"
        SERVICE="food-chaser-staging"
        ;;
    production)
        APP_USER="food-chaser"
        APP_DIR="/opt/food-chaser"
        BRANCH="master"
        SERVICE="food-chaser"
        ;;
    *)
        echo "ERROR: Unknown environment '$ENV'. Use 'staging' or 'production'." >&2
        exit 1
        ;;
esac

echo "==> Deploying to $ENV (branch: $BRANCH, dir: $APP_DIR)..."

echo "==> Pulling latest code..."
sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin
sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/$BRANCH"

echo "==> Installing/updating Python dependencies..."
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"

echo "==> Fixing permissions on instance dir..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR/backend/instance"

echo "==> Restarting service..."
systemctl restart "$SERVICE"

echo "==> Reloading Caddy config..."
cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl reload caddy

echo "==> Done. Service status:"
systemctl status "$SERVICE" --no-pager
