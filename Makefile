# Install the ASC CLI as a per-user systemd timer.
#
#   make install      # render the units, enable and start the timer
#   make status       # show timer state and next/last run
#   make run          # trigger a summary run right now
#   make logs         # follow the service journal
#   make uninstall    # stop, disable and remove the units
#
# Every setting below can be overridden on the command line, e.g.
#
#   make install CHANNEL='#openstack-nova' HOURS=24 SCHEDULE='*-*-* 07:30'
#
# Note: re-run `make install` after changing any setting, since the values are
# baked into the rendered unit files.

UNIT_NAME   ?= asc
SYSTEMD_DIR ?= $(HOME)/.config/systemd/user

# How to invoke the CLI from the service. Defaults to the `asc` console script
# if it is on PATH, otherwise to `python -m asc` for PYTHON (set VENV or
# ASC_CMD to point at the interpreter/venv that has the package installed).
PYTHON  ?= python3
PYTHON  := $(shell command -v $(PYTHON) 2>/dev/null || echo $(PYTHON))
VENV    ?=
ASC_CMD ?= $(if $(VENV),$(VENV)/bin/asc,$(shell command -v asc 2>/dev/null || echo "$(PYTHON) -m asc"))

# Directory the service runs in. Must contain the Piper voice model used by
# --output-type SPEECH_SUMMARY (unless you pass an absolute --tts-model).
WORKDIR ?= $(CURDIR)

# `asc fetch` arguments.
CHANNEL     ?= \#openstack-ironic
HOURS       ?= 14
OUTPUT_TYPE ?= SPEECH_SUMMARY
OUTPUT_DIR  ?= $(HOME)/.local/share/asc
OPEN_BROWSER ?= 0

# Timer settings.
SCHEDULE     ?= hourly
PERSISTENT   ?= true
RANDOM_DELAY ?= 5m

BROWSER_ARGS := $(if $(filter-out 0,$(OPEN_BROWSER)),--open-browser,)

# `make FOO=~/bar` does not get shell tilde expansion, so expand a leading ~
# ourselves. Use `override` because these may be set on the command line.
expand_tilde = $(if $(filter ~,$(1)),$(HOME),$(patsubst ~/%,$(HOME)/%,$(1)))
override ASC_CMD     := $(call expand_tilde,$(ASC_CMD))
override WORKDIR     := $(call expand_tilde,$(WORKDIR))
override OUTPUT_DIR  := $(call expand_tilde,$(OUTPUT_DIR))
override SYSTEMD_DIR := $(call expand_tilde,$(SYSTEMD_DIR))

ASC_EXE := $(firstword $(ASC_CMD))

SERVICE_TEMPLATE := systemd/asc.service
TIMER_TEMPLATE   := systemd/asc.timer
SERVICE_UNIT     := $(SYSTEMD_DIR)/$(UNIT_NAME).service
TIMER_UNIT       := $(SYSTEMD_DIR)/$(UNIT_NAME).timer

SYSTEMCTL ?= systemctl --user

.DEFAULT_GOAL := help
.PHONY: help install uninstall reinstall status run logs enable disable

help:
	@echo "Targets:"
	@echo "  install    Render the units, then enable and start $(UNIT_NAME).timer"
	@echo "  uninstall  Stop, disable and remove $(UNIT_NAME).service/.timer"
	@echo "  reinstall  uninstall + install (use after changing settings)"
	@echo "  status     Show the state of the timer"
	@echo "  run        Run $(UNIT_NAME).service once, now"
	@echo "  logs       Follow the journal for $(UNIT_NAME).service"
	@echo "  enable     Enable and start the timer without re-rendering units"
	@echo "  disable    Stop and disable the timer, leaving units in place"
	@echo ""
	@echo "Settings (override on the command line, e.g. 'make install HOURS=24'):"
	@echo "  ASC_CMD=$(ASC_CMD)"
	@echo "  WORKDIR=$(WORKDIR)"
	@echo "  CHANNEL=$(CHANNEL)  HOURS=$(HOURS)  OUTPUT_TYPE=$(OUTPUT_TYPE)"
	@echo "  OUTPUT_DIR=$(OUTPUT_DIR)  OPEN_BROWSER=$(OPEN_BROWSER)"
	@echo "  SCHEDULE=$(SCHEDULE)  PERSISTENT=$(PERSISTENT)  RANDOM_DELAY=$(RANDOM_DELAY)"
	@echo "  SYSTEMD_DIR=$(SYSTEMD_DIR)"

# Render a unit template into SYSTEMD_DIR, substituting @PLACEHOLDERS@.
# Writes to a temporary file first so systemd never sees a partial unit.
define render_unit
	@mkdir -p "$(SYSTEMD_DIR)"
	@sed -e 's|@UNIT_NAME@|$(UNIT_NAME)|g' \
	     -e 's|@ASC_CMD@|$(ASC_CMD)|g' \
	     -e 's|@WORKDIR@|$(WORKDIR)|g' \
	     -e 's|@CHANNEL@|$(CHANNEL)|g' \
	     -e 's|@HOURS@|$(HOURS)|g' \
	     -e 's|@OUTPUT_TYPE@|$(OUTPUT_TYPE)|g' \
	     -e 's|@OUTPUT_DIR@|$(OUTPUT_DIR)|g' \
	     -e 's|@BROWSER_ARGS@|$(BROWSER_ARGS)|g' \
	     -e 's|@SCHEDULE@|$(SCHEDULE)|g' \
	     -e 's|@PERSISTENT@|$(PERSISTENT)|g' \
	     -e 's|@RANDOM_DELAY@|$(RANDOM_DELAY)|g' \
	     "$(1)" > "$(2).tmp"
	@install -m 644 "$(2).tmp" "$(2)"
	@rm -f "$(2).tmp"
endef

install:
	@command -v systemctl >/dev/null 2>&1 || \
	    { echo "error: systemctl not found; this target needs systemd"; exit 1; }
	@$(SYSTEMCTL) show-environment >/dev/null 2>&1 || \
	    { echo "error: no systemd user manager is reachable for this session"; exit 1; }
	@test -x "$(ASC_EXE)" || \
	    { echo "error: '$(ASC_EXE)' is not executable."; \
	      echo "       Install the package first (e.g. 'pip install -e .'), then"; \
	      echo "       re-run with ASC_CMD=<path to asc>, or set VENV=<venv dir>."; exit 1; }
	@test -d "$(WORKDIR)" || \
	    { echo "error: WORKDIR '$(WORKDIR)' does not exist"; exit 1; }
	@$(ASC_CMD) --version >/dev/null 2>&1 || \
	    echo "warning: '$(ASC_CMD) --version' failed; the timer may not run correctly"
	$(call render_unit,$(SERVICE_TEMPLATE),$(SERVICE_UNIT))
	$(call render_unit,$(TIMER_TEMPLATE),$(TIMER_UNIT))
	@$(SYSTEMCTL) daemon-reload
	@$(SYSTEMCTL) enable --now "$(UNIT_NAME).timer"
	@echo "Installed $(UNIT_NAME).timer from $(WORKDIR)"
	@$(SYSTEMCTL) list-timers --no-pager "$(UNIT_NAME).timer" || true

uninstall:
	@$(SYSTEMCTL) disable --now "$(UNIT_NAME).timer" 2>/dev/null || true
	@$(SYSTEMCTL) stop "$(UNIT_NAME).service" 2>/dev/null || true
	@rm -f "$(SERVICE_UNIT)" "$(TIMER_UNIT)"
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true
	@$(SYSTEMCTL) reset-failed "$(UNIT_NAME).service" "$(UNIT_NAME).timer" 2>/dev/null || true
	@echo "Removed $(UNIT_NAME).service and $(UNIT_NAME).timer from $(SYSTEMD_DIR)"

reinstall: uninstall install

status:
	@$(SYSTEMCTL) status "$(UNIT_NAME).timer" --no-pager || true
	@$(SYSTEMCTL) list-timers --no-pager "$(UNIT_NAME).timer" || true

run:
	@$(SYSTEMCTL) start "$(UNIT_NAME).service"
	@echo "Started $(UNIT_NAME).service; follow it with 'make logs'"

logs:
	@journalctl --user -u "$(UNIT_NAME).service" -n 200 --no-pager -f

enable:
	@$(SYSTEMCTL) enable --now "$(UNIT_NAME).timer"

disable:
	@$(SYSTEMCTL) disable --now "$(UNIT_NAME).timer"
