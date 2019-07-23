#
# Copyright 2019 Thomas Axelsson <thomasa88@gmail.com>
#
# This file is part of pyets2_telemetry_server.
#
# pyets2_telemetry_server is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# pyets2_telemetry_server is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyets2_telemetry_server.
# If not, see <https://www.gnu.org/licenses/>.
#

NAME := pyets2_telemetry_server
VERSION := $(shell cut -d '"' -f 2 version.py | sed 's/\./_/g')
FILES := LICENSE Html signalr __init__.py version.py web_server.py
PY_PLUGIN_DIR := python
PY_PKG_DIR := $(PY_PLUGIN_DIR)/$(NAME)
TAR_NAME := $(NAME)_$(VERSION).tar.bz2

.PHONY: install
install: uninstall $(FILES)
	@( [ "x$(DESTDIR)" != "x" ] && [ -e "$(DESTDIR)" ] ) || \
	  ( echo 'Please provide DESTDIR="<ETS2 PLUGIN DIR>"'; exit 1; )
	@install -d "$(DESTDIR)/$(PY_PKG_DIR)"
	@cp -a $(FILES) "$(DESTDIR)/$(PY_PKG_DIR)/"
	@echo "Installed in \"$(DESTDIR)/$(PY_PKG_DIR)\""

# Set up symbolic links to the repository
.PHONY: install-dev
install-dev: uninstall
	@( [ "x$(DESTDIR)" != "x" ] && [ -e "$(DESTDIR)" ] ) || \
	  ( echo 'Please provide DESTDIR="<ETS2 PLUGIN DIR>"'; exit 1; )
	@mkdir -p "$(DESTDIR)/$(PY_PLUGIN_DIR)"
	@ln -s $(PWD) "$(DESTDIR)/$(PY_PKG_DIR)"
	@echo "Installed links in \"$(DESTDIR)/$(PY_PKG_DIR)\""

.PHONY: uninstall
uninstall:
	@( [ "x$(DESTDIR)" != "x" ] && [ -e "$(DESTDIR)" ] ) || \
	  ( echo 'Please provide DESTDIR="<ETS2 PLUGIN DIR>"'; exit 1; )
	@rm -rf "$(DESTDIR)/$(PY_PKG_DIR)"
# Remove python dir if it is empty
	@[ ! -e "$(DESTDIR)/$(PY_PLUGIN_DIR)" ] || rmdir --ignore-fail-on-non-empty "$(DESTDIR)/$(PY_PLUGIN_DIR)"
	@echo "Uninstalled from \"$(DESTDIR)/$(PY_PKG_DIR)\""

.PHONY: package
package: $(FILES)
	@tar --transform 'flags=r;s|^|$(PY_PKG_DIR)/|' \
	  -cjf $(TAR_NAME) $^
	@echo "Created $(TAR_NAME)"
