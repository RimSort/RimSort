"""
Standalone test for Steamworks GetAppDependencies.

Queries DLC dependency data for given PublishedFileIDs directly via Steamworks,
without running the full DB Builder pipeline.

Usage:
    python tests/utils/steam/steamworks/test_get_app_dependencies.py <pfid1> [pfid2] ...
    python tests/utils/steam/steamworks/test_get_app_dependencies.py --db <path> [--limit N] [--workers N]
"""

import json
import sys
import time
from multiprocessing import Lock, Pool
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path for imports
# Supports running as `python path/to/this_script.py` from any cwd
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.utils.generic import chunks  # noqa: E402
from app.utils.steam.availability import check_steam_available  # noqa: E402
from app.utils.steam.steamworks.wrapper import (  # noqa: E402
    OPERATION_INTERVAL,
    SteamworksAppDependenciesQuery,
    SteamworksInterface,
    _pool_init_worker,
)

# AppInfo resolves paths from __main__.__file__, which when running this
# standalone script points to tests/… instead of the project root.
# Compute the correct libs path relative to the known project root.
LIBS_PATH = str(_project_root / "libs")


def _parse_pfids(raw: list[str]) -> list[int]:
    """Parse PublishedFileIDs from CLI args."""
    pfids: list[int] = []
    for arg in raw:
        arg = arg.strip()
        if not arg.isdigit():
            print(f"  [skip] Skipping invalid pfid: {arg}")
            continue
        pfids.append(int(arg))
    return pfids


def print_result(pfid: int, deps: list[int]) -> None:
    """Print a single query result in a readable format."""
    resolved = [str(a) for a in deps if a in RIMWORLD_DLC_METADATA]
    unresolved = [str(a) for a in deps if a not in RIMWORLD_DLC_METADATA]
    print(f"  [{pfid}] AppID dependencies ({len(deps)} total):")
    if resolved:
        print(f"         RimWorld DLCs: {', '.join(resolved)}")
    if unresolved:
        print(f"         Other AppIDs:  {', '.join(unresolved)}")
    if not deps:
        print("         (none)")


# Inline minimal DLC metadata for display — mirrors RIMWORLD_DLC_METADATA
RIMWORLD_DLC_METADATA: dict[str, dict[str, str]] = {
    "871780": {"name": "RimWorld - Royalty"},
    "1149640": {"name": "RimWorld - Ideology"},
    "1826140": {"name": "RimWorld - Biotech"},
    "2384480": {"name": "RimWorld - Anomaly"},
}


def main() -> None:
    args = sys.argv[1:]
    db_path: str | None = None
    limit = 0
    workers = 1

    # Parse --db, --limit, and --workers flags, collect remaining as positional pfids
    remaining: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--db" and i + 1 < len(args):
            db_path = args[i + 1]
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--workers" and i + 1 < len(args):
            workers = int(args[i + 1])
            i += 2
        else:
            remaining.append(args[i])
            i += 1

    pfids: list[int] = []

    # Load from database if --db provided
    if db_path:
        with open(db_path) as f:
            db = json.load(f)
        all_pfids = [int(k) for k in db.get("database", {}) if len(k) > 8]
        all_pfids.sort()
        if limit > 0:
            all_pfids = all_pfids[:limit]
        pfids.extend(all_pfids)
        print(f"Loaded {len(all_pfids)} PfIDs from {db_path}")

    # Append positional pfids
    pfids.extend(_parse_pfids(remaining))

    pfids = list(dict.fromkeys(pfids))  # deduplicate preserving order
    if not pfids:
        print("Usage: python test_get_app_dependencies.py <pfid1> [pfid2] ...")
        print(
            "       python test_get_app_dependencies.py --db <path> [--limit N] [--workers N]"
        )
        print("Example: python test_get_app_dependencies.py 2892354813 2966480207")
        print(
            "         python test_get_app_dependencies.py --db steamDB.json --limit 100"
        )
        sys.exit(1)

    print(f"PublishedFileIDs to query: {pfids}")
    print()

    # 1. Check Steam availability
    print(f"Checking Steam availability (libs: {LIBS_PATH})...")
    if not check_steam_available(LIBS_PATH, status_callback=lambda m: print(f"  {m}")):
        print("[FAIL] Steam is not available. Aborting.")
        sys.exit(1)
    print("OK Steam available")
    print()

    total = len(pfids)
    print(f"PublishedFileIDs to query: {total}")
    print()

    start = time.monotonic()

    if workers > 1:
        # --- Parallel Pool path (mirrors webapi/wrapper.py) ---
        print(f"Using {workers} worker(s) with multiprocessing Pool")
        CHUNK_SIZE = max(
            1, total // (workers * 2)
        )  # 2 chunks per worker for load balancing
        pfid_chunks = list(chunks(pfids, limit=CHUNK_SIZE))
        queries = [
            SteamworksAppDependenciesQuery(
                pfid_or_pfids=[int(pfid) for pfid in chunk],
                interval=OPERATION_INTERVAL,
                _libs=LIBS_PATH,
            )
            for chunk in pfid_chunks
        ]
        print(f"Split into {len(queries)} chunks (size={CHUNK_SIZE})")

        pfids_appid_deps: dict[int, list[int]] = {}
        init_lock = Lock()
        with Pool(
            processes=workers,
            initializer=_pool_init_worker,
            initargs=(str(_project_root), LIBS_PATH, init_lock),
        ) as pool:
            for i, result in enumerate(
                pool.imap_unordered(SteamworksAppDependenciesQuery.run, queries)
            ):
                if result is not None:
                    pfids_appid_deps.update(result)
                print(
                    f"  Chunk {i + 1}/{len(queries)} completed ({len(result or [])} results)"
                )

        results = pfids_appid_deps
        # Pool workers already handle cleanup; nothing to join
        completed = True

    else:
        # --- Sequential single-process path ---
        print(f"Initializing Steamworks interface for {total} pfid(s)...")
        si = SteamworksInterface(callbacks=True, callbacks_total=total, _libs=LIBS_PATH)
        if si.steam_not_running:
            print("[FAIL] Steamworks initialization failed. Aborting.")
            sys.exit(1)
        print("OK Steamworks interface ready")
        print()

        # Register callback & track fired pfids
        fired_pfids: set[int] = set()

        def _tracking_callback(*args: Any, **kwargs: Any) -> None:
            if args and hasattr(args[0], "publishedFileId"):
                fired_pfids.add(int(args[0].publishedFileId))
            si._cb_app_dependencies_result_callback(*args, **kwargs)

        si.steamworks.Workshop.SetGetAppDependenciesResultCallback(_tracking_callback)

        # 4. Query each pfid sequentially — wait for each callback before proceeding.
        verbose = total <= 20
        print(f"Querying {total} pfid(s) (waiting for each callback)...")
        LOG_INTERVAL = max(1, total // 20) if not verbose else 1
        for idx, pfid in enumerate(pfids, 1):
            if verbose or idx % LOG_INTERVAL == 0 or idx == total:
                print(
                    f"  [{idx}/{total}] GetAppDependencies({pfid})", end="", flush=True
                )
            si.steamworks.Workshop.GetAppDependencies(pfid)
            # Pump callbacks until this pfid's result arrives (up to 10s)
            waited = 0
            while waited < 100:  # 100 * 0.1s = 10s per query
                si.steamworks.run_callbacks()
                if pfid in fired_pfids or pfid in si.get_app_deps_query_result:
                    break
                time.sleep(0.1)
                waited += 1
            else:
                if verbose:
                    print(" [timeout]")
            if verbose:
                print()

        # 5. Wait for all callbacks
        print()
        print("Waiting for Steamworks callbacks...")
        completed = si._wait_for_callbacks(timeout=60)
        if si.steamworks_thread.is_alive() and si.end_callbacks:
            si.steamworks_thread.join(timeout=5)

        results = si.get_app_deps_query_result

        # Cleanup
        print()
        print("Cleaning up...")
        if si.steamworks_thread.is_alive():
            si.steamworks_thread.join(timeout=2)
        si.steamworks.unload()

    elapsed = time.monotonic() - start

    # 6. Print results
    print()
    deps_found = len(results.keys())
    print(f"Total time: {elapsed:.1f}s")
    print(f"Throughput: {total / elapsed:.2f} pfids/sec")
    print(f"Non-empty deps stored: {deps_found}/{total}")
    print(
        f"Estimated full DB (55k) with {workers} worker(s): "
        f"{(55000 * elapsed / total) / 60:.1f} min"
    )
    if total > 20:
        all_dlc_deps = sum(
            1 for d in results.values() if any(a in RIMWORLD_DLC_METADATA for a in d)
        )
        print(f"  Mods with known DLC deps: {all_dlc_deps}")
        print(
            f"  Mods with unknown AppID deps: {sum(1 for d in results.values() if any(a not in RIMWORLD_DLC_METADATA for a in d))}"
        )
        print()
        if results:
            print("  Sample results (first 20):")
            for pfid in list(results.keys())[:20]:
                deps = results.get(pfid, [])
                print_result(pfid, deps)
    else:
        print()
        for pfid in pfids:
            deps = results.get(pfid, [])
            print_result(pfid, deps)

    if not completed:
        print()
        print("[TIMEOUT] Some chunks timed out.")

    print("Done.")


if __name__ == "__main__":
    main()
