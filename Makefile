UV ?= uv
.DEFAULT_GOAL := format-check

.PHONY: format format-check install-skills

format:
	$(UV) run --no-project python tools/format_cpp.py

format-check:
	$(UV) run --no-project python tools/format_cpp.py --check

install-skills:
	$(UV) run --no-project python tools/install_skills.py
