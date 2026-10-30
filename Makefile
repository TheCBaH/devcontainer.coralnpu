.PHONY: submodule prepare fixtures build python-bindings test package ci rtl-tests dma-tests trace-tests
ARCHIVES ?= emulators subsystem
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
dma-tests: prepare
	bash scripts/dma-tests.sh $(DMA_TEST_GROUPS)
trace-tests: prepare
	bash scripts/trace-tests.sh
python-bindings: prepare
	python3 scripts/build.py python-bindings
package: build
	python3 scripts/package.py $(ARCHIVES)
test:
	bash scripts/test-archives.sh
ci: fixtures rtl-tests dma-tests trace-tests package test
