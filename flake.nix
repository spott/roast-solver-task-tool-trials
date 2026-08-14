{
  description = "Roast Solver M1-M6 reference, WASM app, and validation environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay.url = "github:oxalica/rust-overlay";
    rust-overlay.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, rust-overlay }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; overlays = [ (import rust-overlay) ]; };
          rust = pkgs.rust-bin.stable.latest.default.override {
            extensions = [ "rustfmt" ];
            targets = [ "wasm32-unknown-unknown" ];
          };
          wasmBindgen = pkgs.wasm-bindgen-cli_0_2_126 or pkgs.wasm-bindgen-cli;
          cargoDeps = pkgs.rustPlatform.importCargoLock {
            lockFile = ./web-core/Cargo.lock;
          };
        in {
          default = pkgs.stdenvNoCC.mkDerivation {
            pname = "roast-solver-static";
            version = "0.1.0";
            src = self;
            inherit cargoDeps;
            cargoRoot = "web-core";
            nativeBuildInputs = [
              rust
              pkgs.rustPlatform.cargoSetupHook
              wasmBindgen
              pkgs.nodejs_22
            ];
            buildPhase = ''
              runHook preBuild
              cargo build --locked --manifest-path web-core/Cargo.toml \
                --target wasm32-unknown-unknown --release
              mkdir -p dist/wasm dist/docs
              wasm-bindgen \
                web-core/target/wasm32-unknown-unknown/release/roast_solver_web_core.wasm \
                --target web --out-dir dist/wasm
              cp web/index.html web/styles.css web/app.js web/worker.js dist/
              cp docs/PHYSICS.md docs/VALIDATION.md docs/CALIBRATION.md docs/PARITY.md dist/docs/
              node web/scripts/check.mjs
              runHook postBuild
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p $out
              cp -R dist/. $out/
              runHook postInstall
            '';
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; overlays = [ (import rust-overlay) ]; };
          rust = pkgs.rust-bin.stable.latest.default.override { extensions = [ "rustfmt" ]; };
          python = pkgs.python312.withPackages (p: [ p.numpy p.pytest ]);
          cargoDeps = pkgs.rustPlatform.importCargoLock {
            lockFile = ./web-core/Cargo.lock;
          };
        in {
          python = pkgs.runCommand "roast-solver-python-tests" {
            nativeBuildInputs = [ python ];
          } ''
            cp -R ${self} source
            chmod -R u+w source
            cd source/python
            PYTHONPATH=. pytest -q
            touch $out
          '';

          rust = pkgs.stdenv.mkDerivation {
            pname = "roast-solver-rust-tests";
            version = "0.1.0";
            src = self;
            inherit cargoDeps;
            cargoRoot = "web-core";
            nativeBuildInputs = [ rust pkgs.rustPlatform.cargoSetupHook ];
            buildPhase = ''
              runHook preBuild
              cargo test --locked --manifest-path web-core/Cargo.toml
              cargo fmt --manifest-path web-core/Cargo.toml --all -- --check
              runHook postBuild
            '';
            installPhase = ''
              touch $out
            '';
          };

          web = self.packages.${system}.default;
        });

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; overlays = [ (import rust-overlay) ]; };
          rust = pkgs.rust-bin.stable.latest.default.override {
            extensions = [ "rustfmt" ];
            targets = [ "wasm32-unknown-unknown" ];
          };
          python = pkgs.python312.withPackages (p: [ p.numpy p.pytest ]);
        in {
          default = pkgs.mkShell {
            packages = [
              python
              rust
              pkgs.wasm-pack
              (pkgs.wasm-bindgen-cli_0_2_126 or pkgs.wasm-bindgen-cli)
              pkgs.nodejs_22
              pkgs.pkg-config
            ];
            shellHook = ''
              export PYTHONPATH="$PWD/python''${PYTHONPATH:+:$PYTHONPATH}"
              echo "Roast Solver shell: npm test | npm run build | npm run preview"
            '';
          };
        });
    };
}
