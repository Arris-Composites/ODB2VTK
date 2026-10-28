UV ?= uv
.DEFAULT_GOAL := format-check

.PHONY: format format-check

format:
	$(UV) run --no-project python tools/format_cpp.py

format-check:
	$(UV) run --no-project python tools/format_cpp.py --check
