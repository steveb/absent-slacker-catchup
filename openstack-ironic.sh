#!/bin/bash

hours=${hours:-14}
channel=${channel:-#openstack-ironic}
venv=${venv:-${VIRTUAL_ENV:-}}

# Run from this checkout so the default --tts-model relative path resolves.
cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" || exit 1

# Prefer a venv (venv=~/venvs/asc) or an `asc` on PATH, then fall back to
# running the package from this checkout.
if [ -n "$venv" ]; then
    asc_cmd=("$venv/bin/asc")
elif command -v asc >/dev/null 2>&1; then
    asc_cmd=(asc)
else
    asc_cmd=(python3 -m asc)
fi

# Summarize the last 14 hours of chat from the #openstack-ironic channel
"${asc_cmd[@]}" fetch --hours "$hours" --output-type SPEECH_SUMMARY --open-browser "$channel"
