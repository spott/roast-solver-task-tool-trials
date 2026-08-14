{
  description = "Roast Solver M6: NumPy reference, Rust/WASM core, static UI";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in {
      devShells = eachSystem (system: let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (p: [ p.numpy p.pytest p.setuptools ]);
      in { default = pkgs.mkShell {
        packages = [ python pkgs.rustc pkgs.cargo pkgs.llvmPackages.lld pkgs.nodejs_22 ];
        shellHook = ''
          export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
          echo "Roast Solver dev shell — pytest | cargo test --manifest-path rust-core/Cargo.toml | npm run build"
        '';
      }; });

      checks = eachSystem (system: let pkgs = import nixpkgs { inherit system; }; in {
        python = pkgs.runCommand "roast-solver-python-tests" {
          nativeBuildInputs = [ (pkgs.python3.withPackages (p: [ p.numpy p.pytest ])) ];
          src = self;
        } ''
          cp -r $src source; chmod -R u+w source; cd source
          PYTHONPATH=. pytest
          touch $out
        '';
        rust = pkgs.runCommand "roast-solver-core-check" {
          nativeBuildInputs = [ pkgs.rustc pkgs.cargo pkgs.stdenv.cc ]; src = self;
        } ''
          cp -r $src source; chmod -R u+w source; cd source
          cargo test --manifest-path rust-core/Cargo.toml
          touch $out
        '';
        web = pkgs.runCommand "roast-solver-web-check" { nativeBuildInputs = [ pkgs.nodejs_22 ]; src = self; } ''
          cp -r $src source; chmod -R u+w source; cd source
          npm test
          SKIP_WASM=1 npm run build
          cp -r dist $out
        '';
      });

      packages = eachSystem (system: let pkgs = import nixpkgs { inherit system; }; in {
        default = pkgs.stdenvNoCC.mkDerivation {
          pname = "roast-solver-static"; version = "0.1.0"; src = self;
          nativeBuildInputs = [ pkgs.nodejs_22 pkgs.rustc pkgs.cargo pkgs.llvmPackages.lld ];
          buildPhase = "REQUIRE_WASM=1 npm run build";
          installPhase = "mkdir -p $out; cp -r dist/* $out/";
        };
      });
    };
}
