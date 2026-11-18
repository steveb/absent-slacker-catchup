#!/bin/bash
# Run a command with the summary endpoint's API key loaded.
#
# The systemd timer and the local helpers (openstack-ironic.sh, `make run`)
# both go through this script, so a rotated key is picked up on every run.
#
# The files are sourced rather than read with systemd's EnvironmentFile=,
# because they may use shell syntax such as `export ENMAAS_KEY=...` or
# command substitution. `set -a` is used so that plain `KEY=value` lines are
# exported as well.
#
# Files are sourced in order and later ones win:
#   ~/.config/asc/env                   legacy per-project override
#   ~/.config/claude-code-vertex/env.sh the shared, rotated key
# Missing files are skipped. When at least one is present it is authoritative:
# any ENMAAS_KEY inherited from the calling environment (a stale
# `systemctl --user set-environment` value, say) is dropped first so it cannot
# silently win over the rotated key.
#
# Environment:
#   ASC_KEY_VAR      variable that holds the key (default: ENMAAS_KEY)
#   ASC_ENV_PATH     extra directories to prepend to PATH (colon separated)
#   ASC_ENV_VERBOSE  set to 1 to log the key's source and fingerprint
#
# Usage: contrib/asc-run.sh <command> [args...]

if [ "$#" -eq 0 ]; then
    echo "usage: $(basename -- "$0") <command> [args...]" >&2
    exit 2
fi

: "${HOME:?asc-run: HOME is not set}"

# A systemd unit gets a much smaller PATH than a login shell, and an env file
# often shells out to a per-user tool (gcloud, pass, op, ...) to obtain the
# token. Look there first so the timer resolves the same key as the shell.
PATH="$HOME/.local/bin:$HOME/bin${ASC_ENV_PATH:+:$ASC_ENV_PATH}:$HOME/google-cloud-sdk/bin:$PATH"
export PATH

key_var=${ASC_KEY_VAR:-ENMAAS_KEY}
env_files=(
    "$HOME/.config/asc/env"
    "$HOME/.config/claude-code-vertex/env.sh"
)

sourced=()
for env_file in "${env_files[@]}"; do
    [ -r "$env_file" ] && sourced+=("$env_file")
done

if [ "${#sourced[@]}" -gt 0 ]; then
    unset "$key_var"
fi

key_source=""
for env_file in "${sourced[@]}"; do
    set -a
    # shellcheck disable=SC1090 # the paths are dynamic by design
    if ! . "$env_file"; then
        echo "asc-run: could not source $env_file" >&2
        exit 1
    fi
    set +a
    if [ -n "${!key_var:-}" ]; then
        key_source=$env_file
    fi
done

# Log where the key came from, and which key it is, without printing it. The
# timer runs under systemd, where the journal is the only place to look when
# the endpoint answers 401.
if [ "${ASC_ENV_VERBOSE:-}" = 1 ] || [ -n "${INVOCATION_ID:-}" ]; then
    fingerprint=""
    if [ -n "${!key_var:-}" ] && command -v sha256sum >/dev/null 2>&1; then
        fingerprint=" sha256:$(printf '%s' "${!key_var}" | sha256sum | cut -c1-12)"
    fi
    if [ -n "${!key_var:-}" ]; then
        echo "asc-run: $key_var$fingerprint from ${key_source:-inherited environment}" >&2
    else
        echo "asc-run: $key_var is not set (no key in ${sourced[*]:-any env file})" >&2
    fi
fi

exec "$@"
