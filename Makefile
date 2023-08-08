VENV_DIR ?= .venv
VENV_RUN = . $(VENV_DIR)/bin/activate
PIP_CMD ?= pip
BUILD_DIR ?= dist
TEST_PATH ?= tests

usage:             ## Show this help
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

install:           ## Install dependencies in local virtualenv folder
	(test `which virtualenv` || $(PIP_CMD) install --user virtualenv) && \
		(test -e $(VENV_DIR) || virtualenv $(VENV_OPTS) $(VENV_DIR)) && \
		($(VENV_RUN) && $(PIP_CMD) install --upgrade pip) && \
		($(VENV_RUN); $(PIP_CMD) install .[dev])

publish:           ## Publish the library to the central PyPi repository
	# build and upload archive
	$(VENV_RUN); ./setup.py sdist && twine upload $(BUILD_DIR)/*.tar.gz

test:              ## Run automated tests
	$(VENV_RUN); pytest $(PYTEST_ARGS) $(TEST_PATH)

lint:              ## Run code linter to check code style
	$(VENV_RUN); flake8 airspeed tests

format:            ## Run code formatter (black/isort)
	$(VENV_RUN); python -m black airspeed tests; python -m isort airspeed tests

clean:             ## Clean up virtualenv
	rm -rf $(VENV_DIR)

.PHONY: usage install clean publish test lint format
