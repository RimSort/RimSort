---
title: SteamCMD & Workshop Browser
nav_order: 5
parent: User Guide
permalink: user-guide/steamcmd-browser
---
# SteamCMD and Workshop Browser

{: .no_toc}

[SteamCMD][SteamCMD] is a tool released by Valve that RimSort optionally integrates with in order to download Steam Workshop mods without Steam and or a copy of RimWorld on steam. RimSort's built in Workshop Browser allows you to navigate the Steam Workshop directly and select mods to download via SteamCMD.

RimSort supports updating of mods installed via SteamCMD, meaning that you can have finer control over whenever or not you wish to update Steam Workshop mods versus directly using Steam.

## Table of Contents

{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Setting up SteamCMD

On Linux, RimSort keeps SteamCMD's user configuration in a dedicated `home`
directory inside the configured SteamCMD prefix. This prevents SteamCMD from
changing the desktop Steam client's library configuration.

## Using the Workshop Browser

The Steam Workshop Browser is an embedded web view of the Steam Community that lets you
browse the RimWorld workshop and queue mods for download without leaving RimSort. A
sidebar ("Mod Downloader") holds the list of mods you have selected.

To add a mod:

1. Navigate to a mod or collection page in the browser. When the active page is a mod
   detail or collection page, an **Add to list** button appears in the navigation bar.
2. Click **Add to list** to append it to your download list. You can also click
   **Add Mods by Workshop ID** to paste one or more Steam published file IDs directly.

Each entry in the download list shows a badge indicating its status:

- **Default** &mdash; the mod is on your list but not yet downloaded. The list shows an
  **Add to list** control for this state.
- **Added** &mdash; the mod has been selected and is queued. A `-` badge marks this state.
- **Installed** &mdash; the mod is already present in your active mod set. A `✓` badge
  marks this state.

Right-click an entry to remove it individually, double-click an entry to open its
Workshop page, or click **Clear List** to empty the queue.

Once your list is ready, choose how to fetch the mods:

- **Download mod(s) (SteamCMD)** &mdash; downloads via SteamCMD. This does **not** require
  the Steam client or a copy of RimWorld on Steam, and is the preferred route for
  offline / SteamCMD-based instances.
- **Download mod(s) (Steam app)** &mdash; subscribes via the Steam client (Steamworks API).
  This requires the Steam client to be running and authenticated, and that you own
  RimWorld on Steam. Use this when you want the mods to also be managed by your Steam
  library.

{: .note}
> RimSort hides the native Steam "Subscribe" buttons while browsing so that all
> downloads go through the two options above.

## Updating SteamCMD Mods

RimSort tracks mods you have downloaded via SteamCMD using the
`appworkshop_294100.acf` file inside your SteamCMD prefix. To check for updates use
`Download > Update Workshop Mods`, or enable *Check for mod updates on refresh* under
*Settings &rarr; Advanced* to run the check automatically whenever your mod list is
refreshed.

When checking, RimSort compares the update timestamps recorded for your installed
SteamCMD mods (the `timeupdated` value in the `.acf` file and the mod folder's
modification time) against the latest timestamps reported by the Steam WebAPI. Outdated
mods appear in the *Workshop Mod Updater* panel, where you can re-download them either
via SteamCMD or by subscribing again through the Steam client (Steamworks API).

If you would rather replace a mod with a clean copy on every update, enable
**Delete before update** under *Settings &rarr; Internal Tools &rarr; SteamCMD*.
This removes the existing mod folder before re-downloading. Note that, because RimSort
relies on the `.acf` file for update detection, clearing the `.acf` file may interfere
with update checks &mdash; see [Troubleshooting SteamCMD](#troubleshooting-steamcmd)
below.

## Troubleshooting SteamCMD

{: .important}
> SteamCMD being an external tool, has a different set of logs. You can find them at your SteamCMD install location which may depend on your personal RimSort instance setup.
>
> You can find your current SteamCMD install location in the settings panel under `SteamCMD > SteamCMD installation location`. The logs are located in the subfolder `logs` of `SteamCMD`.

Occassionally, SteamCMD may have unwanted behavior such as download failures, reinstallation of deleted mods, etc. Assuming that your issue is not a connection issue where your computer is unable to communicate with Valve's servers, consider the following steps.

 - Clear your SteamCMD depotcache
 - Clear your .acf file

 Both of these steps can be done manually, or via RimSort in the settings panel under `Internal Tools > SteamCMD`.

 {: .warning}
 > RimSort currently relies on the data in the .acf file when checking for mod updates for SteamCMD mods. Deleting and or clearing the .acf file may cause potential issues with updating SteamCMD mods.

[SteamCMD]: https://developer.valvesoftware.com/wiki/SteamCMD
