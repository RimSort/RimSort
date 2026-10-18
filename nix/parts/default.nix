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
    ./tools.nix
  ];

  # One nixpkgs instance for every part. The packaged app legitimately
  # touches proprietary bits (steam-run FHS env, valve SDK libsteam_api.so),
  # so only steam and rimsort itself are allowed through the unfree gate.
  perSystem =
    { system, ... }:
    {
      _module.args.pkgs = import inputs.nixpkgs {
        inherit system;
        config = {
          allowUnfreePredicate =
            pkg:
            builtins.elem (lib.getName pkg) [
              "rimsort"
              "rimsort-tests"
              "steam"
              "steam-unwrapped"
            ];
          # checkov (the IaC linter for .github/workflows) pulls
          # python3.14-ecdsa, which nixpkgs marks insecure for CVE-2024-23342:
          # a timing side-channel in ECDSA signature verification that can
          # recover private key material given enough signatures.
          #
          # Accepted because checkov is a developer-time lint tool, is not part
          # of the rimsort runtime closure, and does not exercise the
          # vulnerable code path (signature verification). Drop this if checkov
          # ever leaves the hook set.
          #
          # nixpkgs pins the name, so a bump that renames it fails loudly here
          # instead of silently.
          permittedInsecurePackages = [ "python3.14-ecdsa-0.19.2" ];
        };
      };
    };
}
