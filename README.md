# Absent Slacker Catchup (ASC)

A command line tool for absent slacker catchup.

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

# Say hello
asc hello
asc hello "Your Name"

# Show status
asc status

# Enable verbose output
asc -v status
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black asc/
```

### Type Checking

```bash
mypy asc/
```

## Project Structure

```
absent-slacker-catchup/
├── asc/                    # Main package
│   ├── __init__.py        # Package initialization
│   ├── __main__.py        # Module entry point
│   └── cli.py             # Command line interface
├── tests/                 # Test files
├── pyproject.toml         # Project configuration
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
└── README.md             # This file
``` 