# Don't create debug packages for Nuitka-compiled binaries
%global debug_package %{nil}

# Filter out auto-detected dependencies for bundled Nuitka libraries
# These libraries are bundled in /usr/share/rimsort/ and should not be system requirements
%global __requires_exclude ^(libcrypto-.*\\.so.*|libssl-.*\\.so.*|libgfortran-.*\\.so.*|libjpeg-.*\\.so.*|liblzma-.*\\.so.*|libopenjp2-.*\\.so.*|libpcre-.*\\.so.*|libquadmath-.*\\.so.*|libsharpyuv-.*\\.so.*|libssh2-.*\\.so.*|libtiff-.*\\.so.*|libwebp-.*\\.so.*|libwebpdemux-.*\\.so.*|libwebpmux-.*\\.so.*|libxcb-.*\\.so.*|libXau-.*\\.so.*|libgit2-.*\\.so.*|libscipy_openblas.*\\.so.*|libtiff\\.so\\.5.*|libQt6EglFsKmsGbmSupport\\.so.*|libsteam_api\\.so.*)$

# Also filter out auto-detected provides for bundled libraries (they're private to this app)
%global __provides_exclude ^(libcrypto-.*\\.so.*|libssl-.*\\.so.*|libgfortran-.*\\.so.*|libjpeg-.*\\.so.*|liblzma-.*\\.so.*|libopenjp2-.*\\.so.*|libpcre-.*\\.so.*|libquadmath-.*\\.so.*|libsharpyuv-.*\\.so.*|libssh2-.*\\.so.*|libtiff-.*\\.so.*|libwebp-.*\\.so.*|libwebpdemux-.*\\.so.*|libwebpmux-.*\\.so.*|libxcb-.*\\.so.*|libXau-.*\\.so.*|libgit2-.*\\.so.*|libscipy_openblas.*\\.so.*|libtiff\\.so\\.5.*|libsteam_api\\.so.*)$

Name:           rimsort
Version:        %{?version}%{!?version:1.0.63}
Release:        1%{?dist}
Summary:        Mod manager for RimWorld

License:        AGPL-3.0-only
URL:            https://rimsort.github.io/RimSort/
Source0:        https://github.com/RimSort/RimSort/archive/v%{version}/%{name}-%{version}.tar.gz

ExclusiveArch:  x86_64

BuildRequires:  git
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  python3.12
BuildRequires:  python3.12-devel
BuildRequires:  uv
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib

Requires:       glibc

%description
RimSort is an open source mod manager for the video game RimWorld.
Built from the ground up to be reliable and community managed.

This package contains a standalone Nuitka-compiled binary with all
dependencies bundled.

%prep
%autosetup -n RimSort-%{version}

# Generate version.xml (required by the build process)
# Format matches GitHub Actions workflow
cat > version.xml << 'EOF'
<version>
  <version>%{version}</version>
  <major>%(echo %{version} | cut -d. -f1)</major>
  <minor>%(echo %{version} | cut -d. -f2)</minor>
  <patch>%(echo %{version} | cut -d. -f3)</patch>
  <increment>1</increment>
  <commit>%(git rev-parse HEAD 2>/dev/null || echo "unknown")</commit>
  <tag>v%{version}</tag>
</version>
EOF

%build
# Sync dependencies using uv
uv sync --locked --no-dev --group build

# Build using the existing distribute.py script
# Skip git submodule init (already in tarball), use pre-built SteamworksPy libs, download todds
uv run --frozen python ./distribute.py --product-version='%{version}.1' --skip-submodules

%install
# Create directory structure
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/metainfo
install -d %{buildroot}%{_datadir}/icons/hicolor/256x256/apps

# Install the entire Nuitka build output to /usr/share/rimsort
cp -pr build/app.dist/* %{buildroot}%{_datadir}/%{name}/

# Create wrapper script in /usr/bin
cat > %{buildroot}%{_bindir}/%{name} << 'EOF'
#!/bin/bash
exec %{_datadir}/%{name}/RimSort "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/%{name}

# Install desktop file
desktop-file-install \
    --dir=%{buildroot}%{_datadir}/applications \
    data/io.github.rimsort.RimSort.desktop

# Install AppStream metadata
install -Dpm 0644 data/io.github.rimsort.RimSort.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/io.github.rimsort.RimSort.metainfo.xml

# Install application icon
install -Dpm 0644 themes/default-icons/AppIcon_a.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/io.github.rimsort.RimSort.png

%check
# Validate desktop file
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.rimsort.RimSort.desktop

# Validate AppStream metadata
appstream-util validate-relax --nonet %{buildroot}%{_datadir}/metainfo/io.github.rimsort.RimSort.metainfo.xml

%files
%license LICENSE.md
%doc README.md

# Main executable wrapper
%{_bindir}/%{name}

# Application directory with all bundled content
%{_datadir}/%{name}/

# Desktop integration
%{_datadir}/applications/io.github.rimsort.RimSort.desktop
%{_datadir}/metainfo/io.github.rimsort.RimSort.metainfo.xml
%{_datadir}/icons/hicolor/256x256/apps/io.github.rimsort.RimSort.png

%post
# Update desktop database
/usr/bin/update-desktop-database &> /dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &> /dev/null || :

%postun
# Update desktop database
/usr/bin/update-desktop-database &> /dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &> /dev/null || :

%changelog
* Fri Dec 20 2025 Anten Skrabec <cebarks@gmail.com> - 1.0.63-1
- Initial RPM packaging for COPR
