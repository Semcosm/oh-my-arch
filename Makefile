.PHONY: help check build dry-run clean

help:
	@printf '%s\\n' 'Targets:' '  make check    Validate the build model without mkarchiso' '  make dry-run  Print the default build plan' '  make build    Build the default x86_64 minimal ISO' '  make clean    Remove generated work and output files'

check:
	./oma check
	./scripts/test/test_oma.sh

dry-run:
	./oma build --arch x86_64 --profile minimal --dry-run

build:
	./oma build --arch x86_64 --profile minimal

clean:
	rm -rf .oma
	find output -mindepth 1 ! -name .gitkeep -exec rm -rf -- {} +

