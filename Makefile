
.PHONY: test

ENV_NAME=discourse-importer
BIN_DIR=$(CURDIR)/$(ENV_NAME)/bin

default: run

install:
	conda create python=3 -y -p $(CURDIR)/$(ENV_NAME) --file requirements.txt
	$(BIN_DIR)/pip install --upgrade pip
	$(BIN_DIR)/python $(CURDIR)/setup.py develop
	$(BIN_DIR)/pip install -e $(CURDIR)/.

clean:
	rm -rf $(CURDIR)/$(ENV_NAME)
	rm -rf $(CURDIR)/build
	rm -rf $(CURDIR)/dist
	rm -rf $(CURDIR)/src/discourse_importer.egg-info
	find $(CURDIR) -name '*.pyc' -exec rm {} \;

run:
	$(MAKE) clean
	$(MAKE) install
