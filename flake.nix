{
  description = "Airspeed";

  inputs = {
    nixpkgs.url = "nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShell = pkgs.mkShell {
          buildInputs = with pkgs; [ poetry poetry2nix (python37.withPackages (p: [ p.setuptools p.six ])) python37Packages.flake8 python310Packages.pylint ];
        };
      }
    );
}
