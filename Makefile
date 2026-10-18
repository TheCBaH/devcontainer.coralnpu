.PHONY: submodule prepare fixtures build python-bindings test package ci rtl-tests
ARCHIVES ?= emulators libraries subsystem
submodule:
	git submodule update --init --recursive --depth 1
prepare: submodule
	python3 scripts/build.py prepare
fixtures: prepare
	python3 scripts/build.py fixtures
build: prepare
	python3 scripts/build.py build $(ARCHIVES)
rtl-tests: prepare
	python3 scripts/build.py rtl-tests
python-bindings: prepare
	python3 scripts/build.py python-bindings
package: build
	python3 scripts/package.py $(ARCHIVES)
test:
	bash scripts/test-archives.sh
ci: fixtures rtl-tests package test
