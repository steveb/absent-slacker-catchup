#!/bin/bash
# Convenience wrapper: summarize the channel from this checkout.
hours=${hours:-24}
channel=${channel:-#openstack-ironic}
output_type=${output_type:-SPEECH_SUMMARY}

# Load the API key (and anything else) that the systemd timer uses, if present.
if [ -f "$HOME/.config/asc/env" ]; then
    set -a
    . "$HOME/.config/asc/env"
    set +a
fi

cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" || exit 1

if [ -x .venv/bin/asc ]; then
    exec .venv/bin/asc fetch --hours "$hours" --output-type "$output_type" \
        "$@" "$channel"
fi

exec python3 -m asc fetch --hours "$hours" --output-type "$output_type" \
    "$@" "$channel"
