#!/usr/bin/env bash
#
# setup.sh - lifecycle CLI for the Telegram Server Dash systemd deployment.
#
# Commands: install, update, configure, status, logs, uninstall [--purge]
# Presentation lives in deploy/lib/ui.sh: chrome (banner, progress, spinners,
# diagnostics, errors) is written to stderr while panels, tables and journal
# output stay on stdout, so `setup.sh status > report.txt` yields clean data.

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
UI_LIB="${SOURCE_DIR}/deploy/lib/ui.sh"
CANDIDATE_RELEASE=""
ENV_BACKUP=""
ENV_CHANGE_PENDING=0
ENV_PREVIOUSLY_EXISTS=0
COMMAND=""
COMMAND_ARGS=()
EXIT_STATUS=0
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

if [[ ! -r "${UI_LIB}" ]]; then
    printf 'Error: the CLI presentation library is missing: %s\n' "${UI_LIB}" >&2
    printf 'Run setup.sh from a complete checkout of the repository.\n' >&2
    exit 1
fi

# shellcheck source=deploy/lib/ui.sh
source "${UI_LIB}"

UI_SCRIPT_NAME="setup.sh"

die() {
    ui_die "$1" "${2:-}"
}

confirm() {
    ui_confirm "$1"
}

app_version() {
    local version=""
    if [[ -r "${SOURCE_DIR}/pyproject.toml" ]]; then
        version="$(awk -F'"' '/^version[[:space:]]*=/ {print $2; exit}' "${SOURCE_DIR}/pyproject.toml")"
    fi
    printf '%s' "${version:-unknown}"
    return 0
}

app_revision() {
    local revision=""
    if command -v git >/dev/null 2>&1; then
        revision="$(git -C "${SOURCE_DIR}" rev-parse --short HEAD 2>/dev/null || true)"
    fi
    printf '%s' "${revision}"
    return 0
}

cleanup() {
    UI_EXITING=1
    ui_cleanup
    if [[ -n "${CANDIDATE_RELEASE}" && -d "${CANDIDATE_RELEASE}" ]]; then
        if [[ ! -L "${CURRENT_LINK}" ]] || [[ "$(readlink -f -- "${CURRENT_LINK}")" != "${CANDIDATE_RELEASE}" ]]; then
            rm -rf -- "${CANDIDATE_RELEASE}"
        fi
    fi
    restore_environment_change
}

trap cleanup EXIT
trap 'ui_on_error "$?" "${LINENO}" "${BASH_COMMAND}"' ERR

usage() {
    local fd="${1:-1}" reset="${UI_C_RESET}" dim="${UI_C_DIM}"
    local strong="${UI_C_BOLD_WHITE}" heading="${UI_C_BOLD_BLUE}"
    local command_color="${UI_C_BOLD_GREEN}" option_color="${UI_C_CYAN}"
    {
        printf '\n'
        printf '  %sTELEGRAM SERVER DASH%s %s v%s\n' "${strong}" "${reset}" "${UI_G_SEP}" "${UI_VERSION}"
        printf '  %sNative systemd deployment and operations for the Telegram bot.%s\n' "${dim}" "${reset}"
        printf '\n'
        printf '  %sUsage%s  sudo ./%s <command> [options]\n' "${heading}" "${reset}" "${UI_SCRIPT_NAME}"
        printf '\n'
        printf '  %sCommands%s\n' "${heading}" "${reset}"
        printf '    %s%-20s%s%s\n' "${command_color}" "install" "${reset}" "Install or repair the systemd deployment"
        printf '    %s%-20s%s%s\n' "${command_color}" "update" "${reset}" "Deploy this checkout without touching config or data"
        printf '    %s%-20s%s%s\n' "${command_color}" "configure" "${reset}" "Update BOT_TOKEN and ADMIN_USER_IDS, then restart"
        printf '    %s%-20s%s%s\n' "${command_color}" "status" "${reset}" "Service state, managed paths, recent journal"
        printf '    %s%-20s%s%s\n' "${command_color}" "logs" "${reset}" "Follow the service journal until Ctrl+C"
        printf '    %s%-20s%s%s\n' "${command_color}" "uninstall [--purge]" "${reset}" "Remove service and app; --purge deletes config and data"
        printf '\n'
        printf '  %sOptions%s\n' "${heading}" "${reset}"
        printf '    %s%-20s%s%s\n' "${option_color}" "-h, --help" "${reset}" "Show this help and exit"
        printf '    %s%-20s%s%s\n' "${option_color}" "-V, --version" "${reset}" "Show the installer version and exit"
        printf '    %s%-20s%s%s\n' "${option_color}" "--no-color" "${reset}" "Disable ANSI colour (NO_COLOR is also honoured)"
        printf '    %s%-20s%s%s\n' "${option_color}" "--plain" "${reset}" "Disable colour, unicode glyphs and animations"
        printf '    %s%-20s%s%s\n' "${option_color}" "--no-animation" "${reset}" "Keep colour but drop the spinner"
        printf '    %s%-20s%s%s\n' "${option_color}" "--no-banner" "${reset}" "Skip the branded header"
        printf '\n'
        printf '  %sEnvironment%s\n' "${heading}" "${reset}"
        printf '    %s\n' "TSD_PLAIN / TSD_ASCII / TSD_NO_COLOR / TSD_NO_ANIMATION / TSD_NO_BANNER"
        printf '\n'
        printf '  %sNotes%s\n' "${heading}" "${reset}"
        printf '    %s\n' "Every command except --help and --version must run as root."
        printf '    %s\n' "Chrome is written to stderr, data to stdout, so output can be piped safely."
        printf '\n'
    } >&"${fd}"
    return 0
}

require_root() {
    local command="$1"
    if [[ "${EUID}" -eq 0 ]]; then
        return 0
    fi
    ui_die "Administrator privileges are required for '${command}'." \
        "Retry with: sudo ./${UI_SCRIPT_NAME} ${command}"
}

check_platform() {
    if ! command -v systemctl >/dev/null 2>&1; then
        ui_die "systemctl was not found on this host." "Use Ubuntu or Debian with systemd as PID 1."
    fi
    if [[ ! -d /run/systemd/system ]]; then
        ui_die "systemd is not running as PID 1 on this host."
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        ui_die "apt-get was not found on this host." "Only Ubuntu and Debian are supported."
    fi
    if [[ ! -r /etc/os-release ]]; then
        ui_die "Cannot identify the operating system." "/etc/os-release is missing."
    fi

    local os_id os_like os_name
    os_id="$(awk -F= '$1 == "ID" {gsub(/\"/, "", $2); print $2}' /etc/os-release)"
    os_like="$(awk -F= '$1 == "ID_LIKE" {gsub(/\"/, "", $2); print $2}' /etc/os-release)"
    if [[ "${os_id}" != "ubuntu" && "${os_id}" != "debian" && " ${os_like} " != *" debian "* ]]; then
        ui_die "Unsupported operating system '${os_id:-unknown}'." "Use Ubuntu or Debian."
    fi

    os_name="$(awk -F= '$1 == "PRETTY_NAME" {gsub(/\"/, "", $2); print $2}' /etc/os-release)"
    ui_ok "Supported platform detected: ${os_name:-${os_id}}"
}

preflight() {
    local command="$1"
    require_root "${command}"
    ui_section "Preflight"
    ui_ok "Running as root"
    check_platform
}

acquire_lock() {
    if ! command -v flock >/dev/null 2>&1; then
        ui_die "flock is required." "Install the util-linux package and retry."
    fi
    exec 9>"${LOCK_FILE}"
    if ! flock -n 9; then
        ui_die "Another setup.sh lifecycle command is already running." \
            "Wait for it to finish, then run 'install' again."
    fi
}

install_packages() {
    export DEBIAN_FRONTEND=noninteractive
    ui_run_quiet "refreshing the APT package index" apt-get update
    ui_run_quiet "installing OS packages (python3, venv, pip, git, ping, procps)" \
        apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git iputils-ping procps ca-certificates tar util-linux

    python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
        die "Python 3.11 or newer is required." "Upgrade to a supported Ubuntu or Debian release."
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
        ui_note "reusing the existing ${SERVICE_USER} system account"
        return
    fi

    if getent group "${SERVICE_GROUP}" >/dev/null; then
        useradd --system --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --gid "${SERVICE_GROUP}" "${SERVICE_USER}"
    else
        useradd --system --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --user-group "${SERVICE_USER}"
    fi
    ui_note "created the ${SERVICE_USER} system account"
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
        die "BOT_TOKEN has an invalid format." "Copy the full token from @BotFather and retry."
}

validate_admin_ids() {
    [[ "$1" =~ ^[0-9]+(:[A-Za-z0-9_]{5,32})?(,[0-9]+(:[A-Za-z0-9_]{5,32})?)*$ ]] || \
        die "ADMIN_USER_IDS must be comma-separated Telegram user IDs." \
            "Each entry is an ID or ID:username, for example 123456789:namauser"
}

prompt_runtime_values() {
    local existing_token existing_admin existing_log entered_token entered_admin
    local token_hint admin_hint
    existing_token="$(read_env_value BOT_TOKEN)"
    existing_admin="$(read_env_value ADMIN_USER_IDS)"
    existing_log="$(read_env_value LOG_CHAT_ID)"

    if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
        die "Interactive configuration requires a terminal." "Run the command from an interactive shell."
    fi

    ui_section "Runtime configuration"
    ui_hint "Values are stored in ${ENV_FILE} with mode 0600 and are never printed back."

    if [[ -n "${existing_token}" ]]; then
        token_hint="leave blank to keep the stored token"
    else
        token_hint="token from @BotFather, for example 123456789:AAExampleTokenValue"
    fi
    entered_token="$(ui_prompt_secret "BOT_TOKEN" "${token_hint}")" || die "Unable to read BOT_TOKEN."
    BOT_TOKEN_VALUE="${entered_token:-${existing_token}}"
    validate_token "${BOT_TOKEN_VALUE}"

    if [[ -n "${existing_admin}" ]]; then
        admin_hint="stored value: ${existing_admin} (leave blank to keep it)"
    else
        admin_hint="comma-separated user IDs, optionally bound as ID:username, at least one"
    fi
    entered_admin="$(ui_prompt_text "ADMIN_USER_IDS" "${admin_hint}")" || die "Unable to read ADMIN_USER_IDS."
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
    ui_note "wrote ${ENV_FILE}"
}

seed_config_and_data() {
    if [[ ! -e "${CONFIG_FILE}" ]]; then
        if [[ -f "${SOURCE_DIR}/config/config.yaml" ]] && \
            confirm "Import repository-local config/config.yaml"; then
            install -o root -g "${SERVICE_GROUP}" -m 0640 \
                "${SOURCE_DIR}/config/config.yaml" "${CONFIG_FILE}"
            ui_note "imported config/config.yaml"
        else
            install -o root -g "${SERVICE_GROUP}" -m 0640 \
                "${SOURCE_DIR}/config/config.yaml.example" "${CONFIG_FILE}"
            ui_note "installed config.yaml.example, edit it to register your servers"
        fi
    else
        ui_note "keeping the existing ${CONFIG_FILE}"
    fi

    if [[ ! -e "${DATABASE_FILE}" && -f "${SOURCE_DIR}/data/bot.db" ]] && \
        confirm "Import repository-local data/bot.db"; then
        install -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0600 \
            "${SOURCE_DIR}/data/bot.db" "${DATABASE_FILE}"
        ui_note "imported data/bot.db"
    fi
}

load_existing_runtime_values() {
    BOT_TOKEN_VALUE="$(read_env_value BOT_TOKEN)"
    ADMIN_USER_IDS_VALUE="$(read_env_value ADMIN_USER_IDS)"
    LOG_CHAT_ID_VALUE="$(read_env_value LOG_CHAT_ID)"
    validate_token "${BOT_TOKEN_VALUE}"
    validate_admin_ids "${ADMIN_USER_IDS_VALUE}"
    [[ "${LOG_CHAT_ID_VALUE}" =~ ^(-?[0-9]+)?$ ]] || die "Existing LOG_CHAT_ID is invalid."
    ui_note "reusing the stored runtime configuration"
}

create_release() {
    local release_id
    release_id="$(date -u +%Y%m%d%H%M%S)-$$"
    CANDIDATE_RELEASE="${RELEASES_DIR}/${release_id}"
    install -d -o root -g root -m 0755 "${CANDIDATE_RELEASE}"
    ui_note "release ${release_id}"

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
    ui_run_quiet "installing Python dependencies into the release virtualenv" \
        "${CANDIDATE_RELEASE}/.venv/bin/python" -m pip install \
        --disable-pip-version-check --progress-bar off \
        -r "${CANDIDATE_RELEASE}/requirements.txt"
    "${CANDIDATE_RELEASE}/.venv/bin/python" -m compileall -q "${CANDIDATE_RELEASE}" || \
        die "Python bytecode compilation failed." "Check the release for syntax errors."
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

service_is_running() {
    systemctl is-active --quiet "${SERVICE_NAME}"
}

wait_for_service_active() {
    local attempt
    for ((attempt = 1; attempt <= 10; attempt++)); do
        if systemctl is-failed --quiet "${SERVICE_NAME}"; then
            return 1
        fi
        if systemctl is-active --quiet "${SERVICE_NAME}"; then
            sleep 2
            if systemctl is-active --quiet "${SERVICE_NAME}"; then
                return 0
            fi
            return 1
        fi
        sleep 1
    done
    return 1
}

start_or_restart_service() {
    local status=0
    systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
    ui_spinner_start "waiting for the service to report active"
    if service_is_running; then
        systemctl restart "${SERVICE_NAME}" || status=1
    else
        systemctl start "${SERVICE_NAME}" || status=1
    fi
    if (( status == 0 )); then
        if ! wait_for_service_active; then
            status=1
        fi
    fi
    ui_spinner_stop
    return "${status}"
}

rollback_activation() {
    local old_release="$1" unit_backup="$2" rollback_link status=0
    systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
    if [[ -n "${old_release}" && -d "${old_release}" ]]; then
        rollback_link="${APP_ROOT}/.current.rollback.$$"
        ln -s -- "${old_release}" "${rollback_link}" || status=1
        mv -Tf -- "${rollback_link}" "${CURRENT_LINK}" || status=1
    else
        rm -f -- "${CURRENT_LINK}" || status=1
    fi

    if [[ -n "${unit_backup}" && -f "${unit_backup}" ]]; then
        mv -f -- "${unit_backup}" "${UNIT_FILE}" || status=1
    else
        rm -f -- "${UNIT_FILE}" || status=1
    fi
    systemctl daemon-reload || true
    restore_environment_change

    if [[ -n "${old_release}" && -d "${old_release}" ]]; then
        systemctl start "${SERVICE_NAME}" || status=1
    else
        systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
    fi
    return "${status}"
}

restore_previous_release() {
    local old_release="$1" unit_backup="$2" reason="$3"
    if rollback_activation "${old_release}" "${unit_backup}"; then
        die "${reason} The previous deployment was restored."
    fi
    die "${reason} The rollback did not complete." \
        "Inspect ${UNIT_FILE} and ${APP_ROOT} on this host before retrying."
}

show_diagnostics() {
    ui_section "Diagnostics"
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
        restore_previous_release "${old_release}" "${unit_backup}" "Unable to install the systemd unit;"
    fi
    if ! systemctl daemon-reload; then
        restore_previous_release "${old_release}" "${unit_backup}" "systemd rejected the unit;"
    fi
    new_link="${APP_ROOT}/.current.$$"
    if ! ln -s -- "${CANDIDATE_RELEASE}" "${new_link}" || \
        ! mv -Tf -- "${new_link}" "${CURRENT_LINK}"; then
        rm -f -- "${new_link}" || true
        restore_previous_release "${old_release}" "${unit_backup}" "Unable to activate the release;"
    fi
    if ! systemctl enable "${SERVICE_NAME}" >/dev/null; then
        restore_previous_release "${old_release}" "${unit_backup}" "Unable to enable the service;"
    fi

    if start_or_restart_service; then
        prune_releases "${CANDIDATE_RELEASE}" "${old_release}"
        CANDIDATE_RELEASE=""
        [[ -z "${unit_backup}" ]] || rm -f -- "${unit_backup}"
        commit_environment_change
        return
    fi

    ui_stage_fail
    ui_warn "The new release failed to start; restoring the previous deployment."
    show_diagnostics
    if rollback_activation "${old_release}" "${unit_backup}"; then
        die "Deployment failed." "The previous release and persistent data were preserved."
    fi
    die "Deployment failed and the rollback did not complete." \
        "Inspect ${UNIT_FILE}, ${CURRENT_LINK} and ${APP_ROOT} on this host before retrying."
}

require_existing_install() {
    if [[ ! -L "${CURRENT_LINK}" || ! -f "${ENV_FILE}" || ! -f "${CONFIG_FILE}" ]]; then
        ui_die "No complete installation was found." "Run: sudo ./${UI_SCRIPT_NAME} install"
    fi
    ui_ok "Existing deployment detected under ${APP_ROOT}"
}

current_release_id() {
    local release=""
    if [[ -L "${CURRENT_LINK}" ]]; then
        release="$(readlink -f -- "${CURRENT_LINK}")"
    fi
    if [[ -z "${release}" ]]; then
        printf 'none'
        return 0
    fi
    printf '%s' "$(basename -- "${release}")"
    return 0
}

service_state() {
    local active="" sub_state=""
    active="$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true)"
    sub_state="$(systemctl show "${SERVICE_NAME}" --property=SubState --value 2>/dev/null || true)"
    if [[ -z "${active}" ]]; then
        printf 'unknown'
        return 0
    fi
    if [[ -n "${sub_state}" && "${sub_state}" != "dead" ]]; then
        printf '%s (%s)' "${active}" "${sub_state}"
        return 0
    fi
    printf '%s' "${active}"
    return 0
}

service_state_style() {
    local active=""
    active="$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true)"
    case "${active}" in
        active) printf 'ok' ;;
        failed) printf 'error' ;;
        *) printf 'warn' ;;
    esac
    return 0
}

format_duration() {
    local seconds="$1" days=0 hours=0 minutes=0
    days=$(( seconds / 86400 ))
    hours=$(( (seconds % 86400) / 3600 ))
    minutes=$(( (seconds % 3600) / 60 ))
    if (( days > 0 )); then
        printf '%dd %dh %dm' "${days}" "${hours}" "${minutes}"
        return 0
    fi
    if (( hours > 0 )); then
        printf '%dh %dm' "${hours}" "${minutes}"
        return 0
    fi
    printf '%dm %ds' "${minutes}" "$(( seconds % 60 ))"
    return 0
}

format_since() {
    local timestamp="$1" epoch="" now="" seconds=0
    if [[ -z "${timestamp}" || "${timestamp}" == "n/a" ]]; then
        printf 'not running'
        return 0
    fi
    if ! epoch="$(date -d "${timestamp}" +%s 2>/dev/null)"; then
        printf '%s' "${timestamp}"
        return 0
    fi
    now="$(date +%s)"
    seconds=$(( now - epoch ))
    if (( seconds < 0 )); then
        seconds=0
    fi
    format_duration "${seconds}"
    return 0
}

format_bytes() {
    local bytes="$1"
    if [[ ! "${bytes}" =~ ^[0-9]+$ ]]; then
        printf 'unknown'
        return 0
    fi
    awk -v value="${bytes}" 'BEGIN { printf "%.1f MiB", value / 1048576 }'
    return 0
}

path_state() {
    if [[ -e "$1" ]]; then
        printf 'present'
        return 0
    fi
    printf 'missing'
    return 0
}

path_style() {
    if [[ -e "$1" ]]; then
        printf 'ok'
        return 0
    fi
    printf 'warn'
    return 0
}

show_deployment_summary() {
    local state="" style="" release=""
    state="$(service_state)"
    style="$(service_state_style)"
    release="$(current_release_id)"
    ui_panel_begin "Deployment summary"
    ui_panel_row "Service" "${SERVICE_NAME}"
    ui_panel_row "State" "${state}" "${style}"
    ui_panel_row "Release" "${release}"
    ui_panel_row "Application" "${CURRENT_LINK}"
    ui_panel_row "Configuration" "${CONFIG_FILE}"
    ui_panel_row "Environment" "${ENV_FILE}"
    ui_panel_row "Database" "${DATABASE_FILE}"
    ui_panel_row "Follow logs" "sudo ./${UI_SCRIPT_NAME} logs"
    ui_panel_end
    return 0
}

read_unit_state() {
    local output="" line="" key="" value=""
    UNIT_LOAD_STATE="not-found"
    UNIT_ACTIVE_STATE="unknown"
    UNIT_SUB_STATE="unknown"
    UNIT_ENABLED_STATE="unknown"
    UNIT_MAIN_PID="0"
    UNIT_RESTARTS="0"
    UNIT_MEMORY=""
    UNIT_TASKS=""
    UNIT_SINCE=""
    if ! output="$(systemctl show "${SERVICE_NAME}" \
        --property=LoadState --property=ActiveState --property=SubState \
        --property=UnitFileState --property=MainPID --property=NRestarts \
        --property=MemoryCurrent --property=TasksCurrent \
        --property=ActiveEnterTimestamp --property=ExecMainStartTimestamp 2>/dev/null)"; then
        return 1
    fi
    while IFS= read -r line; do
        key="${line%%=*}"
        value="${line#*=}"
        case "${key}" in
            LoadState) UNIT_LOAD_STATE="${value}" ;;
            ActiveState) UNIT_ACTIVE_STATE="${value}" ;;
            SubState) UNIT_SUB_STATE="${value}" ;;
            UnitFileState) UNIT_ENABLED_STATE="${value}" ;;
            MainPID) UNIT_MAIN_PID="${value}" ;;
            NRestarts) UNIT_RESTARTS="${value}" ;;
            MemoryCurrent) UNIT_MEMORY="${value}" ;;
            TasksCurrent) UNIT_TASKS="${value}" ;;
            ActiveEnterTimestamp) UNIT_SINCE="${value}" ;;
            ExecMainStartTimestamp) [[ -n "${UNIT_SINCE}" ]] || UNIT_SINCE="${value}" ;;
        esac
    done <<<"${output}"
    return 0
}

show_recent_journal() {
    local lines="${1:-25}"
    ui_section_data "Recent journal"
    if ! journalctl -u "${SERVICE_NAME}" -n "${lines}" --no-pager -o short-iso 2>/dev/null; then
        ui_warn "The journal could not be read for ${SERVICE_NAME}."
        return 0
    fi
    ui_hint "Follow live output with: sudo ./${UI_SCRIPT_NAME} logs"
    return 0
}

show_unit_report() {
    local state_line="" style="" enabled="" uptime="" memory="" tasks=""
    if ! read_unit_state; then
        ui_die "systemctl could not read ${SERVICE_NAME}." "Check that the unit is installed."
    fi

    state_line="${UNIT_ACTIVE_STATE} (${UNIT_SUB_STATE})"
    case "${UNIT_ACTIVE_STATE}" in
        active) style="ok" ;;
        failed) style="error" ;;
        *) style="warn" ;;
    esac
    enabled="${UNIT_ENABLED_STATE}"
    if [[ -z "${enabled}" || "${enabled}" == "n/a" ]]; then
        enabled="unknown"
    fi
    uptime="$(format_since "${UNIT_SINCE}")"
    memory="$(format_bytes "${UNIT_MEMORY}")"
    tasks="${UNIT_TASKS}"
    if [[ ! "${tasks}" =~ ^[0-9]+$ ]]; then
        tasks="unknown"
    fi

    ui_panel_begin "Service state"
    ui_panel_row "Unit" "${SERVICE_NAME}"
    ui_panel_row "Unit file" "${UNIT_FILE}" "$(path_style "${UNIT_FILE}")"
    ui_panel_row "Load state" "${UNIT_LOAD_STATE}"
    ui_panel_row "Active state" "${state_line}" "${style}"
    ui_panel_row "Enabled" "${enabled}"
    ui_panel_row "Main PID" "${UNIT_MAIN_PID}"
    ui_panel_row "Running for" "${uptime}"
    ui_panel_row "Restarts" "${UNIT_RESTARTS}"
    ui_panel_row "Memory" "${memory}"
    ui_panel_row "Tasks" "${tasks}"
    ui_panel_row "Release" "$(current_release_id)"
    ui_panel_end
    return 0
}

show_managed_paths() {
    local path_width=$(( UI_WIDTH - 34 ))
    if (( path_width < 24 )); then
        path_width=24
    fi
    ui_section_data "Managed paths"
    ui_table_begin 16 "${path_width}" 10
    ui_table_head "Resource" "Path" "State"
    ui_table_row "$(path_style "${UNIT_FILE}")" "Service unit" "${UNIT_FILE}" "$(path_state "${UNIT_FILE}")"
    ui_table_row "$(path_style "${APP_ROOT}")" "Application" "${APP_ROOT}" "$(path_state "${APP_ROOT}")"
    ui_table_row "$(path_style "${CONFIG_FILE}")" "Configuration" "${CONFIG_FILE}" "$(path_state "${CONFIG_FILE}")"
    ui_table_row "$(path_style "${ENV_FILE}")" "Environment" "${ENV_FILE}" "$(path_state "${ENV_FILE}")"
    ui_table_row "$(path_style "${DATABASE_FILE}")" "Database" "${DATABASE_FILE}" "$(path_state "${DATABASE_FILE}")"
    ui_table_end
    return 0
}

command_install() {
    ui_plan 8
    ui_stage "Installing required OS packages"
    install_packages
    ui_stage_ok
    ui_stage "Creating the service account"
    ensure_service_account
    ui_stage_ok
    ui_stage "Preparing directories and persistent state"
    ensure_directories
    seed_config_and_data
    normalize_persistent_permissions
    ui_stage_ok
    ui_stage "Collecting runtime configuration"
    prompt_runtime_values
    ui_stage_ok
    ui_stage "Copying the application into a release"
    create_release
    ui_stage_ok
    ui_stage "Validating the release"
    validate_release "${CANDIDATE_RELEASE}"
    ui_stage_ok
    ui_stage "Writing the environment file"
    prepare_environment_change
    write_environment_file
    ui_stage_ok
    ui_stage "Activating the release and starting the service"
    activate_release
    ui_stage_ok
    show_deployment_summary
    ui_ok "Installation complete. The bot is now polling Telegram."
    ui_hint "Register servers in ${CONFIG_FILE}, then run: sudo ./${UI_SCRIPT_NAME} configure"
}

command_update() {
    ui_plan 8
    ui_stage "Verifying the existing deployment"
    require_existing_install
    ui_stage_ok
    ui_stage "Installing required OS packages"
    install_packages
    ui_stage_ok
    ui_stage "Creating the service account"
    ensure_service_account
    ui_stage_ok
    ui_stage "Preparing directories and persistent state"
    ensure_directories
    normalize_persistent_permissions
    ui_stage_ok
    ui_stage "Loading the stored runtime configuration"
    load_existing_runtime_values
    ui_stage_ok
    ui_stage "Copying the application into a release"
    create_release
    ui_stage_ok
    ui_stage "Validating the release"
    validate_release "${CANDIDATE_RELEASE}"
    ui_stage_ok
    ui_stage "Activating the release and restarting the service"
    activate_release
    ui_stage_ok
    show_deployment_summary
    ui_ok "Update complete. Configuration and persistent data were preserved."
}

command_configure() {
    require_existing_install
    ui_plan 3
    ui_stage "Reviewing the stored configuration"
    normalize_persistent_permissions
    prompt_runtime_values
    ui_stage_ok
    ui_stage "Writing the environment file"
    prepare_environment_change
    write_environment_file
    ui_stage_ok
    ui_stage "Validating and restarting the service"
    if ! validate_release "$(readlink -f -- "${CURRENT_LINK}")" || ! start_or_restart_service; then
        ui_stage_fail
        ui_warn "Configuration failed; restoring the previous environment file."
        show_diagnostics
        restore_environment_change
        systemctl restart "${SERVICE_NAME}" || true
        die "Configuration was not applied." "The stored environment file was restored unchanged."
    fi
    ui_stage_ok
    show_deployment_summary
    ui_ok "Configuration updated and the service restarted."
}

command_status() {
    if [[ ! -L "${CURRENT_LINK}" && ! -f "${UNIT_FILE}" ]]; then
        ui_warn "${SERVICE_NAME} is not installed on this host."
        ui_hint "Install it with: sudo ./${UI_SCRIPT_NAME} install"
        EXIT_STATUS=4
        return 0
    fi
    show_unit_report
    show_managed_paths
    show_recent_journal 25
    case "${UNIT_ACTIVE_STATE}" in
        active) EXIT_STATUS=0 ;;
        *) EXIT_STATUS=3 ;;
    esac
    return 0
}

command_logs() {
    if [[ ! -f "${UNIT_FILE}" ]]; then
        ui_die "${SERVICE_NAME} is not installed on this host." \
            "Install it with: sudo ./${UI_SCRIPT_NAME} install"
    fi
    ui_section "Following ${SERVICE_NAME}"
    ui_hint "Press Ctrl+C to stop following the journal."
    journalctl -u "${SERVICE_NAME}" -f || true
    return 0
}

command_uninstall() {
    local purge="${1:-}"
    if [[ -n "${purge}" && "${purge}" != "--purge" ]]; then
        die "uninstall accepts only the optional --purge flag." "Run 'sudo ./${UI_SCRIPT_NAME} --help' for details."
    fi

    ui_section "Uninstall"
    ui_warn "This removes ${SERVICE_NAME} and ${APP_ROOT}."
    if [[ "${purge}" == "--purge" ]]; then
        ui_warn "Configuration and data will be deleted after a typed confirmation."
    else
        ui_info "Configuration under ${CONFIG_DIR} and data under ${DATA_DIR} are preserved."
    fi

    ui_plan 3
    ui_stage "Stopping and disabling the service"
    systemctl disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
    ui_stage_ok
    ui_stage "Removing the systemd unit and application"
    rm -f -- "${UNIT_FILE}"
    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
    rm -rf -- "${APP_ROOT}"
    ui_stage_ok
    ui_stage "Removing configuration and data"
    if [[ "${purge}" == "--purge" ]]; then
        if ! ui_prompt_typed "Type PURGE to delete ${CONFIG_DIR} and ${DATA_DIR}" "PURGE"; then
            ui_stage_fail
            die "Purge cancelled; configuration and data were preserved."
        fi
        rm -rf -- "${CONFIG_DIR}" "${DATA_DIR}"
        if getent passwd "${SERVICE_USER}" >/dev/null; then
            userdel "${SERVICE_USER}"
        fi
        if getent group "${SERVICE_GROUP}" >/dev/null; then
            groupdel "${SERVICE_GROUP}" >/dev/null 2>&1 || true
        fi
    else
        ui_note "skipped, --purge was not requested"
    fi
    ui_stage_ok

    local path_width=$(( UI_WIDTH - 34 ))
    if (( path_width < 24 )); then
        path_width=24
    fi
    ui_section_data "Removal summary"
    ui_table_begin 16 "${path_width}" 10
    ui_table_head "Resource" "Path" "Result"
    ui_table_row "ok" "Service unit" "${UNIT_FILE}" "removed"
    ui_table_row "ok" "Application" "${APP_ROOT}" "removed"
    if [[ "${purge}" == "--purge" ]]; then
        ui_table_row "ok" "Configuration" "${CONFIG_DIR}" "removed"
        ui_table_row "ok" "Data" "${DATA_DIR}" "removed"
        ui_table_row "ok" "Service account" "${SERVICE_USER}" "removed"
    else
        ui_table_row "info" "Configuration" "${CONFIG_DIR}" "preserved"
        ui_table_row "info" "Data" "${DATA_DIR}" "preserved"
        ui_table_row "info" "Service account" "${SERVICE_USER}" "preserved"
    fi
    ui_table_end
    if [[ "${purge}" == "--purge" ]]; then
        ui_ok "Service, application, configuration, and data removed."
        return 0
    fi
    ui_ok "Service and application removed; configuration and data were preserved."
    ui_hint "Delete them later with: sudo ./${UI_SCRIPT_NAME} uninstall --purge"
}

parse_arguments() {
    local argument="" mode=""
    for argument in "$@"; do
        case "${argument}" in
            -h | --help)
                COMMAND="help"
                ;;
            -V | --version)
                COMMAND="version"
                ;;
            --no-color)
                UI_COLOR_MODE="never"
                ;;
            --color)
                UI_COLOR_MODE="always"
                ;;
            --color=*)
                mode="${argument#--color=}"
                case "${mode}" in
                    auto | always | never) UI_COLOR_MODE="${mode}" ;;
                    *) die "Unsupported colour mode '${mode}'." "Use --color=auto, --color=always, or --color=never." ;;
                esac
                ;;
            --plain)
                UI_PLAIN=1
                UI_COLOR_MODE="never"
                UI_NO_ANIMATION=1
                ;;
            --no-animation | --no-spinner)
                UI_NO_ANIMATION=1
                ;;
            --no-banner)
                UI_DISABLE_BANNER=1
                ;;
            -*)
                COMMAND_ARGS+=("${argument}")
                ;;
            *)
                if [[ -z "${COMMAND}" ]]; then
                    COMMAND="${argument}"
                else
                    COMMAND_ARGS+=("${argument}")
                fi
                ;;
        esac
    done
    return 0
}

require_no_extra_arguments() {
    if (( $# > 1 )); then
        die "'$1' does not accept additional arguments." "Run 'sudo ./${UI_SCRIPT_NAME} --help' to list the supported commands."
    fi
    return 0
}

version_report() {
    local revision=""
    revision="$(app_revision)"
    if [[ -n "${revision}" ]]; then
        printf '%s v%s (revision %s)\n' "telegram-server-dash" "${UI_VERSION}" "${revision}"
        return 0
    fi
    printf '%s v%s\n' "telegram-server-dash" "${UI_VERSION}"
    return 0
}

run_command() {
    case "${COMMAND}" in
        install)
            require_no_extra_arguments "${COMMAND}" "${COMMAND_ARGS[@]}"
            acquire_lock
            command_install
            ;;
        update)
            require_no_extra_arguments "${COMMAND}" "${COMMAND_ARGS[@]}"
            acquire_lock
            command_update
            ;;
        configure)
            require_no_extra_arguments "${COMMAND}" "${COMMAND_ARGS[@]}"
            acquire_lock
            command_configure
            ;;
        status)
            require_no_extra_arguments "${COMMAND}" "${COMMAND_ARGS[@]}"
            command_status
            ;;
        logs)
            require_no_extra_arguments "${COMMAND}" "${COMMAND_ARGS[@]}"
            command_logs
            ;;
        uninstall)
            if (( ${#COMMAND_ARGS[@]} > 1 )); then
                die "uninstall accepts only the optional --purge flag." "Run 'sudo ./${UI_SCRIPT_NAME} --help' for details."
            fi
            acquire_lock
            command_uninstall "${COMMAND_ARGS[0]:-}"
            ;;
    esac
}

main() {
    UI_VERSION="$(app_version)"
    parse_arguments "$@"

    case "${COMMAND}" in
        "")
            ui_init
            usage 2
            exit 2
            ;;
        help)
            ui_init
            UI_ACTION="help"
            ui_banner "help"
            usage 1
            exit 0
            ;;
        version)
            ui_init
            version_report
            exit 0
            ;;
        install | update | configure | status | logs | uninstall) ;;
        *)
            ui_init
            UI_ACTION="${COMMAND}"
            ui_banner "${COMMAND}"
            ui_error "Unknown command '${COMMAND}'."
            usage 2
            exit 2
            ;;
    esac

    UI_ACTION="${COMMAND}"
    ui_init
    ui_banner "${COMMAND}"
    preflight "${COMMAND}"
    run_command
    if (( EXIT_STATUS != 0 )); then
        exit "${EXIT_STATUS}"
    fi
    return 0
}

main "$@"
