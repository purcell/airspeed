{
  description = "Airspeed";

  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixpkgs-unstable/nixexprs.tar.zst";
  };

  outputs =
    { self, nixpkgs }:
    {
      devShell = builtins.mapAttrs (
        system: pkgs:
        pkgs.mkShell {
          buildInputs = with pkgs; [
            (python3.withPackages (
              p: with p; [
                setuptools
                cachetools
                build
                coverage
                twine
              ]
            ))
            ruff
            ty
            uv
          ];
        }
      ) nixpkgs.legacyPackages;
    };
}
