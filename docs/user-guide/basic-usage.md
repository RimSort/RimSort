---
title: Basic Usage
nav_order: 2
layout: default
parent: User Guide
permalink: user-guide/basic-usage
---
# Basic Usage
{: .no_toc}

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Initial Setup

RimSort by default will prompt you to configure game configuration paths and install SteamCMD. It may also ask your preference for more critical settings such as whenever or not to enable Steam Integration. Outside of that, the default settings are applied, and you are free to configure as you like from the [Settings Panel](#settings-panel).

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

{: .note}
> RimSort releases do not come with this additional external metadata. For information on the optional but highly recommended databases that provide the additional external metadata and how to get them, see the [Databases page](../user-guide/databases).

RimSort uses external metadata in order to enhance its functionality. The metadata provides it with additional information beyond the information present in a downloaded mod's `About.xml` file. External Metadata in RimSort is designed to be highly user extendable and sharable.

### Steam Workshop Metadata (`steamDB.json`)
{: .d-inline-block}

Steam Workshop Metadata
{: .label .label-blue }

  Contains metadata queried from Steam WebAPI + Steamworks API, utilizing the schema defined by Paladin's RimPy Mod Manager Database db.json

  To build the Steam Workshop Database yourself, use the [SteamDB Builder](../user-guide/db-builder).
  > Why is this necessary?
  
  - Dependency metadata that is available on Steam - mod developers list DLC dependencies as well as additional mod dependencies on Steam.
    - In an ideal world, this can be taken care of completely by proper About.xml creation. However, SteamDB can supplement the available data if this is not done.
  - Some local metadata is included from mods' About.xml. This includes PackageId and gameVersions.
    - Providing a complete database, this allows the user to be able to sometimes find mod dependencies even without having the mods already downloaded.
      - When trying to import a mod list that contains mods that are not already available locally, in order to try to lookup PackageId -> PublishedFileId, SteamDB is necessary.

### Rules Metadata (Community Rules Database, User Rules)
{: .d-inline-block}

Rules Metadata
{: .label .label-red }

  There are two external rules databases that RimSort uses, `userRules.json` and `communityRules.json`. They both provide the same functionality, but one is community driven and intended to be shared, and the other is intended for your own personal load order rules. 
  
  Both of these databases uses a schema compatible with Paladin's RimPy Mod Manager Database communityRules.json.

  {: .note}
  > While you can modify the databases directly as they are plain text files, it is recommended to use RimSort's built in [Rule Editor](../user-guide/rule-editor) utility to edit the rules defined in these databases.

  > Why is this necessary?

  This also allows us to load in custom sorting rules! Mod developers are not always as responsive when conflicts or incompatibilities are found. This allows people to define additional sorting rules that are generally agreed upon by others as required. Traditionally, Paladin distributed these via RimPy Community Mod Manager Database. RimSort has chosen a different path of distribution, utilizing git.

   - `loadAfter` and `loadBefore`
      - These are rules native to RimWorld. These are typically defined in a mod's About.xml
   - `loadBottom` - Originally defined by Paladin in RimPy Community Mod Manager Database community rules.
      - Used to force mods to the bottom of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 3 mod" and sorting it _after_ any mods not tagged with this.
    - `loadTop`
      - Used to force mods to the top of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 1 mod" and sorting it _before_ any mods not tagged with this. This custom rule is original to RimSort.
    - _**WIP**_ `isFramework`
      - A "framework mod" is a mod which provides extension to other mods, but does not provide actual content when used by itself. This custom rule is original to RimSort.
      - Examples of such mods:
        - Universum, Vanilla Expanded Framework, XMLExtensions, etc
      - RimSort will tag such mods that have this rule, so that it can display a warning when these mods are not being "depended on". There is not much point to using such mods without the mods that use them, it is a framework after all!

  For detailed instructions on creating and managing these rules using the Rule Editor, including how to add custom load order rules for specific mods, see the [Rule Editor](../user-guide/rule-editor) page.
