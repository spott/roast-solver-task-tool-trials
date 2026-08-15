{
  description = "Roast Solver M1-M6: NumPy reference, Rust/WASM core, and static UI";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = function: nixpkgs.lib.genAttrs systems (system: function (import nixpkgs { inherit system; }));
    in {
      packages = forAllSystems (pkgs:
        let
          python = pkgs.python312;
          pythonPackage = python.pkgs.buildPythonPackage {
            pname = "roast-solver";
            version = "0.1.0";
            src = ./.;
            pyproject = true;
            build-system = [ python.pkgs.setuptools ];
            dependencies = [ python.pkgs.numpy ];
            nativeCheckInputs = [ python.pkgs.pytestCheckHook ];
            pythonImportsCheck = [ "roast_solver" ];
          };
          wasmCore = pkgs.rustPlatform.buildRustPackage {
            pname = "roast-core-wasm";
            version = "0.1.0";
            src = ./rust-core;
            cargoLock.lockFile = ./rust-core/Cargo.lock;
            CARGO_BUILD_TARGET = "wasm32-unknown-unknown";
            RUSTFLAGS = "-C target-feature=+simd128";
            cargoBuildFlags = [ "--lib" ];
            doCheck = false;
            installPhase = ''
              mkdir -p $out/lib
              cp target/wasm32-unknown-unknown/release/roast_core.wasm $out/lib/
            '';
          };
          web = pkgs.stdenvNoCC.mkDerivation {
            pname = "roast-solver-web";
            version = "0.1.0";
            src = ./web;
            nativeBuildInputs = [ pkgs.nodejs_22 ];
            buildPhase = ''
              ROAST_SKIP_WASM=1 npm run build
              cp ${wasmCore}/lib/roast_core.wasm dist/
            '';
            installPhase = "mkdir -p $out; cp -r dist/. $out/";
          };
        in {
          default = web;
          inherit web pythonPackage wasmCore;
        });

      checks = forAllSystems (pkgs:
        let packages = self.packages.${pkgs.system};
        in {
          python = packages.pythonPackage;
          rust = pkgs.rustPlatform.buildRustPackage {
            pname = "roast-core-tests";
            version = "0.1.0";
            src = ./.;
            cargoRoot = "rust-core";
            buildAndTestSubdir = "rust-core";
            cargoLock.lockFile = ./rust-core/Cargo.lock;
          };
          web = pkgs.runCommand "roast-web-tests" { nativeBuildInputs = [ pkgs.nodejs_22 ]; } ''
            cp -r ${./web} source
            chmod -R +w source
            cd source
            npm test
            ROAST_SKIP_WASM=1 npm run build
            test -f dist/index.html
            touch $out
          '';
        });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python312.withPackages (p: [ p.numpy p.pytest p.setuptools ]))
            pkgs.rustc pkgs.cargo pkgs.rustfmt pkgs.lld pkgs.nodejs_22 pkgs.binaryen
          ];
          shellHook = ''
            echo "Roast Solver dev shell: pytest · cargo test --manifest-path rust-core/Cargo.toml · npm --prefix web run build"
          '';
        };
      });
    };
}
