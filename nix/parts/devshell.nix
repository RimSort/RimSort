# Pure Nix dev shell: the locked devEnv venv is the environment. Nix owns the
# env; uv is lock-only here (uv add / uv lock), never env-provisioning.
{ lib, ... }:
{
  perSystem =
    { config, pkgs, ... }:
    let
      inherit (config.rimsortPython) devEnv qtLdLibraryPathFor qtPluginPathFor;
      hooks = config.pre-commit.settings;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = [
          devEnv
          pkgs.uv
          pkgs.just
        ]
        ++ hooks.enabledPackages;

        env = {
          # uv must not shadow the Nix environment: `uv run` resolves to the
          # locked devEnv instead of provisioning its own venv
          UV_NO_SYNC = "1";
          UV_PYTHON_DOWNLOADS = "never";
          UV_PROJECT_ENVIRONMENT = "${devEnv}";
          # just recipes skip `uv sync` (the env is read-only)
          RIMSORT_NIX_SHELL = "1";
        }
        // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          # the PySide6 wheel's Qt dlopens system libs at runtime
          LD_LIBRARY_PATH = qtLdLibraryPathFor devEnv;
        };

        shellHook = ''
          # The git-hooks.nix installer unsets core.hooksPath; keep an explicit
          # `just install-hooks` choice instead of silently replacing it.
          if [ "$(${lib.getExe hooks.gitPackage} config --get core.hooksPath 2>/dev/null)" = ".githooks" ]; then
            echo "core.hooksPath=.githooks (just install-hooks) kept; Nix pre-commit hooks not installed" 1>&2
          else
            ${hooks.installationScript}
          fi
          export PATH=${hooks.package}/bin:$PATH
          unset PYTHONPATH
          export QT_QPA_PLATFORM_PLUGIN_PATH=${qtPluginPathFor devEnv}
          echo "RimSort dev shell (Nix). Python tools come from uv.lock via uv2nix." 1>&2
          echo "Run the app: python -m app --dev   (or: just run)" 1>&2
          echo "Tests:       just test" 1>&2
          echo "Deps:        uv add <pkg> && uv lock   (lock only; Nix rebuilds from it)" 1>&2
        '';
      };
    };
}
