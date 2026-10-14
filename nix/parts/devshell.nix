# Pure Nix dev shell: the locked devEnv venv is the environment. Nix owns the
# env; uv is lock-only here (uv add / uv lock), never env-provisioning.
_: {
  perSystem =
    { config, pkgs, ... }:
    let
      inherit (config.rimsortPython) devEnv qtLdLibraryPathFor qtPluginPathFor;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = [
          devEnv
          pkgs.uv
          pkgs.just
        ]
        ++ config.pre-commit.settings.enabledPackages;

        env = {
          # uv must not shadow the Nix environment
          UV_NO_SYNC = "1";
          UV_PYTHON_DOWNLOADS = "never";
        }
        // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          # the PySide6 wheel's Qt dlopens system libs at runtime
          LD_LIBRARY_PATH = qtLdLibraryPathFor devEnv;
        };

        shellHook = ''
          ${config.pre-commit.shellHook}
          unset PYTHONPATH
          export QT_QPA_PLATFORM_PLUGIN_PATH=${qtPluginPathFor devEnv}
          echo "RimSort dev shell (Nix). Python tools come from uv.lock via uv2nix." 1>&2
          echo "Run the app: python -m app --dev   (not: uv run python -m app)" 1>&2
          echo "Tests:       pytest --doctest-modules --no-qt-log -s   (just targets call uv run; use bare tools here)" 1>&2
          echo "Deps:        uv add <pkg> && uv lock   (lock only; Nix rebuilds from it)" 1>&2
        '';
      };
    };
}
