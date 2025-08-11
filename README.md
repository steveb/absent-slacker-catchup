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