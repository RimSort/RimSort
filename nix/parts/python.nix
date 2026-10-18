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
      # the patchelf inputs and the RUNPATH entries for dlopen'd libraries
      # (qtRuntimeDeps); listed once so the two cannot drift.
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
      #    The PySide6 wheels link libQt6* and libpyside6/libshiboken6 across
      #    wheel boundaries (shiboken6, essentials, addons, webengine and pdf
      #    are separate store paths). Each wheel gets the wheels it depends on
      #    as auto-patchelf search paths, so those links land in RUNPATH and no
      #    LD_LIBRARY_PATH is needed. nixpkgs Qt is NOT handed to auto-patchelf:
      #    it would be baked into RUNPATH (and the closure) and load instead of
      #    the wheel's Qt on any minor skew.
      myOverrides =
        final: prev:
        let
          inherit (pkgs) lib;
          # Package dirs holding a wheel's shared libraries: libshiboken6 sits
          # in shiboken6/, libpyside6 in PySide6/, libQt6* in PySide6/Qt/lib.
          wheelLibDirs = drv: [
            "${drv}/${python.sitePackages}/shiboken6"
            "${drv}/${python.sitePackages}/PySide6"
            "${drv}/${python.sitePackages}/PySide6/Qt/lib"
          ];
          # Wheels each wheel links against; acyclic (essentials' QML plugins
          # for addons/webengine modules stay unresolved, RimSort loads no QML).
          wheelDeps = {
            pyside6-essentials = [ final.shiboken6 ];
            pyside6-addons = [
              final.shiboken6
              final.pyside6-essentials
            ];
            pyside6-webengine = [
              final.shiboken6
              final.pyside6-essentials
              final.pyside6-addons
            ];
            pyside6-pdf = [
              final.shiboken6
              final.pyside6-essentials
              final.pyside6-addons
            ];
          };
          # system libraries the wheels' Qt links (libxkbfile satisfies a
          # build-time link only); formerly propagated by nixpkgs Qt
          pysideSystemDeps =
            commonQtSystemLibs
            ++ (with pkgs; [
              cups
              fontconfig
              freetype
              harfbuzz
              krb5
              libgbm
              libxcb-cursor
              libxcb-image
              libxcb-keysyms
              libxcb-render-util
              libxcb-util
              libxcb-wm
              libxcomposite
              libxkbfile
              libxtst
              wayland
              zstd
            ]);
        in
        lib.mapAttrs (
          name: drv:
          drv.overrideAttrs (old: {
            # pyside_tool resolves PySide6/__init__.py through its symlink into
            # the pyside6 store path, which lacks the tool binaries (they ship
            # in essentials); the unresolved venv directory has both.
            postInstall =
              old.postInstall or ""
              + lib.optionalString (name == "pyside6-essentials") ''
                substituteInPlace $out/${python.sitePackages}/PySide6/scripts/pyside_tool.py \
                  --replace-fail "Path(ref_mod.__file__).resolve().parent" "Path(ref_mod.__file__).parent"
              '';
            buildInputs =
              old.buildInputs or [ ] ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux pysideSystemDeps;
            # Qt dlopens these (GL, dbus, X11/Wayland client libs); the
            # dlopen'ing library's RUNPATH is searched, so add them to all.
            runtimeDependencies = lib.optionals pkgs.stdenv.hostPlatform.isLinux qtRuntimeDeps;
            preFixup =
              old.preFixup or ""
              + lib.concatMapStrings (dir: ''
                addAutoPatchelfSearchPath ${dir}
              '') (lib.concatMap wheelLibDirs (wheelDeps.${name} or [ ]));
            # libQt6*/libpyside6/libshiboken6 still missing after the search
            # paths belong to the essentials QML plugins for modules shipped in
            # later wheels (see wheelDeps). The other entries belong to
            # optional plugins RimSort never loads (GTK3 platform theme, SQL
            # drivers, smart cards, speech). Anything else missing fails the
            # build.
            autoPatchelfIgnoreMissingDeps = [
              "libQt6*.so.6"
              "libpyside6.abi3.so.*"
              "libshiboken6.abi3.so.*"
              # GTK3 platform theme
              "libatk-1.0.so.0"
              "libcairo-gobject.so.2"
              "libcairo.so.2"
              "libgdk-3.so.0"
              "libgdk_pixbuf-2.0.so.0"
              "libgtk-3.so.0"
              "libpango-1.0.so.0"
              "libpangocairo-1.0.so.0"
              # Qt SQL drivers (Oracle, Firebird, Mimer, MySQL, ODBC, PostgreSQL)
              "libclntsh.so.*"
              "libfbclient.so.2"
              "libmimerapi.so"
              "libmysqlclient.so.*"
              "libodbc.so.2"
              "libpq.so.5"
              # QtNfc, QtTextToSpeech
              "libpcsclite.so.1"
              "libspeechd.so.2"
            ];
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

      # 7. Libraries Qt dlopens at runtime; baked into the wheels' RUNPATH via
      #    runtimeDependencies (see myOverrides).
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
        description = "uv2nix pipeline: python, workspace, pythonSet, appEnv, devEnv";
      };

      config.rimsortPython = {
        inherit
          python
          workspace
          pythonSet
          appEnv
          devEnv
          ;
      };
    };
}
