---
title: CLI Reference
nav_order: 8
layout: default
parent: User Guide
permalink: user-guide/cli-reference
---
# CLI Reference
{: .no_toc}

RimSort provides a command-line interface for headless operation of key features. This enables automation workflows, CI/CD integration, and scripting without requiring the graphical interface.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Overview

The RimSort CLI is designed for users who need to automate RimSort functionality in headless environments. Unlike the graphical interface, the CLI:

- **Requires no display server** - Perfect for Docker containers, remote servers, and CI/CD pipelines
- **Provides structured exit codes** - Enables reliable error handling in scripts and automation
- **Supports environment variables** - Securely configure credentials without exposing them in command history
- **Works without Qt dependencies** - Lightweight operation with minimal system requirements

Currently available commands:
- `build-db` - Build Steam Workshop metadata databases

Additional commands may be added in future versions to support more RimSort functionality.

## Running the CLI

If you have RimSort installed from a release build:

```bash
./RimSort build-db --help
```

or on windows:
```bash
RimSort.exe build-db --help
```

If you're running from source:

```bash
python -m app build-db --help

# Or with uv:
uv run python -m app build-db --help
```
## Commands
### `build-db`

Build a Steam Workshop metadata database by querying the Steam WebAPI. The resulting database contains mod names, URLs, dependencies, and optional DLC requirements in a JSON format compatible with RimSort and RimPy.

#### Prerequisites

**Steam WebAPI Key**
{: .d-inline-block}
Required
{: .label .label-red }

{: .important }
For detailed instructions on obtaining your Steam WebAPI key, see the [DB Builder guide](db-builder#how-to-obtain-your-steam-webapi-key-for-use-with-with-db-builder-dynamicquery).

{: .warning}
You need to own RimWorld on Steam for this to work. You may also need to have spent at least $5 USD on your Steam account to have general access to the Steam WebAPI to utilize Steamworks API (for DLC dependency data).

You need a Steam WebAPI key (32 characters) to use this command. The DB Builder has some "soft requirements" inherited from Steam's API access policies:

#### Basic Usage

```bash
# Using environment variable (recommended for security)
export RIMSORT_STEAM_API_KEY=your_32_character_key_here
RimSort build-db --output steamDB.json

# Quick build without DLC data (faster)
RimSort build-db --output steamDB.json --no-dlc-data --quiet

# Update existing database instead of overwriting
RimSort build-db --output steamDB.json --update
```

#### Options Reference

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--api-key TEXT` | String | (see below) | Steam WebAPI key (32 characters). Can also be set via `RIMSORT_STEAM_API_KEY` environment variable. |
| `--output PATH` | Path | **required** | Output JSON file path for the database. |
| `--dlc-data/--no-dlc-data` | Boolean | dlc-data | Include DLC dependency data via Steamworks API. Requires Steam client running and RimWorld ownership. Significantly slower due to additional API calls. |
| `--update/--overwrite` | Boolean | overwrite | Update existing database (merge new data) or overwrite completely. |
| `--quiet` | Flag | false | Suppress progress output. Errors are still written to stderr. |

#### Environment Variables & Configuration

The Steam API key can be provided in three ways, with the following priority order:

1. **`--api-key` command line argument** - Highest priority, but may expose the key in shell history
2. **`RIMSORT_STEAM_API_KEY` environment variable** - Recommended for security
3. **Fallback to `settings.json`** - If you've configured RimSort GUI, the CLI will use that API key

#### Exit Codes

The `build-db` command uses standard exit codes for automation:

- **0** - Success: Database built/updated successfully
- **1** - Error: Validation failed, build failed, or exception occurred
- **2** - Interrupted: User cancelled with Ctrl+C

### Troubleshooting

##### **`Error: Steam API key is required`**

The command cannot find a valid API key. Provide it via:
- `--api-key` command line option
- `RIMSORT_STEAM_API_KEY` environment variable
- Configure in RimSort GUI (saved to `settings.json`)

##### **`Error: Invalid Steam WebAPI key! Key must be 32 characters`**

Your API key is not the correct length. Check your key at [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Common issue: extra spaces or newlines when copying the key.



##### **`Error: Cannot update non-existent database`**

You used `--update` mode but the target database file doesn't exist. For the first build, use `--overwrite` (the default):

```bash
# First build
RimSort build-db --output steamDB.json --overwrite

# Subsequent updates
RimSort build-db --output steamDB.json --update
```

#####**DLC data collection fails silently**

DLC dependency data requires the Steamworks API, which needs:
- Steam client running and authenticated
- RimWorld owned on your Steam account

If unavailable, use `--no-dlc-data` for headless environments:

```bash
RimSort build-db --output steamDB.json --no-dlc-data
```
