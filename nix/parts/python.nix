# uv2nix pipeline: uv.lock is the single source of truth for the Python world.
# Exposes the whole pipeline as the perSystem option `rimsortPython` so other
# parts consume it without repeating the build (DRY).
{ lib, inputs, ... }:
{
  perSystem =
    { pkgs, ... }:
    let
      # Explicit pin; pyproject requires-python is ==3.14.*
      python = pkgs.python314;

      # 1. Load workspace (pyproject.toml + uv.lock at eval time)
      workspace = inputs.uv2nix.lib.workspace.loadWorkspace {
        workspaceRoot = ../..;
      };

      # 2. Overlay: uv.lock -> derivations (wheels preferred, house default;
      #    uv does not lock build systems, so sdists are the fallback path)
      uvLockedOverlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      # System libraries the PySide6 wheel's Qt links or dlopens. Shared by
      # the build-time patchelf inputs (below) and the runtime wrapper/shell
      # environments (qtRuntimeDeps); listed once so the two cannot drift.
      commonQtSystemLibs = with pkgs; [
        alsa-lib
        libxkbcommon
        nspr
        nss
        pulseaudio
        libxdamage
        libxrandr
      ];

      # 3. Last-resort per-package fixes. uv2nix ships no bundled overrides by
      #    design; extend here (with a comment per entry) when a locked package
      #    needs one. Keep it near-empty. Legacy setuptools builds (steam,
      #    steamfiles, protobuf3-to-dict) are handled in pyproject.toml via
      #    [tool.uv.extra-build-dependencies], which uv2nix picks up here.
      #
      #    The PySide6 wheels bundle a Qt QML plugin tree whose .so files link
      #    libQt6* by SONAME; auto-patchelf cannot resolve those inside the
      #    wheel, so hand patchelf the Qt libs at BUILD time only. RimSort uses
      #    no QML, so any minor-version skew against nixpkgs Qt is irrelevant:
      #    at runtime the wheel's own Qt wins via $ORIGIN RUNPATH and the
      #    wrapper's LD_LIBRARY_PATH.
      myOverrides =
        _final: prev:
        let
          inherit (pkgs) lib;
          # Qt libs so auto-patchelf can resolve libQt6* SONAMEs inside the
          # bundled QML plugin tree (build-time only, like the nixpkgs package)
          pysideQtDeps = with pkgs.qt6; [
            qt5compat
            qtbase
            qtdeclarative
            qtquick3d
            qtquicktimeline
            qtsvg
            qtwayland
          ];
          # system libraries the QML/WebEngine plugins reference
          # (libxkbfile satisfies a build-time link only)
          pysideSystemDeps = commonQtSystemLibs ++ [ pkgs.libxkbfile ];
        in
        lib.mapAttrs (
          _name: drv:
          drv.overrideAttrs (old: {
            buildInputs =
              old.buildInputs or [ ]
              ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux (pysideQtDeps ++ pysideSystemDeps);
            # libraries, not Qt apps: build inputs trigger qtPreHook
            dontWrapQtApps = true;
            # The Essentials/Addons wheels split the Qt libraries between them
            # (addons wants libQt6Network, essentials wants libQt6WebEngineCore),
            # so cross-wheel references cannot be build inputs without a cycle.
            # Likewise exotic Qt SQL drivers (oracle/mimer) stay unresolved.
            # Runtime resolution happens via $ORIGIN RUNPATH + the wrapper's
            # LD_LIBRARY_PATH (qtRoot below).
            autoPatchelfIgnoreMissingDeps = true;
          })
        ) (lib.filterAttrs (name: _v: lib.strings.hasPrefix "pyside6" name) prev);

      # 4. Python package set
      pythonSet =
        (pkgs.callPackage inputs.pyproject-nix.build.packages { inherit python; }).overrideScope
          (
            lib.composeManyExtensions [
              inputs.pyproject-build-systems.overlays.wheel
              uvLockedOverlay
              myOverrides
            ]
          );

      # 5. Runtime env: production deps only (default groups)
      appEnv = pythonSet.mkVirtualEnv "rimsort-env" workspace.deps.default;

      # 6. Dev env: dev group too (pytest, pytest-qt, mypy + stubs, pyright,
      #    ruff, ...). Doubles as the lint hook environment (git-hooks binPath).
      devEnv = pythonSet.mkVirtualEnv "rimsort-dev-env" workspace.deps.all;

      # 7. Qt runtime plumbing shared by the app wrapper and the dev shell:
      #    the wheel's own Qt (plugins + libs) plus the system libraries it
      #    dlopens at runtime. Function-based so each env (appEnv, devEnv)
      #    resolves against its own site-packages.
      qtRootFor = env: "${env}/lib/${python.libPrefix}/site-packages/PySide6/Qt";
      qtPluginPathFor = env: "${qtRootFor env}/plugins/platforms";
      qtLdLibraryPathFor = env: "${qtRootFor env}/lib:${pkgs.lib.makeLibraryPath qtRuntimeDeps}";
      qtRuntimeDeps =
        commonQtSystemLibs
        ++ (with pkgs; [
          dbus
          fontconfig
          freetype
          glib
          libGL
          wayland
          libx11
          libxcb
          libxcursor
          libxext
          libxfixes
          libxi
          libxrender
        ]);
    in
    {
      options.rimsortPython = lib.mkOption {
        type = lib.types.raw;
        internal = true;
        description = "uv2nix pipeline: python, workspace, pythonSet, appEnv, devEnv, qtRootFor, qtPluginPathFor, qtLdLibraryPathFor, qtRuntimeDeps";
      };

      config.rimsortPython = {
        inherit
          python
          workspace
          pythonSet
          appEnv
          devEnv
          qtRootFor
          qtPluginPathFor
          qtLdLibraryPathFor
          qtRuntimeDeps
          ;
      };
    };
}
