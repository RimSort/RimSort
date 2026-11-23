---
title: MCP Server
nav_order: 9
layout: default
parent: User Guide
permalink: user-guide/mcp-server
---
# MCP Server

{: .no_toc}

RimSort ships a [Model Context Protocol](https://modelcontextprotocol.io/) server so any MCP client can inspect your installed RimWorld mods, validate a load order, and read or write `ModsConfig.xml` through structured tool calls.

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

The server is a normal MCP stdio process. Any client that can launch a local command and speak JSON-RPC on that process's stdin and stdout can use it. The snippets below differ only in where each client stores the config and which key wraps the server entry.

From a source checkout the launch command is always `uv`, with these arguments:

```json
["run", "python", "-m", "app", "--mcp"]
```

`uv` must be on the `PATH` the client uses. The process working directory must be the repository root, because `python -m app` is imported from that checkout. Clients that document a working-directory field (`cwd` below) should set it to that directory. `QT_QPA_PLATFORM=offscreen` stops Qt from opening a window.

A release build uses the packaged executable instead of `uv`, with the same `--mcp` and `--instance` arguments shown under Starting the server (`./RimSort` or `RimSort.exe`).

To serve an instance other than the one selected in the GUI, append the instance name to `args`:

```json
["run", "python", "-m", "app", "--mcp", "--instance", "My Second Instance"]
```

The configs below omit `--instance`, so they bind the active instance. An unknown name still exits with code `2`.

### Cursor

Cursor reads a top-level `mcpServers` object from `.cursor/mcp.json` in a project, or from `~/.cursor/mcp.json` for every project. See [MCP in Cursor](https://cursor.com/docs/mcp).

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

### Claude Desktop

The same `mcpServers` block belongs in `claude_desktop_config.json`. [Claude Desktop's local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers) places that file at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

Settings → Developer → Edit Config opens the file.

### Gemini CLI

Gemini CLI reads a top-level `mcpServers` object from `~/.gemini/settings.json` for every session, or from `.gemini/settings.json` in a project (the project file overrides the user file). A stdio server sets `command`. `args`, `env`, and `cwd` are optional. See [MCP servers with Gemini CLI](https://geminicli.com/docs/tools/mcp-server/).

```json
{
  "mcpServers": {
    "rimsort": {
      "command": "uv",
      "args": ["run", "python", "-m", "app", "--mcp"],
      "env": { "QT_QPA_PLATFORM": "offscreen" },
      "cwd": "/path/to/RimSort"
    }
  }
}
```

### Codex CLI

OpenAI Codex reads `~/.codex/config.toml`. A trusted project can override it with `.codex/config.toml`; Codex skips project layers until the project is trusted. A stdio server is a table named `[mcp_servers.<name>]` with `command` and optional `args`, `env`, and `cwd`. See [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) and the [`mcp_servers` reference](https://learn.chatgpt.com/docs/config-file/config-reference).

```toml
[mcp_servers.rimsort]
command = "uv"
args = ["run", "python", "-m", "app", "--mcp"]
env = { "QT_QPA_PLATFORM" = "offscreen" }
cwd = "/path/to/RimSort"
```

### VS Code

GitHub Copilot in VS Code uses the VS Code MCP format. Workspace config is `.vscode/mcp.json`. The user-profile file is opened with the command **MCP: Open User Configuration**; its path is not a fixed location in the docs. Both files use a top-level `servers` object, and a local server sets `"type": "stdio"`. In a workspace, `cwd` defaults to the workspace folder. A user-profile entry is not tied to one folder, so set `cwd` there to the checkout. See the [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

```json
{
  "servers": {
    "rimsort": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "app", "--mcp"],
      "env": { "QT_QPA_PLATFORM": "offscreen" }
    }
  }
}
```

VS Code forwards that entry to the Copilot agent session. In Copilot Chat, switch the mode to Agent and enable the RimSort tools. Copilot's separate portable files (workspace `.mcp.json`, or `~/.copilot/mcp-config.json`) use `mcpServers` instead of `servers` and take `command` plus `args` without `type`.

### Windsurf

Cascade reads `mcpServers` from `mcp_config.json`. The [Windsurf Cascade MCP guide](https://docs.devin.ai/windsurf/plugins/cascade/mcp) puts that file at `~/.config/devin/mcp_config.json` on macOS and Linux (`$XDG_CONFIG_HOME/devin/mcp_config.json` when `XDG_CONFIG_HOME` is set) and at `%AppData%/devin/mcp_config.json` on Windows. Open MCP config file in Cascade's MCP menu opens the file for your install. A stdio entry is `command`, `args`, and `env`. The guide does not document a working-directory field, so start the client from the RimSort checkout (or point `command` at a release binary and pass `--mcp`).

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

The editor's own discovery file is separate: `~/.codeium/windsurf/mcp_config.json` (Next builds use `~/.codeium/windsurf-next/mcp_config.json`). It uses the same `mcpServers` shape.

### Zed

Zed stores local servers under `context_servers` in the settings file opened by `zed: open settings file`. Each entry has `command`, `args`, and `env`. See [Model Context Protocol in Zed](https://zed.dev/docs/ai/mcp). The settings page does not document a working-directory key. If `uv run python -m app` cannot see this checkout, point `command` at a release binary and pass `--mcp`.

```json
{
  "context_servers": {
    "rimsort": {
      "command": "uv",
      "args": ["run", "python", "-m", "app", "--mcp"],
      "env": { "QT_QPA_PLATFORM": "offscreen" }
    }
  }
}
```

### Other stdio clients

A client that is not listed above still works when it can start a process and use stdio rather than HTTP or SSE. Give it the same `command`, `args`, and `env` as the Cursor block, and set its working directory to the repository root when the client has a place to put that path.

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
