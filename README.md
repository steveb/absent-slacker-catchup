# Absent Slacker Catchup (ASC)

A command line tool to summarize the previous hours of an OpenStack IRC channel.

This tool supports any channel which is archived at https://meetings.opendev.org/irclogs/

## Installation

### Development Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd absent-slacker-catchup
```

2. Install in development mode:
```bash
pip install -e .
```

Or install with development dependencies:
```bash
pip install -e .[dev]
```

## Usage

After installation, you can use the `asc` command:

```bash
# Show help
asc --help

# Show version
asc --version

# Summarize the last 14 hours of the IRC channel #openstack-ironic, generate an audio file
# reading the summary, and open a browser with the resulting generated page.
asc fetch --hours 14 --output-type SPEECH_SUMMARY --open-browser "#openstack-ironic"

```

## Running on a schedule (user systemd timer)

The `Makefile` installs `asc.service` and `asc.timer` as per-user systemd units
and starts the timer:

```bash
make install
```

The units are written to `~/.config/systemd/user/` and run `asc fetch` hourly,
writing results to `~/.local/share/asc/`. Set `ASC_CMD` (or `VENV`) if the `asc`
command is not on `PATH`:

```bash
make install VENV=~/venvs/asc
```

Settings are baked into the rendered units, so re-run `make install` after
changing them. For example, to summarize a different channel every morning and
open the report in a browser:

```bash
make install CHANNEL='#openstack-nova' HOURS=24 SCHEDULE='*-*-* 07:30' OPEN_BROWSER=1
```

Other targets: `make status`, `make run` (run once now), `make logs`,
`make reinstall` and `make uninstall`. Run `make help` for the full list.

The units are per-user, so they only run while you are logged in. To let the
timer run while logged out, enable lingering once:

```bash
loginctl enable-linger "$USER"
```