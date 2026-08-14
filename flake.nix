{
  description = "Roast Solver M1-M6 reference, Rust/WASM core, and static web app";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          core = pkgs.rustPlatform.buildRustPackage {
            pname = "roast-solver-core";
            version = "0.1.0";
            src = pkgs.lib.cleanSource ./.;
            cargoLock.lockFile = ./web-core/Cargo.lock;
            cargoRoot = "web-core";
            buildAndTestSubdir = "web-core";
          };
          wasm = pkgs.rustPlatform.buildRustPackage {
            pname = "roast-solver-wasm";
            version = "0.1.0";
            src = pkgs.lib.cleanSource ./.;
            cargoLock.lockFile = ./web-core/Cargo.lock;
            cargoRoot = "web-core";
            buildAndTestSubdir = "web-core";
            doCheck = false;
            nativeBuildInputs = [ pkgs.lld pkgs.wasm-bindgen-cli pkgs.binaryen ];
            buildPhase = ''
              runHook preBuild
              cargo build --manifest-path web-core/Cargo.toml --offline --locked \
                --release --target wasm32-unknown-unknown
              runHook postBuild
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p $out
              wasm-bindgen --target web --out-dir $out \
                web-core/target/wasm32-unknown-unknown/release/roast_solver_core.wasm
              wasm-opt -Oz -o $out/core.opt.wasm $out/roast_solver_core_bg.wasm
              mv $out/core.opt.wasm $out/roast_solver_core_bg.wasm
              runHook postInstall
            '';
          };
          web = pkgs.buildNpmPackage {
            pname = "roast-solver-web";
            version = "0.1.0";
            src = ./web;
            npmDepsHash = "sha256-Ifc6WZ5Z7lbOS7+UsmvJlKfOYxkbv2bEMTxyt4WZrXI=";
            npmBuildScript = "build:web";
            preBuild = ''
              rm -rf src/wasm
              mkdir -p src/wasm
              cp -r ${wasm}/. src/wasm/
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p $out
              cp -r dist/. $out/
              runHook postInstall
            '';
          };
          wasm-smoke = pkgs.runCommand "roast-solver-wasm-smoke" {
            nativeBuildInputs = [ pkgs.nodejs_22 ];
          } ''
            mkdir -p work/web/src/wasm work/scripts
            cp -r ${wasm}/. work/web/src/wasm/
            cp ${./scripts/smoke-wasm.mjs} work/scripts/smoke-wasm.mjs
            cd work
            node scripts/smoke-wasm.mjs
            touch $out
          '';
        in {
          inherit core wasm wasm-smoke web;
          default = web;
          python-reference = pkgs.python312Packages.buildPythonPackage {
            pname = "roast-solver";
            version = "0.1.0";
            pyproject = true;
            src = pkgs.lib.cleanSource ./.;
            build-system = [ pkgs.python312Packages.setuptools ];
            dependencies = [ pkgs.python312Packages.numpy ];
            nativeCheckInputs = [ pkgs.python312Packages.pytestCheckHook ];
            pythonImportsCheck = [ "roast_solver" ];
          };
        });

      checks = forAllSystems (system:
        let packages = self.packages.${system}; in {
          inherit (packages) core wasm wasm-smoke web python-reference;
        });

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (ps: [ ps.numpy ps.pytest ]);
        in {
          default = pkgs.mkShell {
            packages = [
              python pkgs.nodejs_22 pkgs.rustc pkgs.cargo pkgs.rustfmt pkgs.clippy
              pkgs.lld pkgs.wasm-bindgen-cli pkgs.binaryen pkgs.python312Packages.build
            ];
            shellHook = ''
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
              echo "Roast Solver dev shell: Python, Rust/WASM, Node, and validation tools ready."
            '';
          };
        });
    };
}
