# Developer tooling with no nixpkgs equivalent, so the same gates can run
# inside Nix that CI runs outside it.
#
# Today: jscpd (copy/paste detection). jscpd 5.x is a Rust binary published as
# platform-specific npm packages rather than a nixpkgs attribute, and the
# `npx`-installed copy cannot exec on NixOS because it carries a
# /lib64/ld-linux-x86-64.so.2 interpreter that does not exist there. Fetching
# the same pinned tarball and pointing the loader at Nix's glibc makes the
# identical version run under Nix, in the pre-commit hook and in CI.
{ lib, ... }:
{
  perSystem =
    { pkgs, ... }:
    let
      # Keep in lockstep with the jscpd version the justfile pins for
      # non-Nix developers (`just jscpd` -> npx --yes jscpd@<version>).
      version = "5.3.0";

      jscpdPkgs = {
        x86_64-linux = {
          name = "jscpd-linux-x64-gnu";
          hash = "sha256-hutkqIus0cMUl9nXQg6vb2DBMCqpSlqce5SNr3S5TaM=";
        };
        aarch64-linux = {
          name = "jscpd-linux-arm64-gnu";
          hash = "sha256-MXBYWqQpd7B6FGy8T1fpqzZsSTrv8bfr8jtiFAkk5XQ=";
        };
      };

      systemKey = pkgs.stdenv.hostPlatform.system;
      jscpdSupported = builtins.hasAttr systemKey jscpdPkgs;

      jscpdDrv =
        if jscpdSupported then
          let
            arch = jscpdPkgs.${systemKey};
            inherit (arch) hash;
          in
          pkgs.stdenv.mkDerivation {
            pname = arch.name;
            inherit version;

            src = pkgs.fetchurl {
              url = "https://registry.npmjs.org/${arch.name}/-/" + "${arch.name}-${version}.tgz";
              inherit hash;
            };

            nativeBuildInputs = [ pkgs.patchelf ];

            dontConfigure = true;
            # No build step: the tarball ships a prebuilt executable.
            dontBuild = true;

            installPhase = ''
              runHook preInstall

              mkdir -p "$out/bin"
              # Nix's unpack strips the npm `package/` prefix.
              cp bin/jscpd "$out/bin/jscpd"
              cp LICENSE "$out/LICENSE"
              chmod +x "$out/bin/jscpd"

              # Replace the foreign interpreter (and give it a glibc rpath) so
              # the binary runs against Nix's glibc instead of /lib64.
              patchelf \
                --set-interpreter ${pkgs.stdenv.cc.bintools.dynamicLinker} \
                --set-rpath ${lib.makeLibraryPath [ pkgs.glibc ]} \
                "$out/bin/jscpd"

              runHook postInstall
            '';

            meta = {
              description = "Copy/paste detector (copy-paste detection)";
              longDescription = ''
                Detects duplicated code across a project. Used as RimSort's
                duplication gate: CI requires 0% duplication.
              '';
              mainProgram = "jscpd";
              platforms = builtins.attrNames jscpdPkgs;
              license = pkgs.lib.licenses.mit;
            };
          }
        else
          null;
    in
    {
      options.rimsortTools = lib.mkOption {
        type = lib.types.raw;
        internal = true;
        description = "Developer tooling provided by the flake (jscpdDrv, jscpdSupported)";
      };

      config.rimsortTools = {
        inherit jscpdDrv jscpdSupported;
      };

      # Exposed so it can be run directly: `nix run .#jscpd -- .`
      config.packages = lib.optionalAttrs jscpdSupported { jscpd = jscpdDrv; };
    };
}
