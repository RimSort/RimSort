# Packaged app + checks. Sources are filesets of the flake's own tree with
# the SteamworksPy submodule overlaid from fetchFromGitHub at the repo's
# pinned rev (flake git-tree sources drop gitlink contents and SteamworksPy is
# a runtime import). Ships the desktop item with the self-updater disabled.
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
{
  lib,
  inputs,
  withSystem,
  ...
}:
{
  perSystem =
    { config, pkgs, ... }:
    let
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

      # Release parity: the default identifies the source
      # revision, a release injects the real tag:
      #   RIMSORT_VERSION=v1.2.3 nix build --impure
      # (builtins.getEnv returns "" in pure evaluation)
      commit = inputs.self.rev or inputs.self.dirtyRev or "unknown";
      version =
        let
          env = builtins.getEnv "RIMSORT_VERSION";
          rev = inputs.self.shortRev or inputs.self.dirtyShortRev or null;
        in
        if env != "" then
          env
        else if rev != null then
          "0.0.0+git.${rev}"
        else
          "0.0.0+dev";

      # Flake git-tree sources drop gitlink contents, but SteamworksPy is a
      # runtime import (from steamworks import STEAMWORKS resolves against
      # it). Its contents are fetched at the repo's own pinned revision and
      # overlaid into submodules/ (mkSrc below); steamfiles is not fetched:
      # it comes from uv.lock. Update the pin when the submodule moves (CI
      # compares it with the gitlink).
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
      # Only what the app reads at runtime (AppInfo resolves these as
      # siblings of app/; SteamworksPy reads steam_appid.txt from the cwd), so
      # doc or tooling edits do not rebuild the package.
      runtimeFiles = lib.fileset.unions [
        ../../app
        ../../libs
        ../../locales
        ../../themes
        ../../LICENSE.md
        ../../setup_steam_recovery_script.js
        ../../setup_web_channel_script.js
        ../../steam_appid.txt
      ];
      testFiles = lib.fileset.unions [
        runtimeFiles
        ../../tests
        ../../pyproject.toml
        ../../translation_helper.py
      ];
      mkSrc =
        name: fileset:
        pkgs.runCommand name { } ''
          cp -r ${
            lib.fileset.toSource {
              root = ../..;
              inherit fileset;
            }
          } $out
          chmod -R u+w $out
          mkdir -p $out/submodules
          for sub in ${submoduleSrcs}/*; do
            cp -r "$sub/." "$out/submodules/$(basename "$sub")"
          done
          chmod -R u+w $out/submodules
        '';
      src = mkSrc "rimsort-src" runtimeFiles;
      testSrc = mkSrc "rimsort-test-src" testFiles;

      # Launch prefix exported to the app via RIMSORT_LAUNCH_PREFIX (game +
      # SteamCMD run inside the Steam runtime FHS env)
      steam-run = (pkgs.steam.override { privateTmp = false; }).run;

      # PySide6 wheels bundle their own Qt; it still dlopens system libs.
      # LD_LIBRARY_PATH is required: libQt6* links across the separate wheel
      # store paths are left unresolved in RUNPATH (see python.nix).
      qtLdLibraryPath = qtLdLibraryPathFor appEnv;
      qtWrapperFlags = lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        "--set"
        "QT_QPA_PLATFORM_PLUGIN_PATH"
        (qtPluginPathFor appEnv)
        "--prefix"
        "LD_LIBRARY_PATH"
        ":"
        qtLdLibraryPath
      ];

      # The game and SteamCMD must resolve libraries from the Steam runtime,
      # not RimSort's Qt closure: strip exactly the entries the wrapper
      # prepended and keep anything else (the user's own value, or one set
      # through RimSort's game environment variables).
      launchPrefix = pkgs.writeShellApplication {
        name = "rimsort-launch";
        text = ''
          case "''${LD_LIBRARY_PATH-}" in
          "${qtLdLibraryPath}") unset LD_LIBRARY_PATH ;;
          "${qtLdLibraryPath}":*) export LD_LIBRARY_PATH="''${LD_LIBRARY_PATH#"${qtLdLibraryPath}":}" ;;
          esac
          unset QT_QPA_PLATFORM_PLUGIN_PATH
          exec ${steam-run}/bin/steam-run "$@"
        '';
      };

      # Tests run against the shipped (unpatched) runtime files plus the
      # tests. Only the network-dependent tests are skipped, like the
      # nixpkgs package's disabledTestPaths; the hardcoded-executable tests
      # nixpkgs disables pass here because our sources are never patched.
      pytestDrv = pkgs.stdenv.mkDerivation {
        # No version: a rev-based one would rerun the suite on every commit,
        # even when the test inputs (testSrc, devEnv) are unchanged.
        name = "rimsort-tests";
        src = testSrc;

        nativeBuildInputs = [ devEnv ];

        dontBuild = true;
        doCheck = true;

        preCheck = ''
          export HOME=$(mktemp -d)
          export QT_QPA_PLATFORM=offscreen
          # Same library path the app wrapper and dev shell use: cross-wheel
          # libQt6* links are resolved only through it.
          export LD_LIBRARY_PATH=${qtLdLibraryPathFor devEnv}
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
          # The store is read-only: without precompiled bytecode every start
          # recompiles the whole app in memory.
          ${appEnv}/bin/python -m compileall -q $out/lib/rimsort/app $out/lib/rimsort/submodules

          # AppInfo reads the displayed version from version.xml (the release
          # workflow writes it for the other builds)
          cat > $out/lib/rimsort/version.xml <<EOF
          <version>
            <version>${version}</version>
            <commit>${commit}</commit>
          </version>
          EOF

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
            --set RIMSORT_LAUNCH_PREFIX ${lib.getExe launchPrefix} \
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
      # Build the packaged app on every check run: a PR that breaks the
      # wrapper, filesets, or desktop metadata must fail here rather than
      # first surfacing in the post-merge cache publication.
      checks.package = config.packages.rimsort;
    };

  # For NixOS / home-manager configurations:
  #   nixpkgs.overlays = [ rimsort.overlays.default ];
  flake.overlays.default =
    _final: prev:
    withSystem prev.stdenv.hostPlatform.system (
      { config, ... }:
      {
        inherit (config.packages) rimsort;
      }
    );
}
