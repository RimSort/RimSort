# Flake-parts parts for the Nix toolchain. Each file is one concern; the
# uv2nix pipeline is defined exactly once (python.nix) and consumed as the
# perSystem option `rimsortPython` by hooks/devshell/packages.
{ lib, inputs, ... }:
{
  imports = [
    ./python.nix
    ./hooks.nix
    ./devshell.nix
    ./packages.nix
  ];

  # One nixpkgs instance for every part. The packaged app legitimately
  # touches proprietary bits (steam-run FHS env, valve SDK libsteam_api.so),
  # so only steam and rimsort itself are allowed through the unfree gate.
  perSystem =
    { system, ... }:
    {
      _module.args.pkgs = import inputs.nixpkgs {
        inherit system;
        config.allowUnfreePredicate =
          pkg:
          builtins.elem (lib.getName pkg) [
            "rimsort"
            "rimsort-tests"
            "steam"
            "steam-unwrapped"
          ];
      };
    };
}
