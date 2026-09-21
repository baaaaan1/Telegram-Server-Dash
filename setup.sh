#!/usr/bin/env bash

set -Eeuo pipefail

SERVICE_NAME="telegram-server-dash.service"
SERVICE_USER="tsd"
SERVICE_GROUP="tsd"
APP_ROOT="/opt/telegram-server-dash"
RELEASES_DIR="${APP_ROOT}/releases"
CURRENT_LINK="${APP_ROOT}/current"
CONFIG_DIR="/etc/telegram-server-dash"
ENV_FILE="${CONFIG_DIR}/telegram-server-dash.env"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
DATA_DIR="/var/lib/telegram-server-dash"
DATABASE_FILE="${DATA_DIR}/bot.db"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}"
LOCK_FILE="/run/lock/telegram-server-dash-setup.lock"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CANDIDATE_RELEASE=""
ENV_BACKUP=""
ENV_CHANGE_PENDING=0
ENV_PREVIOUSLY_EXISTS=0
# Optional runtime settings that are not prompted for but must survive a rewrite.
OPTIONAL_ENV_KEYS=(
    OPERATOR_USER_IDS
    VIEWER_USER_IDS
    STRICT_USERNAME_MATCH
    TSD_PIN
    PIN_TTL_SECONDS
    AUTH_MAX_ATTEMPTS
    AUTH_LOCKOUT_SECONDS
    RATE_LIMIT_PER_MINUTE
)

usage() {
    cat <<'EOF'
Usage: sudo ./setup.sh <command> [option]

Commands:
  install              Install or repair the native systemd deployment
  update               Deploy the current checkout without replacing config/data
  configure            Update BOT_TOKEN and ADMIN_USER_IDS, then restart
  status               Show service status and recent journal entries
  logs                 Follow the service journal
  uninstall [--purge]  Remove the service/app; --purge also deletes config/data
EOF
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

info() {
    printf '%s\n' "$*"
}

cleanup() {
    if [[ -n "${CANDIDATE_RELEASE}" && -d "${CANDIDATE_RELEASE}" ]]; then
        if [[ ! -L "${CURRENT_LINK}" ]] || [[ "$(readlink -f -- "${CURRENT_LINK}")" != "${CANDIDATE_RELEASE}" ]]; then
            rm -rf -- "${CANDIDATE_RELEASE}"
        fi
    fi
    restore_environment_change
}
trap cleanup EXIT

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run this command as root, for example: sudo ./setup.sh $*"
}

check_platform() {
    command -v systemctl >/dev/null 2>&1 || die "systemctl is required. Use an Ubuntu/Debian systemd host."
    [[ -d /run/systemd/system ]] || die "systemd is not running as PID 1 on this host."
    command -v apt-get >/dev/null 2>&1 || die "apt-get is required. Only Ubuntu and Debian are supported."
    [[ -r /etc/os-release ]] || die "Cannot identify the operating system: /etc/os-release is missing."

    local os_id os_like
    os_id="$(awk -F= '$1 == "ID" {gsub(/\"/, "", $2); print $2}' /etc/os-release)"
    os_like="$(awk -F= '$1 == "ID_LIKE" {gsub(/\"/, "", $2); print $2}' /etc/os-release)"
    if [[ "${os_id}" != "ubuntu" && "${os_id}" != "debian" && " ${os_like} " != *" debian "* ]]; then
        die "Unsupported OS '${os_id:-unknown}'. Use Ubuntu or Debian."
    fi
}

acquire_lock() {
    command -v flock >/dev/null 2>&1 || die "flock is required (install the util-linux package)."
    exec 9>"${LOCK_FILE}"
    flock -n 9 || die "Another setup.sh lifecycle command is already running."
}

install_packages() {
    info "Installing required OS packages..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git iputils-ping procps ca-certificates tar util-linux

    python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
        die "Python 3.11 or newer is required. Upgrade to a supported Ubuntu/Debian release."
}

ensure_service_account() {
    if getent passwd "${SERVICE_USER}" >/dev/null; then
        local passwd_entry user_id primary_group login_shell
        passwd_entry="$(getent passwd "${SERVICE_USER}")"
        user_id="$(cut -d: -f3 <<<"${passwd_entry}")"
        primary_group="$(getent group "$(cut -d: -f4 <<<"${passwd_entry}")" | cut -d: -f1)"
        login_shell="$(cut -d: -f7 <<<"${passwd_entry}")"
        [[ "${user_id}" -lt 1000 ]] || die "Existing '${SERVICE_USER}' account is not a system user."
        [[ "${primary_group}" == "${SERVICE_GROUP}" ]] || die "Existing '${SERVICE_USER}' account must use group '${SERVICE_GROUP}'."
        [[ "${login_shell}" == "/usr/sbin/nologin" || "${login_shell}" == "/bin/false" ]] || \
            die "Existing '${SERVICE_USER}' account must use a locked login shell."
        return
    fi

    if getent group "${SERVICE_GROUP}" >/dev/null; then
        useradd --system --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --gid "${SERVICE_GROUP}" "${SERVICE_USER}"
    else
        useradd --system --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --user-group "${SERVICE_USER}"
    fi
}

ensure_directories() {
    install -d -o root -g root -m 0755 "${APP_ROOT}" "${RELEASES_DIR}"
    install -d -o root -g "${SERVICE_GROUP}" -m 0750 "${CONFIG_DIR}"
    install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${DATA_DIR}"
}

normalize_persistent_permissions() {
    local database_part
    if [[ -f "${CONFIG_FILE}" ]]; then
        chown root:"${SERVICE_GROUP}" "${CONFIG_FILE}"
        chmod 0640 "${CONFIG_FILE}"
    fi
    if [[ -f "${ENV_FILE}" ]]; then
        chown root:root "${ENV_FILE}"
        chmod 0600 "${ENV_FILE}"
    fi
    if [[ -f "${DATABASE_FILE}" ]]; then
        chown "${SERVICE_USER}":"${SERVICE_GROUP}" "${DATABASE_FILE}"
        chmod 0600 "${DATABASE_FILE}"
    fi
    shopt -s nullglob
    for database_part in "${DATABASE_FILE}"-*; do
        chown "${SERVICE_USER}":"${SERVICE_GROUP}" "${database_part}"
        chmod 0600 "${database_part}"
    done
    shopt -u nullglob
}

read_env_value() {
    local key="$1"
    [[ -r "${ENV_FILE}" ]] || return 0
    awk -v key="${key}" 'index($0, key "=") == 1 {sub("^[^=]*=", ""); print; exit}' "${ENV_FILE}"
}

preserve_optional_env_values() {
    local key value
    for key in "${OPTIONAL_ENV_KEYS[@]}"; do
        value="$(read_env_value "${key}")"
        [[ -n "${value}" ]] || continue
        printf '%s=%s\n' "${key}" "${value}"
    done
}

validate_token() {
    [[ "$1" =~ ^[0-9]+:[A-Za-z0-9_-]{20,}$ ]] || \
        die "BOT_TOKEN has an invalid format. Obtain the token from BotFather."
}

validate_admin_ids() {
    [[ "$1" =~ ^[0-9]+(:[A-Za-z0-9_]{5,32})?(,[0-9]+(:[A-Za-z0-9_]{5,32})?)*$ ]] || \
        die "ADMIN_USER_IDS must be comma-separated user IDs, optionally bound to a username (ID:username)."
}

prompt_runtime_values() {
    local existing_token existing_admin existing_log entered_token entered_admin
    existing_token="$(read_env_value BOT_TOKEN)"
    existing_admin="$(read_env_value ADMIN_USER_IDS)"
    existing_log="$(read_env_value LOG_CHAT_ID)"

    [[ -r /dev/tty ]] || die "Interactive configuration requires a TTY."
    if [[ -n "${existing_token}" ]]; then
        printf 'BOT_TOKEN (leave blank to keep the existing token): ' >/dev/tty
    else
        printf 'BOT_TOKEN: ' >/dev/tty
    fi
    IFS= read -r -s entered_token </dev/tty || die "Unable to read BOT_TOKEN."
    printf '\n' >/dev/tty
    BOT_TOKEN_VALUE="${entered_token:-${existing_token}}"
    validate_token "${BOT_TOKEN_VALUE}"

    if [[ -n "${existing_admin}" ]]; then
        printf 'ADMIN_USER_IDS [%s]: ' "${existing_admin}" >/dev/tty
    else
        printf 'ADMIN_USER_IDS (comma-separated, optional ID:username, at least one): ' >/dev/tty
    fi
    IFS= read -r entered_admin </dev/tty || die "Unable to read ADMIN_USER_IDS."
    entered_admin="${entered_admin//[[:space:]]/}"
    ADMIN_USER_IDS_VALUE="${entered_admin:-${existing_admin}}"
    validate_admin_ids "${ADMIN_USER_IDS_VALUE}"
    LOG_CHAT_ID_VALUE="${existing_log}"
    [[ "${LOG_CHAT_ID_VALUE}" =~ ^(-?[0-9]+)?$ ]] || die "Existing LOG_CHAT_ID is invalid."
}

prepare_environment_change() {
    ENV_CHANGE_PENDING=1
    ENV_PREVIOUSLY_EXISTS=0
    ENV_BACKUP=""
    if [[ -f "${ENV_FILE}" ]]; then
        ENV_PREVIOUSLY_EXISTS=1
        ENV_BACKUP="$(mktemp "${CONFIG_DIR}/.env.backup.XXXXXX")"
        cp -a -- "${ENV_FILE}" "${ENV_BACKUP}"
    fi
}

restore_environment_change() {
    [[ "${ENV_CHANGE_PENDING}" -eq 1 ]] || return 0
    if [[ "${ENV_PREVIOUSLY_EXISTS}" -eq 1 && -f "${ENV_BACKUP}" ]]; then
        mv -f -- "${ENV_BACKUP}" "${ENV_FILE}"
    else
        rm -f -- "${ENV_FILE}"
    fi
    ENV_BACKUP=""
    ENV_CHANGE_PENDING=0
    ENV_PREVIOUSLY_EXISTS=0
}

commit_environment_change() {
    [[ -z "${ENV_BACKUP}" ]] || rm -f -- "${ENV_BACKUP}"
    ENV_BACKUP=""
    ENV_CHANGE_PENDING=0
    ENV_PREVIOUSLY_EXISTS=0
}

write_environment_file() {
    local temp_file
    umask 077
    temp_file="$(mktemp "${CONFIG_DIR}/.telegram-server-dash.env.XXXXXX")"
    {
        printf 'BOT_TOKEN=%s\n' "${BOT_TOKEN_VALUE}"
        printf 'ADMIN_USER_IDS=%s\n' "${ADMIN_USER_IDS_VALUE}"
        printf 'LOG_CHAT_ID=%s\n' "${LOG_CHAT_ID_VALUE}"
        printf 'ENV=production\n'
        printf 'DATABASE_PATH=%s\n' "${DATABASE_FILE}"
        printf 'TSD_CONFIG=%s\n' "${CONFIG_FILE}"
        preserve_optional_env_values
    } >"${temp_file}"
    chown root:root "${temp_file}"
    chmod 0600 "${temp_file}"
    mv -f -- "${temp_file}" "${ENV_FILE}"
}

confirm() {
    local prompt="$1" response
    printf '%s [y/N]: ' "${prompt}" >/dev/tty
    IFS= read -r response </dev/tty || return 1
    [[ "${response}" =~ ^[Yy]$ ]]
}

seed_config_and_data() {
    if [[ ! -e "${CONFIG_FILE}" ]]; then
        if [[ -f "${SOURCE_DIR}/config/config.yaml" ]] && \
            confirm "Import repository-local config/config.yaml"; then
            install -o root -g "${SERVICE_GROUP}" -m 0640 \
                "${SOURCE_DIR}/config/config.yaml" "${CONFIG_FILE}"
        else
            install -o root -g "${SERVICE_GROUP}" -m 0640 \
                "${SOURCE_DIR}/config/config.yaml.example" "${CONFIG_FILE}"
        fi
    fi

    if [[ ! -e "${DATABASE_FILE}" && -f "${SOURCE_DIR}/data/bot.db" ]] && \
        confirm "Import repository-local data/bot.db"; then
        install -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0600 \
            "${SOURCE_DIR}/data/bot.db" "${DATABASE_FILE}"
    fi
}

load_existing_runtime_values() {
    BOT_TOKEN_VALUE="$(read_env_value BOT_TOKEN)"
    ADMIN_USER_IDS_VALUE="$(read_env_value ADMIN_USER_IDS)"
    LOG_CHAT_ID_VALUE="$(read_env_value LOG_CHAT_ID)"
    validate_token "${BOT_TOKEN_VALUE}"
    validate_admin_ids "${ADMIN_USER_IDS_VALUE}"
    [[ "${LOG_CHAT_ID_VALUE}" =~ ^(-?[0-9]+)?$ ]] || die "Existing LOG_CHAT_ID is invalid."
}

create_release() {
    local release_id
    release_id="$(date -u +%Y%m%d%H%M%S)-$$"
    CANDIDATE_RELEASE="${RELEASES_DIR}/${release_id}"
    install -d -o root -g root -m 0755 "${CANDIDATE_RELEASE}"

    info "Copying application into release ${release_id}..."
    tar -C "${SOURCE_DIR}" \
        --exclude='./.git' \
        --exclude='./.venv' \
        --exclude='./venv' \
        --exclude='./.env*' \
        --exclude='./.commandcode' \
        --exclude='./.github' \
        --exclude='./.kilo' \
        --exclude='./data' \
        --exclude='./deploy.logs' \
        --exclude='./.pytest_cache' \
        --exclude='./.ruff_cache' \
        --exclude='./.mypy_cache' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.db' \
        -cf - . | tar -C "${CANDIDATE_RELEASE}" -xf -

    python3 -m venv "${CANDIDATE_RELEASE}/.venv"
    "${CANDIDATE_RELEASE}/.venv/bin/python" -m pip install \
        --disable-pip-version-check -r "${CANDIDATE_RELEASE}/requirements.txt"
    "${CANDIDATE_RELEASE}/.venv/bin/python" -m compileall -q "${CANDIDATE_RELEASE}" || \
        die "Python bytecode compilation failed. Check for syntax errors."
    chown -R root:root "${CANDIDATE_RELEASE}"
}

validate_release() {
    local release="$1"
    BOT_TOKEN="${BOT_TOKEN_VALUE}" \
    ADMIN_USER_IDS="${ADMIN_USER_IDS_VALUE}" \
    LOG_CHAT_ID="${LOG_CHAT_ID_VALUE}" \
    ENV=production \
    DATABASE_PATH="${DATABASE_FILE}" \
    TSD_CONFIG="${CONFIG_FILE}" \
    PYTHONPATH="${release}" \
        "${release}/.venv/bin/python" - "${CONFIG_FILE}" <<'PY'
import sys
from pathlib import Path

from config.servers import load_server_registry
from config.settings import BotSettings

BotSettings()
load_server_registry(Path(sys.argv[1]))
PY
}

start_or_restart_service() {
    local attempt
    systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        systemctl restart "${SERVICE_NAME}" || return 1
    else
        systemctl start "${SERVICE_NAME}" || return 1
    fi
    for ((attempt = 1; attempt <= 10; attempt++)); do
        if systemctl is-failed --quiet "${SERVICE_NAME}"; then
            return 1
        fi
        if systemctl is-active --quiet "${SERVICE_NAME}"; then
            sleep 2
            systemctl is-active --quiet "${SERVICE_NAME}"
            return
        fi
        sleep 1
    done
    return 1
}

rollback_activation() {
    local old_release="$1" unit_backup="$2" rollback_link
    systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
    if [[ -n "${old_release}" && -d "${old_release}" ]]; then
        rollback_link="${APP_ROOT}/.current.rollback.$$"
        ln -s -- "${old_release}" "${rollback_link}"
        mv -Tf -- "${rollback_link}" "${CURRENT_LINK}"
    else
        rm -f -- "${CURRENT_LINK}"
    fi

    if [[ -n "${unit_backup}" && -f "${unit_backup}" ]]; then
        mv -f -- "${unit_backup}" "${UNIT_FILE}"
    else
        rm -f -- "${UNIT_FILE}"
    fi
    systemctl daemon-reload || true
    restore_environment_change

    if [[ -n "${old_release}" && -d "${old_release}" ]]; then
        systemctl start "${SERVICE_NAME}" || true
    else
        systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
    fi
}

show_diagnostics() {
    systemctl status "${SERVICE_NAME}" --no-pager --full || true
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
}

prune_releases() {
    local current="$1" previous="$2" release
    shopt -s nullglob
    for release in "${RELEASES_DIR}"/*; do
        if [[ "${release}" != "${current}" && "${release}" != "${previous}" ]]; then
            rm -rf -- "${release}"
        fi
    done
    shopt -u nullglob
}

activate_release() {
    local old_release="" unit_backup="" new_link
    if [[ -L "${CURRENT_LINK}" ]]; then
        old_release="$(readlink -f -- "${CURRENT_LINK}")"
    fi
    if [[ -f "${UNIT_FILE}" ]]; then
        unit_backup="$(mktemp /run/telegram-server-dash-unit.XXXXXX)"
        cp -a -- "${UNIT_FILE}" "${unit_backup}"
    fi

    if ! install -o root -g root -m 0644 \
        "${SOURCE_DIR}/deploy/telegram-server-dash.service" "${UNIT_FILE}"; then
        rollback_activation "${old_release}" "${unit_backup}"
        die "Unable to install the systemd unit; the previous deployment was restored."
    fi
    if ! systemctl daemon-reload; then
        rollback_activation "${old_release}" "${unit_backup}"
        die "systemd rejected the unit; the previous deployment was restored."
    fi
    new_link="${APP_ROOT}/.current.$$"
    if ! ln -s -- "${CANDIDATE_RELEASE}" "${new_link}" || \
        ! mv -Tf -- "${new_link}" "${CURRENT_LINK}"; then
        rm -f -- "${new_link}"
        rollback_activation "${old_release}" "${unit_backup}"
        die "Unable to activate the release; the previous deployment was restored."
    fi
    if ! systemctl enable "${SERVICE_NAME}" >/dev/null; then
        rollback_activation "${old_release}" "${unit_backup}"
        die "Unable to enable the service; the previous deployment was restored."
    fi

    if start_or_restart_service; then
        info "Service is active."
        prune_releases "${CANDIDATE_RELEASE}" "${old_release}"
        CANDIDATE_RELEASE=""
        [[ -z "${unit_backup}" ]] || rm -f -- "${unit_backup}"
        commit_environment_change
        return
    fi

    info "New release failed to start; restoring the previous deployment." >&2
    show_diagnostics
    rollback_activation "${old_release}" "${unit_backup}"
    die "Deployment failed. The previous release and persistent data were preserved."
}

require_existing_install() {
    [[ -L "${CURRENT_LINK}" && -f "${ENV_FILE}" && -f "${CONFIG_FILE}" ]] || \
        die "No complete installation found. Run: sudo ./setup.sh install"
}

command_install() {
    install_packages
    ensure_service_account
    ensure_directories
    seed_config_and_data
    normalize_persistent_permissions
    prompt_runtime_values
    create_release
    validate_release "${CANDIDATE_RELEASE}"
    prepare_environment_change
    write_environment_file
    activate_release
}

command_update() {
    require_existing_install
    install_packages
    ensure_service_account
    ensure_directories
    normalize_persistent_permissions
    load_existing_runtime_values
    create_release
    validate_release "${CANDIDATE_RELEASE}"
    activate_release
}

command_configure() {
    require_existing_install
    normalize_persistent_permissions
    prompt_runtime_values
    prepare_environment_change
    write_environment_file
    if ! validate_release "$(readlink -f -- "${CURRENT_LINK}")" || ! start_or_restart_service; then
        info "Configuration failed; restoring the previous environment file." >&2
        show_diagnostics
        restore_environment_change
        systemctl restart "${SERVICE_NAME}" || true
        die "Configuration was not applied."
    fi
    commit_environment_change
    info "Configuration updated and service restarted."
}

command_status() {
    local status_code=0
    systemctl status "${SERVICE_NAME}" --no-pager --full || status_code=$?
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
    return "${status_code}"
}

command_logs() {
    journalctl -u "${SERVICE_NAME}" -f
}

command_uninstall() {
    local purge="${1:-}"
    [[ -z "${purge}" || "${purge}" == "--purge" ]] || die "uninstall accepts only the optional --purge flag."

    systemctl disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
    rm -f -- "${UNIT_FILE}"
    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
    rm -rf -- "${APP_ROOT}"

    if [[ "${purge}" == "--purge" ]]; then
        local confirmation
        printf 'Type PURGE to delete %s and %s: ' "${CONFIG_DIR}" "${DATA_DIR}" >/dev/tty
        IFS= read -r confirmation </dev/tty || die "Unable to read purge confirmation."
        [[ "${confirmation}" == "PURGE" ]] || die "Purge cancelled; configuration and data were preserved."
        rm -rf -- "${CONFIG_DIR}" "${DATA_DIR}"
        if getent passwd "${SERVICE_USER}" >/dev/null; then
            userdel "${SERVICE_USER}"
        fi
        if getent group "${SERVICE_GROUP}" >/dev/null; then
            groupdel "${SERVICE_GROUP}" >/dev/null 2>&1 || true
        fi
        info "Service, application, configuration, and data removed."
    else
        info "Service and application removed. Configuration and data were preserved."
    fi
}

main() {
    local command="${1:-}"
    if [[ -z "${command}" ]]; then
        usage
        exit 2
    fi
    shift

    case "${command}" in
        install | update | configure | status | logs | uninstall) ;;
        *)
            usage >&2
            exit 2
            ;;
    esac

    require_root "${command}"
    check_platform

    case "${command}" in
        install)
            [[ "$#" -eq 0 ]] || die "install does not accept additional arguments."
            acquire_lock
            command_install
            ;;
        update)
            [[ "$#" -eq 0 ]] || die "update does not accept additional arguments."
            acquire_lock
            command_update
            ;;
        configure)
            [[ "$#" -eq 0 ]] || die "configure does not accept additional arguments."
            acquire_lock
            command_configure
            ;;
        status)
            [[ "$#" -eq 0 ]] || die "status does not accept additional arguments."
            command_status
            ;;
        logs)
            [[ "$#" -eq 0 ]] || die "logs does not accept additional arguments."
            command_logs
            ;;
        uninstall)
            [[ "$#" -le 1 ]] || die "uninstall accepts only the optional --purge flag."
            acquire_lock
            command_uninstall "${1:-}"
            ;;
    esac
}

main "$@"
