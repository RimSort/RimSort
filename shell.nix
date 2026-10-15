# nix-shell entry point (flake-compat); the flake is the source of truth.
(import ./default.nix).devShells.${builtins.currentSystem}.default
