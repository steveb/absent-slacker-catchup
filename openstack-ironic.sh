#!/bin/bash
# Convenience wrapper: summarize the channel from this checkout.
hours=${hours:-24}
channel=${channel:-#openstack-ironic}
output_type=${output_type:-SPEECH_SUMMARY}

cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" || exit 1

# contrib/asc-run.sh sources ~/.config/claude-code-vertex/env.sh (the rotated
# ENMAAS_KEY) and ~/.config/asc/env, so the timer and this wrapper always use
# the same key.
run=./contrib/asc-run.sh
if [ ! -x "$run" ]; then
    echo "error: $run is missing or not executable" >&2
    exit 1
fi

if [ -x .venv/bin/asc ]; then
    exec "$run" .venv/bin/asc fetch --hours "$hours" --output-type "$output_type" \
        "$@" "$channel"
fi

exec "$run" python3 -m asc fetch --hours "$hours" --output-type "$output_type" \
    "$@" "$channel"
