.PHONY: submodule prepare fixtures build python-bindings test package ci
ARCHIVES ?= emulators libraries subsystem
submodule:
	git submodule update --init --recursive --depth 1
prepare: submodule
	python3 scripts/build.py prepare
fixtures: prepare
	python3 scripts/build.py fixtures
build: prepare
	python3 scripts/build.py build $(ARCHIVES)
python-bindings: prepare
	python3 scripts/build.py python-bindings
package: build
	python3 scripts/package.py $(ARCHIVES)
test:
	bash scripts/test-archives.sh
ci: fixtures package test
