---
title: Basic Usage
nav_order: 2
layout: default
parent: User Guide
---
# Basic Usage
{: .no_toc}

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Initial Setup

RimSort by default will prompt you to configure game configuration paths and install SteamCMD. Outside of that, the default settings are applied and you are free to configure as you like from the Settings Panel.

## Main Menu Bar

The main menu bar is, depending on your operating system and desktop environment, either the bar at the top of the main RimSort Window, or part of the global menu bar. It contains the RimSort version you are running as well as dropdown menus that hide additional options. Here, you'll find special options to interact with RimSort like exporting your mod list, uploading logs, using the todds texture optimizer, or accessing the Steam Workshop.

## Settings panel

You can enter the settings panel from the main menu bar using `File > Settings... ` In this window, you'll find multiple tabs, each labeled. 

### Minimum Required Settings

At a minimum, the paths for the RimWorld install directory, RimWorld Config directory, and Local Mods need to be set. All other settings are optional for basic operations, but certain features may be inoperable.

## Mod info panel

The left side of the main window. Displays general information from a selected mod, with its preview image if found.

## Mod lists

Certain errors/warnings are produced based on dependency presence, incompatibilities, load rules, and any potential updates found.

## External Metadata

RimSort has multiple external metadata options available.

- Historically, RimPy has provided a Steam Workshop Database, in conjunction with a "Community Rules" Database. RimPy also allows user configured rules in some capacity.

For the most part, RimSort will adhere to this functionality.

- Steam Workshop Database (See: Paladin's `db.json`, RimSort's `steamDB.json`)
  - Contains metadata queried from Steam WebAPI + Steamworks API, utilizing the schema defined by Paladin's RimPy Mod Manager Database db.json
  - Why is this necessary?
    - Dependency metadata that is available on Steam - mod developers list DLC dependencies as well as additional mod dependencies on Steam.
      - In an ideal world, this can be taken care of completely by proper About.xml creation. However, SteamDB can supplement the available data if this is not done.
    - Some local metadata is included from mods' About.xml. This includes PackageId and gameVersions.
      - Providing a complete database, this allows the user to be able to sometimes find mod dependencies even without having the mods already downloaded.
        - When trying to import a mod list that contains mods that are not already available locally, in order to try to lookup PackageId -> PublishedFileId, SteamDB is necessary.
- Community Rules Database (Paladin's/RimSort's `communityRules.json`)
  - Contains a database of custom sorting rules compiled by a community, utilizing the schema defined by Paladin's RimPy Mod Manager Database communityRules.json
  - Why is this necessary?
    - This also allows us to load in custom sorting rules! Mod developers are not always as responsive when conflicts or incompatibilities are found. This allows people to define additional sorting rules that are generally agreed upon by others as required. Traditionally, Paladin distributed these via RimPy Community Mod Manager Database. RimSort has chosen a different path of distribution, utilizing git - more will be documented on that in a later section.
      - `loadAfter` and `loadBefore`
        - These are rules native to RimWorld. These are typically defined in a mod's About.xml
      - `loadBottom` - Originally defined by Paladin in RimPy Community Mod Manager Database community rules.
        - Used to force mods to the bottom of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 3 mod" and sorting it _after_ any mods not tagged with this.
      - _**WIP**_ `loadTop`
        - Used to force mods to the top of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 1 mod" and sorting it _before_ any mods not tagged with this. This custom rule is original to RimSort.
      - _**WIP**_ `isFramework`
        - A "framework mod" is a mod which provides extension to other mods, but does not provide actual content when used by itself. This custom rule is original to RimSort.
        - Examples of such mods:
          - Universum, Vanilla Expanded Framework, XMLExtensions, etc
        - RimSort will tag such mods that have this rule, so that it can display a warning when these mods are not being "depended on". There is not much point to using such mods without the mods that use them, it is a framework after all!