# Flake-parts parts for the Nix toolchain. Each file is one concern; the
# uv2nix pipeline is defined exactly once (python.nix) and consumed as the
# perSystem option `rimsortPython` by hooks/devshell/packages.
{
  imports = [
    ./python.nix
    ./hooks.nix
    ./devshell.nix
    ./packages.nix
  ];
}
