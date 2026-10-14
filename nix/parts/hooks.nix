# Reproducible validation layer (git-hooks.nix, flake-parts Pattern A).
# Mirrors the `just check` gate: the Python linters run from the locked devEnv
# venv so hook versions match uv.lock exactly, and mypy resolves app imports
# through the same environment (stubs are locked dev deps).
_: {
  perSystem =
    { config, pkgs, ... }:
    let
      devEnv = config.rimsortPython.devEnv;
      venvBin = "${devEnv}/bin";
      # pyright resolves imports from `python` on PATH; the sandboxed check
      # has no venv there, so wrap the nixpkgs pyright (which ships node,
      # unlike the pip wrapper) with the locked venv first on PATH.
      pyrightWithVenv = pkgs.writeShellScriptBin "rimsort-pyright" ''
        export PATH=${venvBin}:$PATH
        exec ${pkgs.lib.getExe pkgs.pyright} "$@"
      '';
    in
    {
      pre-commit.settings.hooks = {
        # Nix (covers the toolchain files themselves)
        nixfmt.enable = true;
        deadnix.enable = true;
        statix.enable = true;

        # Python: pinned to the lock, not to whatever nixpkgs carries
        ruff = {
          enable = true;
          entry = "${venvBin}/ruff check --fix";
        };
        ruff-format = {
          enable = true;
          entry = "${venvBin}/ruff format";
        };
        mypy = {
          enable = true;
          # Mirror `just typecheck` (repo-wide invocation): per-file mypy
          # runs crash and miss project context.
          entry = "${venvBin}/mypy --config-file pyproject.toml .";
          pass_filenames = false;
        };
        pyright = {
          enable = true;
          # Mirror `just pyright` (repo-wide invocation over the project).
          entry = "${pyrightWithVenv}/bin/rimsort-pyright -p pyproject.toml .";
          pass_filenames = false;
        };

        # Shell / Markdown (repo configs are discovered by the tools)
        shellcheck.enable = true;
        shfmt = {
          enable = true;
          # `just shfmt` runs plain `shfmt -l` (no simplify); the hook's
          # simplify default rewrites pre-existing repo scripts.
          settings.simplify = false;
        };
        markdownlint.enable = true;

        # Repo CI guard: no new function-local `import app...` without ALLOWED
        deferred-imports = {
          enable = true;
          name = "deferred-imports";
          entry = "${venvBin}/python ./check_deferred_imports.py";
          pass_filenames = false;
        };

        # Hygiene
        check-merge-conflicts.enable = true;
        detect-private-keys.enable = true;
      };

      formatter = pkgs.writeShellScriptBin "fmt" ''
        ${pkgs.lib.getExe config.pre-commit.settings.package} run --all-files --config ${config.pre-commit.settings.configFile}
      '';
    };
}
