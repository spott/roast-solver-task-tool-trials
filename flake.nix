{
  description = "Roast Solver M1-M6: NumPy reference, Rust/WASM core, static web app";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (ps: with ps; [ numpy pytest setuptools ]);
        in {
          default = pkgs.mkShell {
            packages = [ python pkgs.nodejs_22 pkgs.cargo pkgs.rustc pkgs.rustfmt pkgs.lld pkgs.curl ];
            shellHook = ''
              export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
              echo "Roast Solver dev shell: python, NumPy, pytest, Rust/wasm, Node"
            '';
          };
        });

      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          clean = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let rel = pkgs.lib.removePrefix (toString ./.) (toString path);
              in !(pkgs.lib.hasInfix "/target" rel || pkgs.lib.hasInfix "/dist" rel ||
                   pkgs.lib.hasInfix "/.git" rel || pkgs.lib.hasInfix "/.venv" rel ||
                   pkgs.lib.hasInfix "/__pycache__" rel || pkgs.lib.hasInfix "/.pytest_cache" rel);
          };
        in {
          default = pkgs.stdenvNoCC.mkDerivation {
            pname = "roast-solver-web";
            version = "0.1.0";
            src = clean;
            nativeBuildInputs = [ pkgs.nodejs_22 pkgs.cargo pkgs.rustc pkgs.lld ];
            buildPhase = ''
              export HOME=$TMPDIR
              npm run build
            '';
            installPhase = "cp -r dist $out";
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (ps: with ps; [ numpy pytest setuptools ]);
        in {
          python = pkgs.runCommand "roast-solver-python-tests" { nativeBuildInputs = [ python ]; } ''
            cp -r ${./roast_solver} roast_solver
            cp -r ${./tests} tests
            cp -r ${./fixtures} fixtures
            export PYTHONPATH=$PWD
            python -m pytest tests
            touch $out
          '';
          rust = pkgs.runCommand "roast-solver-rust-tests" {
            nativeBuildInputs = [ pkgs.cargo pkgs.rustc pkgs.lld pkgs.stdenv.cc ];
          } ''
            cp -r ${./rust_core} rust_core
            cp -r ${./fixtures} fixtures
            chmod -R u+w .
            export HOME=$TMPDIR
            cargo test --manifest-path rust_core/Cargo.toml
            touch $out
          '';
          ui = pkgs.runCommand "roast-solver-ui-tests" { nativeBuildInputs = [ pkgs.nodejs_22 ]; } ''
            cp -r ${./web} web
            node --test web/ui-utils.test.js
            touch $out
          '';
        });
    };
}
