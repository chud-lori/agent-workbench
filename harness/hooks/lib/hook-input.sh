# Sourced by the Claude Code hooks so each reads its stdin payload the same way.
# read_hook_input sets HOOK_PAYLOAD (exported, raw stdin) and HOOK_SESSION_ID
# (the top-level session_id, or empty when absent or not a plain id).

read_hook_input() {
    HOOK_PAYLOAD="$(cat)"
    export HOOK_PAYLOAD
    HOOK_SESSION_ID=""
    # Escaped quotes inside string values cannot match, so only a real "session_id" key does.
    local pattern='"session_id"[[:space:]]*:[[:space:]]*"([A-Za-z0-9_-]{1,64})"'
    if [[ $HOOK_PAYLOAD =~ $pattern ]]; then
        HOOK_SESSION_ID="${BASH_REMATCH[1]}"
    fi
}
