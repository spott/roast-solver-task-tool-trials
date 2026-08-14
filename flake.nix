{
  description = "Roast Solver Python oracle, Rust/WASM core, and static web app";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in {
      devShells = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
            python = pkgs.python3.withPackages (p: [ p.numpy p.pytest ]);
        in { default = pkgs.mkShell {
          packages = [ python pkgs.nodejs_22 pkgs.rustc pkgs.cargo pkgs.wasm-pack pkgs.wasm-bindgen-cli pkgs.binaryen pkgs.lld ];
          shellHook = ''echo "Roast Solver: python, NumPy, Rust, wasm-pack, and Node are ready"'';
        }; });

      packages = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
            cargoDeps = pkgs.rustPlatform.fetchCargoVendor {
              src = self;
              hash = "sha256-9P2NOhMhAqkcyzXPBuN+n4y70hiRVllTqflOlrAaIFc=";
            };
        in {
          default = pkgs.buildNpmPackage {
            pname = "roast-solver-static"; version = "0.1.0"; src = self;
            npmDepsHash = "sha256-KlIV9uzpQ/3r4+g4CF/GnDdh5HW6s5qQAOpuyM4aaqE=";
            inherit cargoDeps;
            nativeBuildInputs = [ pkgs.wasm-pack pkgs.wasm-bindgen-cli pkgs.binaryen pkgs.lld pkgs.cargo pkgs.rustc pkgs.rustPlatform.cargoSetupHook ];
            buildPhase = ''runHook preBuild; npm run build; runHook postBuild'';
            installPhase = ''mkdir -p $out; cp -r dist/. $out/'';
          };
        });
    };
}
