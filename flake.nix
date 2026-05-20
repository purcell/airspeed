{
  description = "Airspeed";

  inputs = {
    nixpkgs.url = "nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { self, nixpkgs }:
    (
      let
        forAllSystems = nixpkgs.lib.genAttrs nixpkgs.lib.platforms.all;
      in
      {
        devShell = forAllSystems (
          system:
          let
            pkgs = import nixpkgs { inherit system; };
          in
          pkgs.mkShell {
            buildInputs = with pkgs; [
              (python3.withPackages (
                p: with p; [
                  setuptools
                  cachetools
                  build
                  coverage
                ]
              ))
              ruff
              ty
              uv
            ];
          }
        );
      }
    );
}
