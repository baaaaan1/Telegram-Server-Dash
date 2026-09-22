#!/usr/bin/env bash
#
# deploy/lib/ui.sh - terminal presentation layer for the setup.sh lifecycle CLI.
#
# Stream contract:
#   stderr -> chrome (banner, progress, spinners, diagnostics, errors)
#   stdout -> data   (panels, tables, summaries; safe to pipe or redirect)
#
# Capability contract:
#   Colour, animation and unicode glyphs are only enabled when the target stream
#   supports them. TSD_PLAIN=1, NO_COLOR, TSD_NO_COLOR=1, TSD_NO_ANIMATION=1,
#   TSD_ASCII=1, TSD_NO_BANNER=1 and the matching command line flags always win.
#
# Public API:
#   ui_init, ui_cleanup, ui_banner, ui_rule, ui_section,
#   ui_info, ui_ok, ui_warn, ui_error, ui_note, ui_hint, ui_die,
#   ui_confirm, ui_prompt_text, ui_prompt_secret,
#   ui_plan, ui_stage, ui_stage_ok, ui_stage_fail, ui_run_quiet,
#   ui_panel_begin, ui_panel_row, ui_panel_end,
#   ui_table_begin, ui_table_head, ui_table_row, ui_table_end,
#   ui_on_error (ERR trap), ui_elapsed
#
# Every ui_* function returns 0 unless it reports an explicit failure, so the
# library is safe to call from a script running under `set -Eeuo pipefail`.

UI_VERSION="dev"
UI_ACTION=""
UI_SCRIPT_NAME="setup.sh"
UI_WIDTH=80
UI_UNICODE=0
UI_COLOR=0
UI_ANIMATION=0
UI_CAPTURE=0
UI_BANNER=1
UI_PLAIN=0
UI_COLOR_MODE="auto"
UI_NO_ANIMATION=0
UI_DISABLE_BANNER=0
UI_SPINNER_PID=""
UI_SPINNER_MSG=""
UI_CURSOR_HIDDEN=0
UI_STEP_INDEX=0
UI_STEP_TOTAL=0
UI_STEP_LABEL=""
UI_STEP_START=""
UI_LAST_COMMAND=""
UI_CAPTURE_FILE=""
UI_LOGS_KEEP=0
UI_LOG_DIR=""
UI_EXITING=0
UI_ERROR_REPORTED=0
UI_WRAP_WIDTH=88
UI_PANEL_OPEN=0
UI_PANEL_TITLE=""
UI_PANEL_LABEL_WIDTH=0
UI_PANEL_VALUE_WIDTH=0
UI_PANEL_ROWS=()
UI_TABLE_OPEN=0
UI_TABLE_WIDTHS=()

UI_C_RESET=""
UI_C_DIM=""
UI_C_GREEN=""
UI_C_YELLOW=""
UI_C_BLUE=""
UI_C_CYAN=""
UI_C_BOLD_RED=""
UI_C_BOLD_GREEN=""
UI_C_BOLD_WHITE=""
UI_C_BOLD_BLUE=""

UI_G_CARET=">"
UI_G_SEP="-"
UI_G_ARROW="->"
UI_G_ELLIPSIS="..."
UI_G_RULE="-"
UI_G_BOX_TL="+"
UI_G_BOX_TR="+"
UI_G_BOX_BL="+"
UI_G_BOX_BR="+"
UI_G_BOX_H="-"
UI_G_BOX_V="|"

# ---------------------------------------------------------------------------
# capability detection
# ---------------------------------------------------------------------------

ui_init() {
    ui__detect_width
    ui__detect_unicode
    ui__detect_color
    ui__load_glyphs
    ui__load_palette
    ui__detect_animation
    if [[ "${UI_DISABLE_BANNER}" -eq 1 ]]; then
        UI_BANNER=0
    fi
    return 0
}

ui__detect_width() {
    local width=""
    if [[ -t 1 || -t 2 ]] && command -v tput >/dev/null 2>&1; then
        width="$(tput cols 2>/dev/null || true)"
    fi
    if [[ ! "${width}" =~ ^[0-9]+$ ]]; then
        width="${COLUMNS:-80}"
    fi
    if [[ ! "${width}" =~ ^[0-9]+$ ]]; then
        width=80
    fi
    if (( width < 40 )); then
        width=40
    fi
    if (( width > 120 )); then
        width=120
    fi
    UI_WIDTH="${width}"
    UI_WRAP_WIDTH=$(( width - 8 ))
    return 0
}

ui__detect_unicode() {
    UI_UNICODE=0
    if [[ "${UI_PLAIN}" -eq 1 || "${TSD_ASCII:-0}" == "1" ]]; then
        return 0
    fi
    local hint="${LC_ALL:-}${LC_CTYPE:-}${LANG:-}"
    if [[ "${hint,,}" == *utf* ]]; then
        UI_UNICODE=1
    fi
    return 0
}

ui__detect_color() {
    UI_COLOR=0
    if [[ "${UI_PLAIN}" -eq 1 ]]; then
        return 0
    fi
    case "${UI_COLOR_MODE}" in
        never)
            return 0
            ;;
        always)
            UI_COLOR=1
            return 0
            ;;
    esac
    if [[ -n "${NO_COLOR:-}" || "${TSD_NO_COLOR:-0}" == "1" ]]; then
        return 0
    fi
    if [[ -n "${CLICOLOR_FORCE:-}" && "${CLICOLOR_FORCE}" != "0" ]]; then
        UI_COLOR=1
        return 0
    fi
    if [[ "${TERM:-dumb}" == "dumb" || "${TERM:-}" == "" ]]; then
        return 0
    fi
    if [[ -t 2 ]]; then
        UI_COLOR=1
    fi
    return 0
}

ui__detect_animation() {
    UI_ANIMATION=0
    UI_CAPTURE=0
    if [[ "${UI_PLAIN}" -eq 1 || "${UI_NO_ANIMATION}" -eq 1 ]]; then
        return 0
    fi
    if [[ "${TSD_NO_ANIMATION:-0}" == "1" ]]; then
        return 0
    fi
    if [[ "${TERM:-dumb}" == "dumb" || "${TERM:-}" == "" ]]; then
        return 0
    fi
    if [[ ! -t 2 ]]; then
        return 0
    fi
    UI_ANIMATION=1
    UI_CAPTURE=1
    return 0
}

ui__load_palette() {
    if [[ "${UI_COLOR}" -ne 1 ]]; then
        return 0
    fi
    UI_C_RESET=$'\033[0m'
    UI_C_DIM=$'\033[2m'
    UI_C_GREEN=$'\033[32m'
    UI_C_YELLOW=$'\033[33m'
    UI_C_BLUE=$'\033[34m'
    UI_C_CYAN=$'\033[36m'
    UI_C_BOLD_RED=$'\033[1;31m'
    UI_C_BOLD_GREEN=$'\033[1;32m'
    UI_C_BOLD_WHITE=$'\033[1;97m'
    UI_C_BOLD_BLUE=$'\033[1;34m'
    return 0
}

ui__load_glyphs() {
    if [[ "${UI_UNICODE}" -ne 1 ]]; then
        return 0
    fi
    UI_G_CARET="›"
    UI_G_SEP="·"
    UI_G_ARROW="↳"
    UI_G_ELLIPSIS="…"
    UI_G_RULE="─"
    UI_G_BOX_TL="╭"
    UI_G_BOX_TR="╮"
    UI_G_BOX_BL="╰"
    UI_G_BOX_BR="╯"
    UI_G_BOX_H="─"
    UI_G_BOX_V="│"
    return 0
}

# ---------------------------------------------------------------------------
# low level helpers
# ---------------------------------------------------------------------------

ui__now() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        printf '%s' "${EPOCHREALTIME//,/.}"
    else
        date +%s
    fi
    return 0
}

ui_elapsed() {
    local start="$1" end="$2"
    if [[ -z "${start}" || -z "${end}" ]]; then
        printf '0.0s'
        return 0
    fi
    awk -v first="${start}" -v second="${end}" 'BEGIN {
        seconds = second - first
        if (seconds < 0) { seconds = 0 }
        if (seconds < 60) { printf "%.1fs", seconds; exit }
        minutes = int(seconds / 60)
        printf "%dm %02ds", minutes, int(seconds - (minutes * 60))
    }'
    return 0
}

ui__repeat() {
    local unit="$1" count="$2" result="" index=0
    if [[ ! "${count}" =~ ^[0-9]+$ ]]; then
        return 0
    fi
    for ((index = 0; index < count; index++)); do
        result+="${unit}"
    done
    printf '%s' "${result}"
    return 0
}

ui__truncate_middle() {
    local text="$1" limit="$2"
    if (( ${#text} <= limit )); then
        printf '%s' "${text}"
        return 0
    fi
    if (( limit < 6 )); then
        printf '%s' "${text:0:limit}"
        return 0
    fi
    local keep=$(( limit - ${#UI_G_ELLIPSIS} ))
    local head=$(( keep / 2 ))
    local tail=$(( keep - head ))
    printf '%s%s%s' "${text:0:head}" "${UI_G_ELLIPSIS}" "${text: -tail}"
    return 0
}

ui__fit() {
    local text="$1" width="$2"
    if [[ ! "${width}" =~ ^[0-9]+$ ]]; then
        printf '%s' "${text}"
        return 0
    fi
    if (( ${#text} > width )); then
        text="$(ui__truncate_middle "${text}" "${width}")"
    fi
    printf '%-*s' "${width}" "${text}"
    return 0
}

ui__mark() {
    local kind="$1" text="mark" color="" width=1
    if [[ "${UI_UNICODE}" -eq 1 ]]; then
        case "${kind}" in
            ok) text="✔"; color="${UI_C_GREEN}" ;;
            fail) text="✖"; color="${UI_C_BOLD_RED}" ;;
            warn) text="▲"; color="${UI_C_YELLOW}" ;;
            info) text="●"; color="${UI_C_BLUE}" ;;
            step) text="▸"; color="${UI_C_BOLD_BLUE}" ;;
            arrow) text="${UI_G_ARROW}"; color="${UI_C_DIM}" ;;
        esac
    else
        width=4
        case "${kind}" in
            ok) text="ok"; color="${UI_C_GREEN}" ;;
            fail) text="fail"; color="${UI_C_BOLD_RED}" ;;
            warn) text="warn"; color="${UI_C_YELLOW}" ;;
            info) text="info"; color="${UI_C_BLUE}" ;;
            step) text="step"; color="${UI_C_BOLD_BLUE}" ;;
            arrow) text="${UI_G_ARROW}"; color="${UI_C_DIM}" ;;
        esac
    fi
    printf '%s%-*s%s' "${color}" "${width}" "${text}" "${UI_C_RESET}"
    return 0
}

ui__style_color() {
    case "${1:-}" in
        ok) printf '%s' "${UI_C_BOLD_GREEN}" ;;
        warn) printf '%s' "${UI_C_YELLOW}" ;;
        error) printf '%s' "${UI_C_BOLD_RED}" ;;
        info) printf '%s' "${UI_C_BLUE}" ;;
        accent) printf '%s' "${UI_C_CYAN}" ;;
        muted) printf '%s' "${UI_C_DIM}" ;;
        *) printf '%s' "" ;;
    esac
    return 0
}

ui__cursor_hide() {
    if [[ "${UI_ANIMATION}" -eq 1 && "${UI_CURSOR_HIDDEN}" -eq 0 ]]; then
        printf '\033[?25l' >&2
        UI_CURSOR_HIDDEN=1
    fi
    return 0
}

ui__cursor_show() {
    if [[ "${UI_CURSOR_HIDDEN}" -eq 1 ]]; then
        printf '\033[?25h' >&2
        UI_CURSOR_HIDDEN=0
    fi
    return 0
}

# ---------------------------------------------------------------------------
# message chrome (stderr)
# ---------------------------------------------------------------------------

ui__say() {
    local kind="$1" message="$2"
    printf '  %s  %s\n' "$(ui__mark "${kind}")" "${message}" >&2
    return 0
}

ui_info() {
    ui__say info "$1"
    return 0
}

ui_ok() {
    ui__say ok "$1"
    return 0
}

ui_warn() {
    ui__say warn "$1"
    return 0
}

ui_error() {
    ui__say fail "$1"
    return 0
}

ui_note() {
    printf '  %s  %s%s%s\n' "$(ui__mark arrow)" "${UI_C_DIM}" "$1" "${UI_C_RESET}" >&2
    return 0
}

ui_hint() {
    printf '     %s%s%s\n' "${UI_C_DIM}" "$1" "${UI_C_RESET}" >&2
    return 0
}

ui_die() {
    local message="$1" hint="${2:-}"
    UI_EXITING=1
    ui_spinner_stop
    if [[ -n "${UI_STEP_START}" ]]; then
        ui_stage_fail
    fi
    printf '\n  %s  %s%s%s\n' "$(ui__mark fail)" "${UI_C_BOLD_RED}" "${message}" "${UI_C_RESET}" >&2
    if [[ -n "${hint}" ]]; then
        printf '     %s%s%s\n' "${UI_C_DIM}" "${hint}" "${UI_C_RESET}" >&2
    fi
    printf '\n' >&2
    exit 1
}

ui_rule() {
    local label="${1:-}" fill=0 line=""
    if [[ -n "${label}" ]]; then
        fill=$(( UI_WRAP_WIDTH - ${#label} - 1 ))
        if (( fill > 0 )); then
            line=" $(ui__repeat "${UI_G_RULE}" "${fill}")"
        fi
        printf '  %s%s%s%s\n' "${label}" "${UI_C_DIM}" "${line}" "${UI_C_RESET}" >&2
        return 0
    fi
    printf '  %s%s%s\n' "${UI_C_DIM}" "$(ui__repeat "${UI_G_RULE}" "${UI_WRAP_WIDTH}")" "${UI_C_RESET}" >&2
    return 0
}

ui_section() {
    ui__section_to 2 "$1"
}

ui_section_data() {
    ui__section_to 1 "$1"
}

ui__section_to() {
    local fd="$1" title="$2" fill=0 line=""
    fill=$(( UI_WRAP_WIDTH - ${#title} - 3 ))
    if (( fill < 1 )); then
        fill=1
    fi
    line=" $(ui__repeat "${UI_G_RULE}" "${fill}")"
    printf '\n  %s %s%s%s%s%s%s\n' \
        "$(ui__mark arrow)" \
        "${UI_C_BOLD_WHITE}" "${title}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${line}" "${UI_C_RESET}" >&"${fd}"
    return 0
}

# ---------------------------------------------------------------------------
# banner
# ---------------------------------------------------------------------------

ui__banner_art() {
    if [[ "${UI_UNICODE}" -eq 1 ]]; then
        cat <<'ART'
 ████████╗███████╗██████╗
 ╚══██╔══╝██╔════╝██╔══██╗
    ██║   ███████╗██║  ██║
    ██║   ╚════██║██║  ██║
    ██║   ███████║██████╔╝
    ╚═╝   ╚══════╝╚═════╝
ART
        return 0
    fi
    cat <<'ART'
  _____ _____ ____
 |_   _/ ____|  _ \
   | || (___ | |_) |
   | | \___ \|  _ <
   | | ____) | |_) |
   |_||_____/|____/
ART
    return 0
}

ui_banner() {
    local action="${1:-${UI_ACTION}}"
    if [[ "${UI_BANNER}" -ne 1 ]]; then
        return 0
    fi

    local host=""
    host="$(hostname 2>/dev/null || true)"
    if [[ -z "${host}" ]]; then
        host="$(uname -n 2>/dev/null || true)"
    fi
    if [[ -z "${host}" ]]; then
        host="unknown-host"
    fi

    local stamp=""
    stamp="$(date -u '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || true)"

    printf '\n' >&2
    if (( UI_WIDTH >= 60 )); then
        printf '%s' "${UI_C_CYAN}" >&2
        ui__banner_art >&2
        printf '%s\n' "${UI_C_RESET}" >&2
        printf '  %sTELEGRAM SERVER DASH%s  %s%s v%s%s\n' \
            "${UI_C_BOLD_WHITE}" "${UI_C_RESET}" \
            "${UI_C_DIM}" "${UI_G_SEP}" "${UI_VERSION}" "${UI_C_RESET}" >&2
        printf '  %sLifecycle toolkit for the Telegram Server Dash systemd service%s\n' \
            "${UI_C_DIM}" "${UI_C_RESET}" >&2
    else
        printf '  %sTELEGRAM SERVER DASH%s %s%s v%s%s\n' \
            "${UI_C_BOLD_WHITE}" "${UI_C_RESET}" \
            "${UI_C_DIM}" "${UI_G_SEP}" "${UI_VERSION}" "${UI_C_RESET}" >&2
    fi

    ui_rule

    if ((${#host} > 24)); then
        host="$(ui__truncate_middle "${host}" 24)"
    fi
    printf '  %shost%s %s  %s%s%s  %saction%s %s%s%s  %s%s%s  %s%s%s\n' \
        "${UI_C_DIM}" "${UI_C_RESET}" "${host}" \
        "${UI_C_DIM}" "${UI_G_SEP}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_C_RESET}" "${UI_C_BOLD_WHITE}" "${action:-unknown}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_G_SEP}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${stamp}" "${UI_C_RESET}" >&2
    printf '\n' >&2
    return 0
}

# ---------------------------------------------------------------------------
# progress indicators
# ---------------------------------------------------------------------------

ui__bar() {
    local index="$1" total="$2" width=24 filled=0 position=0 result=""
    if (( total <= 0 )); then
        total=1
    fi
    filled=$(( index * width / total ))
    if (( filled > width )); then
        filled=width
    fi
    for ((position = 0; position < width; position++)); do
        if (( position < filled )); then
            if [[ "${UI_UNICODE}" -eq 1 ]]; then
                result+="█"
            else
                result+="#"
            fi
        else
            if [[ "${UI_UNICODE}" -eq 1 ]]; then
                result+="░"
            else
                result+="-"
            fi
        fi
    done
    printf '%s' "${result}"
    return 0
}

ui_plan() {
    UI_STEP_TOTAL="$1"
    UI_STEP_INDEX=0
    UI_STEP_LABEL=""
    UI_STEP_START=""
    UI_LAST_COMMAND=""
    UI_ERROR_REPORTED=0
    return 0
}

ui_stage() {
    UI_STEP_INDEX=$(( UI_STEP_INDEX + 1 ))
    UI_STEP_LABEL="$1"
    UI_STEP_START="$(ui__now)"
    UI_LAST_COMMAND=""
    UI_ERROR_REPORTED=0
    ui_spinner_stop
    local counter=""
    counter="$(printf '%2d/%s' "${UI_STEP_INDEX}" "${UI_STEP_TOTAL}")"
    printf '%s[%s]%s %s%s%s  %s%s%s\n' \
        "${UI_C_CYAN}" "$(ui__bar "${UI_STEP_INDEX}" "${UI_STEP_TOTAL}")" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${counter}" "${UI_C_RESET}" \
        "${UI_C_BOLD_WHITE}" "${UI_STEP_LABEL}" "${UI_C_RESET}" >&2
    return 0
}

ui_stage_ok() {
    ui_spinner_stop
    local elapsed=""
    elapsed="$(ui_elapsed "${UI_STEP_START}" "$(ui__now)")"
    printf '  %s  %sdone in %s%s\n' "$(ui__mark ok)" "${UI_C_DIM}" "${elapsed}" "${UI_C_RESET}" >&2
    UI_STEP_START=""
    return 0
}

ui_stage_fail() {
    ui_spinner_stop
    local elapsed=""
    elapsed="$(ui_elapsed "${UI_STEP_START}" "$(ui__now)")"
    printf '  %s  %sfailed after %s%s\n' "$(ui__mark fail)" "${UI_C_BOLD_RED}" "${elapsed}" "${UI_C_RESET}" >&2
    UI_STEP_START=""
    return 0
}

ui_spinner_start() {
    UI_SPINNER_MSG="$1"
    if [[ "${UI_ANIMATION}" -ne 1 ]]; then
        return 0
    fi
    if [[ -n "${UI_SPINNER_PID}" ]]; then
        return 0
    fi
    ui__cursor_hide
    (
        frames=('|' '/' '-' $'\\')
        if [[ "${UI_UNICODE}" -eq 1 ]]; then
            frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
        fi
        index=0
        count=${#frames[@]}
        while :; do
            printf '\r\033[K  %s%s%s %s%s%s%s' \
                "${UI_C_CYAN}" "${frames[index]}" "${UI_C_RESET}" \
                "${UI_SPINNER_MSG}" "${UI_C_DIM}" "${UI_G_ELLIPSIS}" "${UI_C_RESET}" >&2
            index=$(( (index + 1) % count ))
            sleep 0.15
        done
    ) &
    UI_SPINNER_PID=$!
    return 0
}

ui_spinner_stop() {
    if [[ -n "${UI_SPINNER_PID}" ]]; then
        kill "${UI_SPINNER_PID}" 2>/dev/null || true
        wait "${UI_SPINNER_PID}" 2>/dev/null || true
        UI_SPINNER_PID=""
        printf '\r\033[K' >&2
    fi
    ui__cursor_show
    return 0
}

ui__capture_file() {
    local label="$1" name=""
    UI_CAPTURE_FILE=""
    if [[ -z "${UI_LOG_DIR}" ]]; then
        if ! UI_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/telegram-server-dash-setup.XXXXXX" 2>/dev/null)"; then
            UI_LOG_DIR=""
            return 1
        fi
    fi
    name="$(printf '%s' "${label}" | tr -c 'A-Za-z0-9._-' '_')"
    UI_CAPTURE_FILE="${UI_LOG_DIR}/${name}.log"
    return 0
}

ui__log_tail() {
    local log_file="$1" lines="${2:-12}"
    if [[ ! -s "${log_file}" ]]; then
        return 0
    fi
    printf '  %s  %s%s%s\n' "$(ui__mark arrow)" "${UI_C_DIM}" "last ${lines} lines of output:" "${UI_C_RESET}" >&2
    tail -n "${lines}" "${log_file}" 2>/dev/null | sed 's/^/     | /' >&2 || true
    printf '  %s  %s%sfull log: %s%s\n' "$(ui__mark arrow)" "${UI_C_DIM}" "" "${log_file}" "${UI_C_RESET}" >&2
    return 0
}

ui_run_quiet() {
    local message="$1"
    shift
    local status=0
    UI_LAST_COMMAND="$*"
    if [[ "${UI_CAPTURE}" -eq 1 ]] && ui__capture_file "${message}"; then
        ui_spinner_start "${message}"
        "$@" >"${UI_CAPTURE_FILE}" 2>&1 || status=$?
        ui_spinner_stop
        if (( status != 0 )); then
            UI_LOGS_KEEP=1
            ui__log_tail "${UI_CAPTURE_FILE}"
        fi
        return "${status}"
    fi
    ui_note "${message}"
    "$@" || status=$?
    return "${status}"
}

# ---------------------------------------------------------------------------
# panels (stdout)
# ---------------------------------------------------------------------------

ui_panel_begin() {
    UI_PANEL_TITLE="$1"
    UI_PANEL_ROWS=()
    UI_PANEL_LABEL_WIDTH=0
    UI_PANEL_VALUE_WIDTH=0
    UI_PANEL_OPEN=1
    return 0
}

ui_panel_row() {
    local label="$1" value="$2" style="${3:-plain}"
    if [[ "${UI_PANEL_OPEN}" -ne 1 ]]; then
        return 0
    fi
    UI_PANEL_ROWS+=("${label}"$'\t'"${value}"$'\t'"${style}")
    if (( ${#label} > UI_PANEL_LABEL_WIDTH )); then
        UI_PANEL_LABEL_WIDTH=${#label}
    fi
    if (( ${#value} > UI_PANEL_VALUE_WIDTH )); then
        UI_PANEL_VALUE_WIDTH=${#value}
    fi
    return 0
}

ui_panel_end() {
    if [[ "${UI_PANEL_OPEN}" -ne 1 ]]; then
        return 0
    fi
    UI_PANEL_OPEN=0

    local inner=$(( UI_PANEL_LABEL_WIDTH + 2 + UI_PANEL_VALUE_WIDTH ))
    local limit=$(( UI_WIDTH - 8 ))
    if (( inner > limit )); then
        inner="${limit}"
    fi
    if (( inner < 16 )); then
        inner=16
    fi
    local label_width="${UI_PANEL_LABEL_WIDTH}"
    if (( label_width > inner - 10 )); then
        label_width=$(( inner - 10 ))
    fi
    if (( label_width < 1 )); then
        label_width=1
    fi
    local value_width=$(( inner - label_width - 2 ))
    local box_width=$(( inner + 4 ))

    local title_fill=$(( inner - ${#UI_PANEL_TITLE} - 1 ))
    if (( title_fill < 1 )); then
        title_fill=1
    fi
    printf '  %s%s%s%s %s%s%s %s%s%s\n' \
        "${UI_C_DIM}" "${UI_G_BOX_TL}" "${UI_G_BOX_H}" "${UI_C_RESET}" \
        "${UI_C_BOLD_BLUE}" "${UI_PANEL_TITLE}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "$(ui__repeat "${UI_G_BOX_H}" "${title_fill}")${UI_G_BOX_TR}" "${UI_C_RESET}"

    local row="" label="" value="" style="" color=""
    for row in "${UI_PANEL_ROWS[@]}"; do
        label="${row%%$'\t'*}"
        value="${row#*$'\t'}"
        style="${value#*$'\t'}"
        value="${value%%$'\t'*}"
        color="$(ui__style_color "${style}")"
        printf '  %s%s%s %s%s%s  %s%s%s %s%s%s\n' \
            "${UI_C_DIM}" "${UI_G_BOX_V}" "${UI_C_RESET}" \
            "${UI_C_DIM}" "$(ui__fit "${label}" "${label_width}")" "${UI_C_RESET}" \
            "${color}" "$(ui__fit "${value}" "${value_width}")" "${UI_C_RESET}" \
            "${UI_C_DIM}" "${UI_G_BOX_V}" "${UI_C_RESET}"
    done

    printf '  %s%s%s%s\n' \
        "${UI_C_DIM}" "${UI_G_BOX_BL}" \
        "$(ui__repeat "${UI_G_BOX_H}" "$(( box_width - 2 ))")${UI_G_BOX_BR}" "${UI_C_RESET}"
    UI_PANEL_ROWS=()
    return 0
}

# ---------------------------------------------------------------------------
# tables (stdout)
# ---------------------------------------------------------------------------

ui_table_begin() {
    UI_TABLE_WIDTHS=("$@")
    UI_TABLE_OPEN=1
    return 0
}

ui_table_render() {
    local color="$1"
    shift
    local cells=("$@")
    local columns=${#UI_TABLE_WIDTHS[@]}
    local index=0 cell="" width=0 line="" last=""
    if [[ "${UI_TABLE_OPEN}" -ne 1 || "${columns}" -eq 0 ]]; then
        return 0
    fi
    for ((index = 0; index < columns; index++)); do
        cell="${cells[index]:-}"
        width="${UI_TABLE_WIDTHS[index]}"
        if (( index == columns - 1 )); then
            last="$(ui__fit "${cell}" "${width}")"
        else
            line+="$(ui__fit "${cell}" "${width}")  "
        fi
    done
    printf '  %s%s%s%s\n' "${line}" "${color}" "${last}" "${UI_C_RESET}"
    return 0
}

ui_table_head() {
    local total=0 index=0
    for ((index = 0; index < ${#UI_TABLE_WIDTHS[@]}; index++)); do
        total=$(( total + UI_TABLE_WIDTHS[index] ))
    done
    total=$(( total + (2 * (${#UI_TABLE_WIDTHS[@]} - 1)) ))
    ui_table_render "${UI_C_DIM}" "$@"
    printf '  %s%s%s\n' "${UI_C_DIM}" "$(ui__repeat "${UI_G_RULE}" "${total}")" "${UI_C_RESET}"
    return 0
}

ui_table_row() {
    local style="$1"
    shift
    ui_table_render "$(ui__style_color "${style}")" "$@"
}

ui_table_end() {
    UI_TABLE_OPEN=0
    UI_TABLE_WIDTHS=()
    return 0
}

# ---------------------------------------------------------------------------
# prompts (target the controlling terminal)
# ---------------------------------------------------------------------------

ui_confirm() {
    local prompt="$1" response=""
    if [[ ! -r /dev/tty ]]; then
        return 1
    fi
    printf '  %s  %s %s[y/N]%s ' \
        "$(ui__mark info)" "${prompt}" "${UI_C_DIM}" "${UI_C_RESET}" >/dev/tty
    IFS= read -r response </dev/tty || return 1
    [[ "${response}" =~ ^[Yy]$ ]]
}

ui__prompt_label() {
    local label="$1" hint="${2:-}"
    printf '\n  %s  %s%s%s\n' \
        "$(ui__mark step)" "${UI_C_BOLD_WHITE}" "${label}" "${UI_C_RESET}" >/dev/tty
    if [[ -n "${hint}" ]]; then
        printf '     %s%s%s\n' "${UI_C_DIM}" "${hint}" "${UI_C_RESET}" >/dev/tty
    fi
    printf '  %s ' "${UI_G_CARET}" >/dev/tty
    return 0
}

ui_prompt_text() {
    local label="$1" hint="${2:-}" value=""
    ui__prompt_label "${label}" "${hint}"
    IFS= read -r value </dev/tty || return 1
    printf '%s' "${value}"
    return 0
}

ui_prompt_secret() {
    local label="$1" hint="${2:-}" value=""
    ui__prompt_label "${label}" "${hint}"
    IFS= read -r -s value </dev/tty || return 1
    printf '\n' >/dev/tty
    printf '%s' "${value}"
    return 0
}

ui_prompt_typed() {
    local prompt="$1" expected="$2" response=""
    if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
        return 1
    fi
    printf '\n  %s  %s%s%s\n' "$(ui__mark warn)" "${UI_C_BOLD_RED}" "${prompt}" "${UI_C_RESET}" >/dev/tty
    printf '  %s ' "${UI_G_CARET}" >/dev/tty
    IFS= read -r response </dev/tty || return 1
    [[ "${response}" == "${expected}" ]]
}

# ---------------------------------------------------------------------------
# failure reporting
# ---------------------------------------------------------------------------

ui_on_error() {
    local status="$1" line="${2:-?}" command="${3:-}"
    ui_spinner_stop
    if [[ "${UI_EXITING}" -eq 1 || "${UI_ERROR_REPORTED}" -eq 1 ]]; then
        return 0
    fi
    UI_ERROR_REPORTED=1
    if [[ -n "${UI_STEP_START}" ]]; then
        ui_stage_fail
    fi
    local step="none"
    if [[ -n "${UI_STEP_LABEL}" ]]; then
        step="${UI_STEP_INDEX}/${UI_STEP_TOTAL}  ${UI_STEP_LABEL}"
    fi
    local failed_command="${UI_LAST_COMMAND:-${command}}"
    local head="FAILED"
    local box_width=$(( UI_WIDTH - 6 ))
    local fill=$(( box_width - ${#head} - 5 ))
    if (( fill < 1 )); then
        fill=1
    fi
    printf '\n  %s%s%s%s %s%s%s %s%s%s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_TL}" "${UI_G_BOX_H}" "${UI_C_RESET}" \
        "${UI_C_BOLD_RED}" "${head}" "${UI_C_RESET}" \
        "${UI_C_BOLD_RED}" "$(ui__repeat "${UI_G_BOX_H}" "${fill}")${UI_G_BOX_TR}" "${UI_C_RESET}" >&2
    printf '  %s%s%s %sstep%s      %s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_V}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_C_RESET}" "${step}" >&2
    printf '  %s%s%s %scommand%s   %s%s%s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_V}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_C_RESET}" \
        "${UI_C_YELLOW}" "$(ui__truncate_middle "${failed_command}" "$(( box_width - 14 ))")" "${UI_C_RESET}" >&2
    printf '  %s%s%s %sexit%s      %s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_V}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_C_RESET}" "${status}" >&2
    printf '  %s%s%s %slocation%s  %s:%s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_V}" "${UI_C_RESET}" \
        "${UI_C_DIM}" "${UI_C_RESET}" "${UI_SCRIPT_NAME}" "${line}" >&2
    printf '  %s%s%s%s\n' \
        "${UI_C_BOLD_RED}" "${UI_G_BOX_BL}" \
        "$(ui__repeat "${UI_G_BOX_H}" "$(( box_width - 2 ))")${UI_G_BOX_BR}" "${UI_C_RESET}" >&2
    printf '  %sFix the cause above, then re-run:%s sudo ./%s %s\n' \
        "${UI_C_DIM}" "${UI_C_RESET}" "${UI_SCRIPT_NAME}" "${UI_ACTION:-install}" >&2
    if [[ "${UI_LOGS_KEEP}" -eq 1 && -n "${UI_LOG_DIR}" ]]; then
        printf '  %sRetained logs: %s%s\n' "${UI_C_DIM}" "${UI_LOG_DIR}" "${UI_C_RESET}" >&2
    fi
    printf '\n' >&2
    return 0
}

ui_cleanup() {
    ui_spinner_stop
    if [[ -n "${UI_LOG_DIR}" && "${UI_LOGS_KEEP}" -eq 0 ]]; then
        rm -rf -- "${UI_LOG_DIR}" 2>/dev/null || true
    fi
    UI_LOG_DIR=""
    return 0
}
