{
  description = "Roast Solver reference model, Rust/WASM core, and static web app";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (p: [ p.numpy ]);
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python
              cargo
              rustc
              rustfmt
              gcc
              lld
              wasm-bindgen-cli
              nodejs
              gnumake
            ];
            shellHook = ''
              echo "Roast Solver dev shell: make setup && make check"
            '';
          };
        });

      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          lib = pkgs.lib;
          source = lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let name = baseNameOf path;
              in ! builtins.elem name [
                ".git" ".venv" "__pycache__" "node_modules" "target"
                "dist" "generated" "result" ".pytest_cache"
              ];
          };
          cargoDeps = pkgs.rustPlatform.importCargoLock {
            lockFile = ./rust-core/Cargo.lock;
          };
          wasmBindings = pkgs.stdenv.mkDerivation {
            pname = "roast-solver-wasm-bindings";
            version = "0.1.0";
            src = source;
            cargoRoot = "rust-core";
            inherit cargoDeps;
            nativeBuildInputs = with pkgs; [
              cargo
              rustc
              gcc
              lld
              wasm-bindgen-cli
              rustPlatform.cargoSetupHook
            ];
            buildPhase = ''
              runHook preBuild
              cargo build --manifest-path rust-core/Cargo.toml \
                --target wasm32-unknown-unknown --features wasm --release
              runHook postBuild
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p "$out"
              wasm-bindgen \
                rust-core/target/wasm32-unknown-unknown/release/roast_solver_core.wasm \
                --target web --out-dir "$out" --out-name roast_solver_core
              runHook postInstall
            '';
          };
          web = pkgs.buildNpmPackage {
            pname = "roast-solver-web";
            version = "0.1.0";
            src = source;
            npmDepsHash = "sha256-Kv1gbEVqKZZR2/ICGdUmo6KKwMVSkT1LzdLNe4tPcv0=";
            npmBuildScript = "build:web";
            preBuild = ''
              rm -rf web/src/generated
              mkdir -p web/src/generated
              cp -R ${wasmBindings}/. web/src/generated/
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p "$out"
              cp -R dist/. "$out/"
              runHook postInstall
            '';
          };
          preview = pkgs.writeShellApplication {
            name = "roast-solver-preview";
            runtimeInputs = [ pkgs.python3 ];
            text = ''
              echo "Serving Roast Solver at http://127.0.0.1:4173"
              exec python -m http.server 4173 --bind 127.0.0.1 --directory ${web}
            '';
          };
        in {
          default = web;
          inherit web wasmBindings preview;
        });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.preview}/bin/roast-solver-preview";
        };
        preview = {
          type = "app";
          program = "${self.packages.${system}.preview}/bin/roast-solver-preview";
        };
      });

      checks = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          lib = pkgs.lib;
          source = lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let name = baseNameOf path;
              in ! builtins.elem name [
                ".git" ".venv" "__pycache__" "node_modules" "target"
                "dist" "generated" "result" ".pytest_cache"
              ];
          };
          python = pkgs.python312.withPackages (p: [ p.numpy ]);
          cargoDeps = pkgs.rustPlatform.importCargoLock {
            lockFile = ./rust-core/Cargo.lock;
          };
        in {
          python-reference = pkgs.runCommand "roast-solver-python-tests" {
            nativeBuildInputs = [ python ];
          } ''
            cp -R ${source} source
            chmod -R u+w source
            cd source
            python -m unittest discover -s tests -v
            touch "$out"
          '';

          rust-core = pkgs.stdenv.mkDerivation {
            pname = "roast-solver-rust-tests";
            version = "0.1.0";
            src = source;
            cargoRoot = "rust-core";
            inherit cargoDeps;
            nativeBuildInputs = with pkgs; [
              cargo rustc gcc rustfmt rustPlatform.cargoSetupHook
            ];
            buildPhase = ''
              rustfmt --edition 2021 --check rust-core/src/lib.rs
              cargo test --manifest-path rust-core/Cargo.toml
            '';
            installPhase = ''touch "$out"'';
          };

          wasm-bindings = self.packages.${system}.wasmBindings;
          web = self.packages.${system}.web;
        });
    };
}
