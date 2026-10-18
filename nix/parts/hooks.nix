# Reproducible validation layer (git-hooks.nix, flake-parts Pattern A).
# Mirrors the `just check` gate: the Python linters run from the locked devEnv
# venv so hook versions match uv.lock exactly, and mypy resolves app imports
# through the same environment (stubs are locked dev deps).
{ lib, ... }:
{
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

        # Shell (repo configs are discovered by the tools)
        shellcheck.enable = true;
        shfmt = {
          enable = true;
          # `just shfmt` runs plain `shfmt -l` (no simplify); the hook's
          # simplify default rewrites pre-existing repo scripts.
          settings.simplify = false;
        };

        # Mirror `just markdownlint`: the hook passes an explicit config, so
        # feed it .markdownlint.json and the globs of .markdownlint-cli2.jsonc.
        markdownlint = {
          enable = true;
          settings.configuration = lib.importJSON ../../.markdownlint.json;
          files = "^(docs/.*|[^/]*)\\.md$";
          excludes = [ "^LICENSE\\.md$" ];
        };

        # Repo CI guard: no new function-local `import app...` without ALLOWED
        deferred-imports = {
          enable = true;
          name = "deferred-imports";
          entry = "${venvBin}/python ./check_deferred_imports.py";
          pass_filenames = false;
        };

        # Repo CI guard: EventBus subscribers must be Qt objects or retained.
        # PySide6 does not keep bound-method receivers alive, so an unretained
        # plain-class subscriber is collected and its slots go silent (#2539).
        eventbus-subscribers = {
          enable = true;
          name = "eventbus-subscribers";
          entry = "${venvBin}/python ./check_eventbus_subscribers.py";
          pass_filenames = false;
        };

        # Hygiene
        check-merge-conflicts.enable = true;
        detect-private-keys.enable = true;
      }
      # Copy/paste detection, mirroring `just jscpd`, but via the
      # flake-provided binary so the version and thresholds match
      # `nix flake check` and CI instead of an npx download that cannot exec
      # on NixOS. Whole-repo by nature: duplication is a property of the tree,
      # not of a single file, hence pass_filenames = false. Declared only
      # where tools.nix provides a derivation for the system.
      // lib.optionalAttrs config.rimsortTools.jscpdSupported {
        jscpd = {
          enable = true;
          name = "jscpd";
          entry = "${config.rimsortTools.jscpdDrv}/bin/jscpd . --config .jscpd.json";
          pass_filenames = false;
        };
      };

      formatter = pkgs.writeShellScriptBin "fmt" ''
        ${pkgs.lib.getExe config.pre-commit.settings.package} run --all-files --config ${config.pre-commit.settings.configFile}
      '';
    };
}
