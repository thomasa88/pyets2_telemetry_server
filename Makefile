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

VERSION := $(shell cut -d '"' -f 2 version.py | sed 's/\./_/g')
FILES := LICENSE Html signalr __init__.py version.py web_server.py
PY_DIR := python/pyets2_telemetry_server

.PHONY: install
install: $(FILES)
	@( [ "x$(DESTDIR)" != "x" ] && [ -e "$(DESTDIR)" ] ) || \
	  ( echo 'Please provide DESTDIR="<ETS2 PLUGIN DIR>"'; exit 1; )
	install -d "$(DESTDIR)/$(PY_DIR)"
	cp -a $(FILES) "$(DESTDIR)/$(PY_DIR)/"

.PHONY: package
package: $(FILES)
	tar --transform 'flags=r;s|^|$(PY_DIR)/|' \
	  -cjf pyets2_telemetry_server_$(VERSION).tar.bz2 $^
