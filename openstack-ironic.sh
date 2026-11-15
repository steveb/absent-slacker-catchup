#!/bin/bash
# Convenience wrapper: summarize the channel from this checkout.
hours=${hours:-14}
channel=${channel:-#openstack-ironic}

cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" || exit 1

if [ -x .venv/bin/asc ]; then
    exec .venv/bin/asc fetch --hours "$hours" --output-type SPEECH_SUMMARY \
        --open "$channel"
fi

exec python3 -m asc fetch --hours "$hours" --output-type SPEECH_SUMMARY \
    --open "$channel"
