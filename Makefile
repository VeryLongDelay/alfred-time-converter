PYTHON := /usr/bin/env python3
WORKFLOW_DIR := workflow
WORKFLOW_FILE := UT-Time-Converter.alfredworkflow
SOURCE_ZIP := ut-time-converter-source.zip

.PHONY: run test build build-workflow clean

run:
	$(PYTHON) $(WORKFLOW_DIR)/main.py

test:
	$(PYTHON) test.py

build:
	rm -f $(SOURCE_ZIP)
	zip -r $(SOURCE_ZIP) \
		$(WORKFLOW_DIR) \
		README.md \
		test.py \
		Makefile \
		-x '*.DS_Store' \
		-x '*.alfredworkflow'

build-workflow:
	rm -f $(WORKFLOW_FILE)
	cd $(WORKFLOW_DIR) && zip -r ../$(WORKFLOW_FILE) . \
		-x '*.DS_Store' \
		-x '__pycache__/*' \
		-x '*.pyc' \
		-x '.pytest_cache/*'

clean:
	rm -f $(SOURCE_ZIP) $(WORKFLOW_FILE)
