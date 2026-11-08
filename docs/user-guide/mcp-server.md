---
title: MCP Server
nav_order: 9
layout: default
parent: User Guide
permalink: user-guide/mcp-server
---
# MCP Server

{: .no_toc}

RimSort ships a [Model Context Protocol](https://modelcontextprotocol.io/) server so AI agents (Cursor, Claude Desktop, and other MCP clients) can inspect your installed RimWorld mods, validate a load order, and read or write `ModsConfig.xml` through structured tool calls.

## Table of Contents

{: .no_toc .text-delta }

1. TOC
{:toc}

## Overview

The MCP server reads the same settings, metadata databases and mod folders the graphical application uses. It runs headlessly — no window is created — and speaks JSON-RPC over stdio, which is the transport MCP clients use for local servers.

It is read-mostly by design: analysis tools never touch disk, and the one write tool refuses to save a list it could not validate.

## Starting the server

From a release build:

```bash
./RimSort --mcp
```

On Windows:

```bash
RimSort.exe --mcp
```

From source:

```bash
uv run python -m app --mcp
```

### Instance selection

By default the server binds to the instance that is currently selected in the GUI. To serve a different instance, pass its name:

```bash
uv run python -m app --mcp --instance "My Second Instance"
```

An unknown instance name exits with code `2` and lists the configured instances on stderr.

### Logging

`stdout` is reserved for JSON-RPC frames. All logs go to stderr and to a log file in RimSort's log directory:

```
RimSortMCPServer.log
```

That separation is what allows the server to be launched from an MCP client, which reads everything on stdout as protocol traffic.

## Client configuration

Add the server to your MCP client's configuration. For Cursor, `.cursor/mcp.json` in this repository already contains:

```json
{
  "mcpServers": {
    "rimsort": {
      "command": "uv",
      "args": ["run", "python", "-m", "app", "--mcp"],
      "env": { "QT_QPA_PLATFORM": "offscreen" }
    }
  }
}
```

For Claude Desktop, the same block belongs under `mcpServers` in `claude_desktop_config.json`.

## Tools

| Tool | Purpose |
|------|---------|
| `get_instance_status` | Instance name, detected game version, configured paths, mod counts, duplicate package IDs |
| `search_installed_mods` | Search local and Workshop mods by keyword, supported version and active state |
| `get_mod_details` | Full metadata and merged rules for specific package IDs |
| `get_active_modlist` | The ordered `ModsConfig.xml` list, plus package IDs referenced there but not installed |
| `analyze_and_sort_modlist` | Validate a candidate list and return RimSort's optimal load order |
| `apply_active_modlist` | Back up and write a validated list to `ModsConfig.xml` |
| `refresh_metadata_cache` | Re-scan the filesystem and `ModsConfig.xml` |

### `search_installed_mods`

Matches the query against the mod's name, package ID, authors and description. Every whitespace-separated token must match, so `"vanilla framework"` narrows rather than widens.

Results are capped at 200 records to protect the agent's context window. When a query matches more, the final element is a `{"truncated": true, ...}` marker with the true match count. Descriptions are omitted unless `include_description=True`, and are truncated to 500 characters when included.

### `analyze_and_sort_modlist`

Takes a candidate list of package IDs and returns:

- `sorted_package_ids` — the load order RimSort would produce, using your configured sorting algorithm and the Community Rules / Steam Workshop databases
- `missing_installed_dependencies` — dependencies on disk that were not in the requested list
- `missing_uninstalled_dependencies` — dependencies that are not installed at all, with Workshop IDs where they can be resolved
- `incompatibilities`, `version_mismatches`, `warnings`, `errors`

The base game is always added if omitted. Expansions are **not** added unless they are already enabled in `ModsConfig.xml`, so asking for a sort never silently re-enables a DLC you turned off.

Circular dependencies are returned as a structured `circular_dependency` error with the detected loops, instead of blocking on a dialog.

### `apply_active_modlist`

Writes `ModsConfig.xml` for the bound instance. With `auto_sort=True` (the default) the list is sorted first.

The write is refused — with the file left untouched — when:

- a requested package ID is not installed
- the dependency graph contains a cycle
- the instance has no config folder configured

With `create_backup=True` (the default) the previous file is copied to `backups/mods_config/ModsConfig_<timestamp>.xml` first.

## Safety notes

- The server operates on the mod list, not on your save files.
- `analyze_and_sort_modlist` is side-effect free; use it to preview a change.
- RimSort itself should not be running when you write a mod list, so the GUI cannot overwrite the MCP server's change on exit.

## Troubleshooting

##### **The client reports no tools**

Check that stdin is being piped to the process and that the client launches it with `uv run python -m app --mcp` from the repository root. Running `--mcp` from a release build requires the build to include the `mcp` dependency.

##### **An instance reports zero mods**

`get_instance_status` echoes the resolved `game_folder`, `config_folder`, `local_folder` and `workshop_folder`. Zero mods almost always means those paths are unset or wrong for the bound instance — configure them in the GUI first, then call `refresh_metadata_cache`.
