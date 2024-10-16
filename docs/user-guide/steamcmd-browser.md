---
title: SteamCMD & Workshop Browser
nav_order: 5
parent: User Guide
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

## Using the Workshop Browser

## Updating SteamCMD Mods

## Troubleshooting SteamCMD

{: .important}
> SteamCMD being an external tool, has a different set of logs. You can find them at your SteamCMD install location which may depend on your personal RimSort instance setup.
>
> You can find your current SteamCMD install location in the settings panel under `SteamCMD > SteamCMD installation location`. The logs are located in the subfolder `logs` of `SteamCMD`.

Occassionally, SteamCMD may have unwanted behavior such as download failures, reinstallation of deleted mods, etc. Assuming that your issue is not a connection issue where your computer is unable to communicate with Valve's servers, consider the following steps.

 - Clear your SteamCMD depotcache
 - Clear your .acf file

 Both of these steps can be done manually, or via RimSort in the settings panel under the `SteamCMD` tab as of version `v1.0.11`.

 {: .warning}
 > RimSort currently relies on the data in the .acf file when checking for mod updates for SteamCMD mods. Deleting and or clearing the .acf file may cause potential issues with updating SteamCMD mods.

[SteamCMD]: https://developer.valvesoftware.com/wiki/SteamCMD
