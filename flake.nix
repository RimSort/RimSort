{
  description = "RimSort - free, open-source RimWorld mod manager and sorter";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        pyproject-nix.follows = "pyproject-nix";
      };
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
      };
    };

    git-hooks-nix = {
      url = "github:cachix/git-hooks.nix";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        flake-compat.follows = "flake-compat";
      };
    };

    # default.nix / shell.nix entry points for nix-build and nix-shell
    flake-compat = {
      url = "github:NixOS/flake-compat";
      flake = false;
    };
  };

  # Public binary cache for the flake packages and checks. Nix applies this
  # config only after `--accept-flake-config` or an explicit approval prompt;
  # CI accepts it in its nix setup. Without it everything still works, just
  # from source.
  nixConfig = {
    extra-substituters = [ "https://rimsort.cachix.org" ];
    extra-trusted-public-keys = [ "rimsort.cachix.org-1:1UpAcYYNqR5rKrCjjMQE7kVc+hZx5Vndw6ek2OvFppI=" ];
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      # x86_64-darwin intentionally omitted (deprecated in nixpkgs)
      # Windows stays out: the app targets it, Nix does not.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      imports = [
        inputs.git-hooks-nix.flakeModule
        ./nix/parts
      ];
    };
}
