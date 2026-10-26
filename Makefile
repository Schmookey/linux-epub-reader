.PHONY: test check build-deb

test:
	python3 -m unittest discover -s tests -v

check:
	python3 -m py_compile src/linux_epub_reader.py tests/test_reader.py
	bash -n scripts/build-deb.sh
	$(MAKE) test

build-deb:
	bash scripts/build-deb.sh
