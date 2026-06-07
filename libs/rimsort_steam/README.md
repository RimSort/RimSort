# rimsort_steam

Minimal Steamworks SDK wrapper for RimSort. Exposes only the ISteamUGC functions
needed by RimSort (subscribe, unsubscribe, download, app dependencies) via
extern "C" linkage for consumption by Python ctypes.

This replaces the previous SteamworksPy submodule with a focused, maintainable
~250 LOC C++ shim.

## Prerequisites

1. **Steamworks SDK** -- download from https://partner.steamgames.com (free
   account required). Extract the archive somewhere on your system.

2. Set the `STEAMWORKS_SDK_PATH` environment variable to the extracted SDK root
   directory (the folder containing `public/` and `redistributable_bin/`).

3. **Build tools:**
   - macOS: Xcode Command Line Tools (`xcode-select --install`)
   - Linux: `g++` (any version supporting C++11)
   - Windows: Visual Studio 2022 Build Tools with the C++ desktop workload

## Building

### macOS / Linux

```bash
cd libs/rimsort_steam
export STEAMWORKS_SDK_PATH=/path/to/sdk
make
```

Produces `rimsort_steam.dylib` (macOS) or `rimsort_steam.so` (Linux).

### Windows

```cmd
cd libs\rimsort_steam
set STEAMWORKS_SDK_PATH=C:\path\to\sdk
build_windows.bat
```

Produces `rimsort_steam.dll`.

## Pre-built binaries

Pre-built binaries are committed to `libs/` for convenience. Most developers do
not need to build from source -- the pre-built libraries are loaded at runtime
by the Python wrapper in `app/utils/steam/steamworks/`.

Only rebuild if you need to update the native shim (e.g., to expose additional
Steamworks API surface).

## API surface

See the project spec (`docs/specs/steamworkspy-replacement.md`) for the full
API surface documentation, including ctypes struct layouts and callback
signatures.
