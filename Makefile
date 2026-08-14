.PHONY: setup test test-python test-rust test-web check wasm build dev preview golden clean

setup:
	npm ci

test: test-python test-rust test-web

check: test
	npm run build

test-python:
	python -m unittest discover -s tests -v

# rustfmt is invoked directly because some rustup-only installations do not
# provide cargo fmt. The Nix shell always supplies this binary.
test-rust:
	rustfmt --edition 2021 --check rust-core/src/lib.rs
	cargo test --manifest-path rust-core/Cargo.toml

test-web:
	npm test

wasm:
	npm run wasm

build:
	npm run build

dev:
	npm run dev

preview:
	npm run preview -- --host 127.0.0.1

golden:
	python tools/generate_golden.py

clean:
	rm -rf dist web/src/generated rust-core/target
