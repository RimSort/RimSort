# Packaged app + checks. Source is the flake's own tree (self.outPath) with
# the submodule contents overlaid from fetchFromGitHub at the repo's pinned
# revs (flake git-tree sources drop gitlink contents and SteamworksPy is a
# runtime import). Ships the desktop item with the self-updater disabled.
# - Python environment comes from uv.lock via uv2nix (appEnv); steamfiles
#   therefore comes from the lock, not the submodule build.
# - The wrapper exports the app's RIMSORT_LAUNCH_PREFIX / RIMSORT_TODDS_PATH
#   hooks so packaged launches resolve steam-run and todds without patching
#   the sources (tests run against the same unpatched tree).
# - Steamworks libraries come from the repo's vendored libs/ (loaded from
#   there via _libs); nothing is overlaid at the tree root.
# - Qt env vars are set explicitly on the wrapper: the PySide6 wheel bundles
#   its own Qt, which must not be wrapped against nixpkgs' qtbase
#   (version skew).
{ lib, inputs, ... }:
{
  perSystem =
    { config, system, ... }:
    let
      # Shadow the module `pkgs` for this part only: the packaged app
      # legitimately touches proprietary bits (steam-run FHS env, valve SDK
      # libsteam_api.so). nixpkgs marks those unfree, so building rimsort
      # requires an allowUnfree predicate. Scope it to this part: only steam
      # and rimsort itself are allowed through; hooks/devshell keep the
      # gated package set.
      pkgs = import inputs.nixpkgs {
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
      inherit (config.rimsortPython)
        appEnv
        devEnv
        qtLdLibraryPathFor
        qtPluginPathFor
        ;

      # Both derivations below ship GPL code plus the valve SDK blob.
      licenses = with lib.licenses; [
        gpl3Only
        # For libsteam_api.so (app package; the test drv shares the source)
        valveSDK
      ];

      # Release parity (forgetful pattern): default dev version, release
      # injects the real tag: RIMSORT_VERSION=v1.2.3 nix build --impure
      version =
        let
          r = builtins.tryEval (builtins.getEnv "RIMSORT_VERSION");
          e = if r.success then r.value else "";
        in
        if e != "" then e else "0.0.0+dev";

      # Packaged source tree WITH submodule contents, always pure.
      # inputs.self.outPath materializes the repo (gitignore-aware; dirty
      # trees copy the working state like every other nix build), but flake
      # git-tree sources drop gitlink contents and SteamworksPy is a runtime
      # import (from steamworks import STEAMWORKS resolves against it). We
      # are the repo, so its tree comes from self, while the SteamworksPy
      # contents are fetched at the repo's own pinned revision and overlaid
      # back into submodules/. steamfiles is not fetched: it comes from
      # uv.lock. Update the pin below when the repo's submodule pin moves
      # (compare `git submodule status`).
      submoduleSrcs = pkgs.linkFarm "rimsort-submodules" [
        {
          name = "SteamworksPy";
          path = pkgs.fetchFromGitHub {
            owner = "RimSort";
            repo = "SteamworksPy";
            rev = "7b35e08ed33055b15e6581fce7fc65da3e3e3e53";
            hash = "sha256-3abd5W/6sDjIWfhBK8JqPgLmBHwGdjEmKr29laWPF5Y=";
          };
        }
      ];
      src = pkgs.runCommand "rimsort-src" { } ''
        mkdir $out
        cp -r ${inputs.self.outPath}/. $out/
        chmod -R u+w $out
        # Depending on the Nix version the self tree has no submodules/ at all
        # or empty gitlink directories; copy the contents into place instead
        # of nesting below an existing directory.
        for sub in ${submoduleSrcs}/*; do
          dest="$out/submodules/$(basename "$sub")"
          mkdir -p "$dest"
          cp -r "$sub/." "$dest/"
        done
        chmod -R u+w $out/submodules
      '';

      # Launch prefix exported to the app via RIMSORT_LAUNCH_PREFIX (game +
      # SteamCMD run inside the Steam runtime FHS env)
      steam-run = (pkgs.steam.override { privateTmp = false; }).run;

      # PySide6 wheels bundle their own Qt; it still dlopens system libs
      qtWrapperFlags = lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        "--set"
        "QT_QPA_PLATFORM_PLUGIN_PATH"
        (qtPluginPathFor appEnv)
        "--prefix"
        "LD_LIBRARY_PATH"
        ":"
        (qtLdLibraryPathFor appEnv)
      ];

      # Tests run against the same (unpatched) source that ships in the
      # package. Only the network-dependent tests are skipped, like the
      # nixpkgs package's disabledTestPaths; the hardcoded-executable tests
      # nixpkgs disables pass here because our sources are never patched.
      pytestDrv = pkgs.stdenv.mkDerivation {
        pname = "rimsort-tests";
        inherit version src;

        nativeBuildInputs = [ devEnv ];

        dontBuild = true;
        doCheck = true;

        preCheck = ''
          export HOME=$(mktemp -d)
          export QT_QPA_PLATFORM=offscreen
        '';

        checkPhase = ''
          runHook preCheck
          ${devEnv}/bin/pytest \
            --doctest-modules --no-qt-log -s \
            --ignore=tests/models/metadata/test_metadata_factory.py \
            --ignore=tests/utils/test_privatebin.py
          runHook postCheck
        '';

        installPhase = ''
          mkdir -p $out
          echo "pytest passed" > $out/result
        '';

        meta = {
          description = "RimSort test suite (uv2nix env, pinned source)";
          license = licenses;
        };
      };

      appPkg = pkgs.stdenv.mkDerivation (finalAttrs: {
        pname = "rimsort";
        inherit version src;

        __structuredAttrs = true;

        # Copy the tree (writable). The repo vendors its own Steamworks
        # libraries under libs/, refreshed by distribute.py at release
        # time, and the app loads them from there via _libs.
        unpackPhase = ''
          runHook preUnpack

          cp -r ${finalAttrs.src} source
          chmod -R 755 source

          runHook postUnpack
        '';

        sourceRoot = "source";

        nativeBuildInputs = [
          pkgs.makeBinaryWrapper
          pkgs.copyDesktopItems
        ];

        # Pure Python: nothing to compile. todds and steam-run are not
        # build-time inputs either: they reach the closure through the
        # wrapper's RIMSORT_TODDS_PATH / RIMSORT_LAUNCH_PREFIX values.
        dontBuild = true;

        installPhase = ''
          runHook preInstall

          mkdir -p $out/lib/rimsort $out/bin
          # AppInfo resolves themes/, locales/, libs/, submodules/ as siblings
          # of the app package, so the relative layout is part of the interface.
          cp -r ./* $out/lib/rimsort/

          install -D ./themes/default-icons/AppIcon_a.png \
            $out/share/icons/hicolor/512x512/apps/rimsort.png

          runHook postInstall
        '';

        postInstall = ''
          makeBinaryWrapper ${appEnv}/bin/python $out/bin/rimsort \
            --add-flags "-m app" \
            --chdir $out/lib/rimsort \
            --set PYTHONPATH $out/lib/rimsort \
            --set RIMSORT_DISABLE_UPDATER 1 \
            --set RIMSORT_LAUNCH_PREFIX ${steam-run}/bin/steam-run \
            --set RIMSORT_TODDS_PATH ${pkgs.todds}/bin/todds \
            ${lib.escapeShellArgs qtWrapperFlags}
        '';

        desktopItems = [
          (pkgs.makeDesktopItem {
            name = "io.github.rimsort.RimSort";
            desktopName = "RimSort";
            exec = "rimsort";
            icon = "rimsort";
            comment = finalAttrs.meta.description;
            categories = [ "Game" ];
            startupWMClass = "io.github.rimsort.RimSort";
          })
        ];

        passthru = {
          inherit appEnv;
          tests.pytest = pytestDrv;
        };

        meta = {
          description = "Free, open-source multi-platform mod manager and sorter for RimWorld";
          homepage = "https://github.com/RimSort/RimSort";
          license = licenses;
          mainProgram = "rimsort";
          # Linux-only launch plumbing (steam-run prefix, todds) and Qt
          # runtime libs
          platforms = [ "x86_64-linux" ];
        };
      });

      supported = lib.meta.availableOn pkgs.stdenv.hostPlatform appPkg;
    in
    {
      # meta.platforms refuses evaluation elsewhere; don't advertise outputs
      # that `nix flake check --all-systems` cannot evaluate.
      packages = lib.optionalAttrs supported {
        rimsort = appPkg;
        default = appPkg;
      };

      apps =
        let
          rimsort = {
            type = "app";
            program = "${appPkg}/bin/rimsort";
            meta.description = appPkg.meta.description;
          };
        in
        lib.optionalAttrs supported {
          inherit rimsort;
          default = rimsort;
        };

      checks.pytest = pytestDrv;
    };
}
