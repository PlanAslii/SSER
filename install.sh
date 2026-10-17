#!/usr/bin/env bash
# PlanAsli SSH Manager — Professional installer
# Audit this script before running: less install.sh
# Usage: sudo bash install.sh
set -euo pipefail

PLANASLI_VERSION="${PLANASLI_VERSION:-1.0.0}"
PLANASLI_OWNER="${PLANASLI_OWNER:-PlanAsli}"
PLANASLI_REPO="${PLANASLI_REPO:-planasli-ssh}"
INSTALL_ROOT="/opt/planasli-ssh"
DATA_DIR="/var/lib/planasli-ssh"
CONFIG_DIR="/etc/planasli-ssh"
LOG_DIR="/var/log/planasli-ssh"
SERVICE_USER="planasli"
SERVICE_GROUP="planasli"
PYTHON_BIN="python3"
VENV_DIR="${INSTALL_ROOT}/venv"
APP_PORT=8080

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    err "This installer must be run as root (sudo)."
    exit 1
  fi
}

detect_os() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]]; then
      ok "Detected Ubuntu 24.04 LTS"
      return 0
    fi
    warn "Expected Ubuntu 24.04 LTS, found: ${PRETTY_NAME:-unknown}. Continuing with caution."
  else
    warn "Cannot detect OS. Continuing with caution."
  fi
}

check_disk() {
  local avail
  avail=$(df -BG /opt 2>/dev/null | awk 'NR==2{gsub(/G/,"",$4); print $4}' || echo 10)
  if [[ "${avail:-0}" -lt 2 ]]; then
    err "Less than 2GB free disk space available."
    exit 1
  fi
  ok "Disk space: ${avail}GB available"
}

check_port() {
  if ss -tlnp 2>/dev/null | grep -q ":${APP_PORT} "; then
    warn "Port ${APP_PORT} is already in use."
  else
    ok "Port ${APP_PORT} is free"
  fi
}

install_system_deps() {
  info "Installing system dependencies…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    build-essential libffi-dev libssl-dev \
    curl ca-certificates openssh-server \
    > /dev/null
  ok "System dependencies installed"
}

create_user() {
  if ! getent group "${SERVICE_GROUP}" >/dev/null; then
    groupadd --system "${SERVICE_GROUP}"
  fi
  if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${SERVICE_GROUP}" --home-dir "${DATA_DIR}" \
      --shell /usr/sbin/nologin --comment "PlanAsli SSH Manager" "${SERVICE_USER}"
  fi
  ok "Service account: ${SERVICE_USER}"
}

create_dirs() {
  mkdir -p "${INSTALL_ROOT}/releases" "${INSTALL_ROOT}/current" \
    "${DATA_DIR}/backups" "${CONFIG_DIR}" "${LOG_DIR}"
  # current may be a symlink later
  if [[ -d "${INSTALL_ROOT}/current" && ! -L "${INSTALL_ROOT}/current" ]]; then
    rmdir "${INSTALL_ROOT}/current" 2>/dev/null || true
  fi
  ok "Directories created"
}

install_app() {
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  # If running from a cloned repo, copy from source
  if [[ -d "${src_dir}/app" ]]; then
    local version_dir="${INSTALL_ROOT}/releases/${PLANASLI_VERSION}"
    info "Installing from local source to ${version_dir}"
    rm -rf "${version_dir}"
    mkdir -p "${version_dir}"
    cp -a "${src_dir}/app" "${src_dir}/requirements.txt" "${src_dir}/VERSION" \
      "${src_dir}/systemd" "${src_dir}/update_helper" "${src_dir}/config" \
      "${version_dir}/" 2>/dev/null || true
    # Ensure VERSION exists
    echo "${PLANASLI_VERSION}" > "${version_dir}/VERSION"
    ln -sfn "${version_dir}" "${INSTALL_ROOT}/current"
  else
    err "Source application not found next to install.sh. Clone the repository first."
    exit 1
  fi
  ok "Application files installed"
}

setup_venv() {
  info "Creating Python virtual environment…"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"
  pip install --upgrade pip setuptools wheel -q
  pip install -r "${INSTALL_ROOT}/current/requirements.txt" -q
  ok "Python dependencies installed"
}

init_database() {
  info "Initializing database…"
  mkdir -p "${DATA_DIR}"
  export PLANASLI_DATA_DIR="${DATA_DIR}"
  export DATABASE_URL="sqlite:///${DATA_DIR}/planasli.db"
  export SECRET_KEY
  SECRET_KEY="$(openssl rand -hex 32)"
  # Write env file (restricted permissions)
  cat > "${CONFIG_DIR}/planasli.env" <<ENV
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=sqlite:///${DATA_DIR}/planasli.db
HOST=127.0.0.1
PORT=${APP_PORT}
DATA_DIR=${DATA_DIR}
CONFIG_DIR=${CONFIG_DIR}
LOG_DIR=${LOG_DIR}
GITHUB_OWNER=${PLANASLI_OWNER}
GITHUB_REPO=${PLANASLI_REPO}
ENV
  chmod 640 "${CONFIG_DIR}/planasli.env"
  chown root:"${SERVICE_GROUP}" "${CONFIG_DIR}/planasli.env"

  # Init DB via Python
  cd "${INSTALL_ROOT}/current"
  PYTHONPATH="${INSTALL_ROOT}/current" \
    DATABASE_URL="sqlite:///${DATA_DIR}/planasli.db" \
    "${VENV_DIR}/bin/python" -c "
from app.core.database import init_db
from app.core.config import get_settings
get_settings.cache_clear()
init_db()
print('Database initialized')
"
  touch "${DATA_DIR}/.installed"
  ok "Database initialized"
}

install_systemd() {
  info "Installing systemd units…"
  local unit_src="${INSTALL_ROOT}/current/systemd"
  if [[ -f "${unit_src}/planasli-ssh.service" ]]; then
    cp "${unit_src}/planasli-ssh.service" /etc/systemd/system/
    cp "${unit_src}/planasli-update-check.timer" /etc/systemd/system/ 2>/dev/null || true
    cp "${unit_src}/planasli-update-check.service" /etc/systemd/system/ 2>/dev/null || true
  else
    # Generate service unit
    cat > /etc/systemd/system/planasli-ssh.service <<UNIT
[Unit]
Description=PlanAsli SSH Manager
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${INSTALL_ROOT}/current
EnvironmentFile=${CONFIG_DIR}/planasli.env
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 127.0.0.1 --port ${APP_PORT} --proxy-headers
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${DATA_DIR} ${LOG_DIR} ${CONFIG_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
  fi

  # Update helper (restricted)
  if [[ -f "${INSTALL_ROOT}/current/update_helper/planasli-update-helper" ]]; then
    install -m 750 -o root -g "${SERVICE_GROUP}" \
      "${INSTALL_ROOT}/current/update_helper/planasli-update-helper" \
      /usr/local/sbin/planasli-update-helper
  fi

  systemctl daemon-reload
  systemctl enable planasli-ssh.service
  systemctl enable planasli-update-check.timer 2>/dev/null || true
  ok "Systemd units installed"
}

set_permissions() {
  chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${DATA_DIR}" "${LOG_DIR}"
  chown -R root:"${SERVICE_GROUP}" "${INSTALL_ROOT}"
  chmod -R u=rwX,g=rX,o= "${INSTALL_ROOT}"
  chmod 750 "${DATA_DIR}" "${LOG_DIR}" "${CONFIG_DIR}"
  ok "Permissions set"
}

start_services() {
  systemctl restart planasli-ssh.service
  sleep 2
  if systemctl is-active --quiet planasli-ssh.service; then
    ok "Service is running"
  else
    warn "Service may not have started. Check: journalctl -u planasli-ssh -n 50"
  fi
}

health_check() {
  local tries=0
  while [[ $tries -lt 10 ]]; do
    if curl -sf "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
      ok "Health check passed"
      return 0
    fi
    sleep 1
    tries=$((tries + 1))
  done
  warn "Health endpoint not responding yet. Check logs."
}

print_summary() {
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo -e "  ${GREEN}PlanAsli SSH Manager installed successfully${NC}"
  echo "═══════════════════════════════════════════════════════"
  echo "  Version:     ${PLANASLI_VERSION}"
  echo "  Install:     ${INSTALL_ROOT}/current"
  echo "  Data:        ${DATA_DIR}"
  echo "  Config:      ${CONFIG_DIR}/planasli.env"
  echo "  Logs:        ${LOG_DIR}"
  echo "  Panel URL:   http://127.0.0.1:${APP_PORT}"
  echo ""
  echo "  First visit the panel URL to create the administrator account."
  echo "  The panel binds to localhost by default."
  echo "  For remote access, configure a reverse proxy with HTTPS."
  echo ""
  echo "  Useful commands:"
  echo "    systemctl status planasli-ssh"
  echo "    journalctl -u planasli-ssh -f"
  echo "═══════════════════════════════════════════════════════"
}

# ── Menu ─────────────────────────────────────────────────────
show_menu() {
  echo ""
  echo "PlanAsli SSH Manager Installer"
  echo "─────────────────────────────"
  echo "1. Fresh installation"
  echo "2. Update existing installation"
  echo "3. Repair installation"
  echo "4. Check installation status"
  echo "5. Backup configuration and database"
  echo "6. Restore a backup"
  echo "7. Uninstall panel"
  echo "8. Exit"
  echo ""
  read -r -p "Select option [1-8]: " choice
  case "${choice}" in
    1) do_fresh_install ;;
    2) do_update ;;
    3) do_repair ;;
    4) do_status ;;
    5) do_backup ;;
    6) do_restore ;;
    7) do_uninstall ;;
    8) exit 0 ;;
    *) err "Invalid option"; show_menu ;;
  esac
}

do_fresh_install() {
  if [[ -f "${DATA_DIR}/.installed" ]]; then
    warn "Existing installation detected. Use option 2 (Update) or 3 (Repair)."
    read -r -p "Force reinstall and KEEP data? [y/N]: " ans
    if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
      return
    fi
  fi
  require_root
  detect_os
  check_disk
  check_port
  install_system_deps
  create_user
  create_dirs
  install_app
  setup_venv
  init_database
  install_systemd
  set_permissions
  start_services
  health_check
  print_summary
}

do_update() {
  require_root
  if [[ ! -f "${DATA_DIR}/.installed" ]]; then
    err "No existing installation found."
    return
  fi
  info "Updating application files from local source…"
  install_app
  setup_venv
  set_permissions
  systemctl restart planasli-ssh.service
  health_check
  ok "Update complete"
}

do_repair() {
  require_root
  info "Repairing installation (credentials and accounts are preserved)…"
  install_system_deps
  create_user
  create_dirs
  setup_venv
  install_systemd
  set_permissions
  systemctl restart planasli-ssh.service
  health_check
  ok "Repair complete"
}

do_status() {
  echo "Installation status"
  echo "──────────────────"
  [[ -f "${DATA_DIR}/.installed" ]] && ok "Installed marker present" || warn "Not installed"
  [[ -L "${INSTALL_ROOT}/current" || -d "${INSTALL_ROOT}/current" ]] && ok "App path exists" || warn "App path missing"
  systemctl is-active --quiet planasli-ssh.service && ok "Service active" || warn "Service inactive"
  curl -sf "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1 && ok "Health OK" || warn "Health check failed"
  if [[ -f "${INSTALL_ROOT}/current/VERSION" ]]; then
    echo "  Version: $(cat "${INSTALL_ROOT}/current/VERSION")"
  fi
}

do_backup() {
  require_root
  local ts backup_path
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  backup_path="${DATA_DIR}/backups/manual-${ts}"
  mkdir -p "${backup_path}"
  cp -a "${CONFIG_DIR}" "${backup_path}/config" 2>/dev/null || true
  cp -a "${DATA_DIR}/planasli.db" "${backup_path}/" 2>/dev/null || true
  ok "Backup created: ${backup_path}"
}

do_restore() {
  require_root
  echo "Available backups:"
  ls -1 "${DATA_DIR}/backups/" 2>/dev/null || { err "No backups found"; return; }
  read -r -p "Enter backup directory name: " bname
  local bpath="${DATA_DIR}/backups/${bname}"
  if [[ ! -d "${bpath}" ]]; then
    err "Backup not found"
    return
  fi
  systemctl stop planasli-ssh.service || true
  cp -a "${bpath}/planasli.db" "${DATA_DIR}/" 2>/dev/null || true
  cp -a "${bpath}/config/." "${CONFIG_DIR}/" 2>/dev/null || true
  systemctl start planasli-ssh.service
  ok "Restore complete"
}

do_uninstall() {
  require_root
  echo ""
  warn "This will remove the PlanAsli panel ONLY."
  warn "Managed SSH accounts will NOT be deleted unless you confirm separately."
  read -r -p "Remove panel? [y/N]: " ans
  if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
    return
  fi
  systemctl stop planasli-ssh.service 2>/dev/null || true
  systemctl disable planasli-ssh.service 2>/dev/null || true
  systemctl stop planasli-update-check.timer 2>/dev/null || true
  rm -f /etc/systemd/system/planasli-ssh.service
  rm -f /etc/systemd/system/planasli-update-check.timer
  rm -f /etc/systemd/system/planasli-update-check.service
  systemctl daemon-reload
  rm -rf "${INSTALL_ROOT}"
  read -r -p "Also remove data and config (${DATA_DIR}, ${CONFIG_DIR})? [y/N]: " ans2
  if [[ "${ans2}" == "y" || "${ans2}" == "Y" ]]; then
    rm -rf "${DATA_DIR}" "${CONFIG_DIR}" "${LOG_DIR}"
  fi
  ok "Panel uninstalled. SSH accounts were not touched."
}

# Entry
if [[ "${1:-}" == "--unattended" ]]; then
  do_fresh_install
else
  require_root
  show_menu
fi
