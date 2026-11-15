# Absent Slacker Catchup (ASC)

A command line tool that summarizes the previous hours of an OpenStack IRC
channel. It reads the archived logs from
<https://meetings.opendev.org/irclogs/>, optionally asks a local model (via
[ollama](https://ollama.com/)) for a summary, and optionally reads that summary
aloud with [Piper](https://github.com/rhasspy/piper).

```
make setup
make run          # writes output/<channel>-<timestamp>/ and opens the page
```

## What it does

- Collects every message in the window (default 14 hours) from the archived
  IRC logs, scanning back one day at a time and stopping at the first day with
  no log file.
- Drops messages from nicknames listed in `irc.ignore_nicks` and nicknames that
  match a regex in `irc.bot_patterns` (`opendevreview`, `*-bot`, `zuul`, …).
- Writes a self-contained HTML page and the plain text transcript of the
  window. With `--output-type SUMMARY` it adds an ollama summary; with
  `SPEECH_SUMMARY` it also synthesizes a WAV file.
- Reports partial failures (a failed log fetch, ollama being down, a missing
  voice model) in the page and via the exit status instead of a traceback:
  the dashboard is still written with whatever was available.

## Requirements

- Python 3.11 or newer.
- `ollama` running locally with a model pulled, for `SUMMARY` and
  `SPEECH_SUMMARY`.
- A Piper voice model for `SPEECH_SUMMARY`. The model is not committed; put it
  in `~/.local/share/asc/models/` (or set `tts.model`/`tts.model_dir`):

  ```bash
  mkdir -p ~/.local/share/asc/models
  curl -LO --output-dir ~/.local/share/asc/models \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx
  curl -LO --output-dir ~/.local/share/asc/models \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx.json
  ```

## Usage

```bash
make setup                      # create .venv and install the package + dev extras
.venv/bin/asc fetch --help
.venv/bin/asc fetch --hours 14 --output-type SPEECH_SUMMARY --open "#openstack-ironic"
.venv/bin/asc status            # show the effective configuration
```

| Option | Meaning |
| --- | --- |
| `channel` | IRC channel to summarize (default `#openstack-ironic`). |
| `--hours N` | Window size in hours (default 14). |
| `--since ISO8601` | Explicit window start, e.g. `2026-11-12T06:00:00Z`. |
| `--output-dir DIR` | Where to create the run directory (default `./output`). |
| `--output-type T` | `CHAT`, `SUMMARY` or `SPEECH_SUMMARY` (default `CHAT`). |
| `--ignore-nicks A [B …]` | Nicknames to drop entirely. |
| `--summary-model M` | ollama model used for the summary. |
| `--tts-model M` | Piper voice model (absolute, or a name searched in the model dir). |
| `--tts-model-dir DIR` | Where to look for a relative `--tts-model`. |
| `--json` / `--no-json` | Also write a machine-readable `summary.json`. |
| `--open` / `--no-open` | Force or suppress the browser launch. By default the browser opens when `DISPLAY`/`WAYLAND_DISPLAY` is set. |
| `--stdout` | Print the HTML instead of writing files. |
| `--dry-run` | Collect data and print a summary only; write nothing. |
| `--config PATH` | TOML config file (defaults to `./config.toml` when it exists). |
| `-v`, `-q` | More/less logging (stderr); `-vv` enables debug. |

`--output-directory` is accepted as an alias of `--output-dir` and
`--open-browser` as an alias of `--open`.

Exit status is `1` when the log fetch, the summariser or the voice model
failed. The report is still written.

### Output

```
output/openstack-ironic-2026-11-15-07-12-01/
  chat.txt            # transcript of the window
  summary.html        # self-contained page (inline CSS, no external assets)
  summary.wav         # only with SPEECH_SUMMARY
  summary.json        # only with --json
output/latest.html    # copy of the most recent page
```

Each page has up to four sections: the audio player, the summary, the model's
reasoning (when the model exposes it), and the chat transcript.

## Configuration

Copy [`config.example.toml`](config.example.toml) to `config.toml` and edit what
you need. Every key is optional; unknown keys are logged and ignored. Command
line flags override the file, which overrides the built-in defaults.

```toml
[general]
channel = "#openstack-ironic"
window_hours = 14
output_dir = "output"
output_type = "SPEECH_SUMMARY"
write_json = true

[irc]
ignore_nicks = ["opendevreview"]
bot_patterns = ["^zuul$", "-bot$"]

[summary]
model = "hf.co/mradermacher/…:Q4_K_M"
num_predict = 1024

[tts]
model = "en_GB-jenny_dioco-medium.onnx"
model_dir = "~/.local/share/asc/models"
```

`asc status` prints the effective settings, including whether the voice model
was found.

## Scheduling

### systemd user timer (recommended)

```bash
make install-timer      # hourly, Persistent=true, 5 minute random delay
systemctl --user list-timers asc.timer
journalctl --user -u asc.service
make uninstall-timer
```

The Makefile renders `contrib/asc.service` and `contrib/asc.timer` into
`~/.config/systemd/user/` with the chosen channel, window, output directory and
command, so no hand editing is needed. Re-run `make install-timer` after
changing a setting:

```bash
make install-timer CHANNEL='#openstack-nova' HOURS=24 SCHEDULE='*-*-* 07:30' OPEN_BROWSER=1
```

The units are per-user, so they only run while you are logged in. To let the
timer run while logged out, enable lingering once:

```bash
loginctl enable-linger "$USER"
```

### cron

```
30 6 * * * cd $HOME/dev/localstack/absent-slacker-catchup && .venv/bin/asc fetch --hours 24 --output-type SPEECH_SUMMARY --no-open >> output/cron.log 2>&1
```

`openstack-ironic.sh` is a small wrapper for interactive use: it changes to the
checkout, prefers `.venv/bin/asc`, and falls back to `python3 -m asc`.

## How it works

- `asc/logs.py` – builds the archive URL for each day (`%23channel/%23channel.YYYY-MM-DD.log.html`),
  parses the `table.irclog` rows, applies the nickname/bot filters and stops at
  the first missing day.
- `asc/http.py` – retries with exponential backoff, honours `Retry-After`,
  throttles consecutive requests and sends an identifying User-Agent.
- `asc/summarize.py` – streams the ollama response and splits out any reasoning
  block the model emits.
- `asc/tts.py` – turns the markdown summary into speech-friendly text and
  drives Piper.
- `asc/render.py` + `asc/templates/` – Jinja2 rendering; the IRC text is
  autoescaped and the CSS is inlined into the page.
- `asc/config.py`, `asc/models.py`, `asc/timeutil.py`, `asc/cli.py` – defaults
  and TOML overrides, the data model, timezone-aware window arithmetic, and the
  argument parsing/orchestration.

## Development

```bash
make test        # pytest, offline
make run-long    # 5 day window, useful on a quiet week
make clean       # remove .venv and caches
```

The fixtures in `tests/fixtures/` are real captured `#openstack-ironic` pages
(2026-11-12) plus a synthetic page that exercises replies, bot nicknames, HTML
injection and malformed rows. HTTP behaviour is covered with `responses`, so
the suite never touches the network.

## Notes and limitations

- The window is computed in UTC; the page renders times in your local
  timezone.
- The archive returns whole days, so the first and last day of a window are
  trimmed client-side to the exact cutoff.
- Bot detection is heuristic (`ignore_nicks` plus `bot_patterns`); add patterns
  if a new automation account appears.
- The log scan stops at the first 404, so a gap in the archive ends the run
  early. `irc.max_days` caps the scan so a quiet channel cannot loop.
- A summary needs ollama and the configured model; `CHAT` output needs neither
  ollama nor a voice model.
- Speech synthesis needs the `.onnx` voice model and its `.onnx.json` metadata
  file in the same directory.
