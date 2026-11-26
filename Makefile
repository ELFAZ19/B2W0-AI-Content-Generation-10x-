PYTHON ?= python

.PHONY: film draft radio-cut rough-cut validate smoke test clean-cache

film:
	$(PYTHON) -m pipeline run --quality final

draft:
	$(PYTHON) -m pipeline run --quality draft

radio-cut:
	$(PYTHON) -m pipeline validate
	$(PYTHON) -m pipeline narration
	$(PYTHON) -m pipeline assemble --radio-cut

rough-cut:
	$(PYTHON) -m pipeline validate
	$(PYTHON) -m pipeline narration
	$(PYTHON) -m pipeline keyframes
	$(PYTHON) -m pipeline music
	$(PYTHON) -m pipeline assemble --rough-cut

validate:
	$(PYTHON) -m pipeline validate

smoke:
	$(PYTHON) -m pipeline smoke

test:
	$(PYTHON) -m pytest -v

clean-cache:
	$(PYTHON) -c "import shutil; shutil.rmtree('outputs/.cache_manifest.json', ignore_errors=True)"
