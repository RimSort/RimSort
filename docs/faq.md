---
title: FAQ
nav_order: 2
description: "Frequently asked questions"
layout: default
---
# Frequently Asked Questions
{: .no_toc }
Here are answers/solutions to common questions/solutions

<details open markdown="block">
  <summary>
    Table of contents
  </summary>
  {: .text-delta }
1. TOC
{:toc}
</details>


## macOS gatekeeper/Windows Defender tells me that RimSort is damaged/unsafe to run/is malware

RimSort is not malware and is safe to use. You can safely override any AV (Anti-virus) detections.

Unfortunately, because RimSort is compiled Python, it has a tendency to trigger false detections, especially for new releases. There are ways for us to mitigate these detections, but it requires expensive code signing certificates. If you are still unsure, you can scan the executable/files using virus total. Typically, there may be a few false detections, but the vast majority of scans will return negative.

For **_windows defender (WD)_** specifically, we tend to try and send samples to Microsoft to whitelist the RimSort release if there are any false detections. This process can still take at least a full day, and needs to be repeated every release. Thus, if WD is false flagging RimSort, we still appreciate a quick report, but it should be safe to override WD. 

For **_macOS_,** we'd require a similar yet separate yearly fee to sign apps on macOS. Mac users can, for now, use [this workaround](https://github.com/RimSort/RimSort/wiki/User-Guide#macos). There is no solution for us on macOS other than paying Apple.

## Where are game paths located?

Game paths and other location settings are located in the settings panel under `Locations`.

## What is todds?

[Todds](https://github.com/todds-encoder/todds) is a tool by [joseasoler](https://github.com/joseasoler) for encoding RimWorld's texture files to a different format, .dds. .dds files consume less memory when loaded without getting noticeably blurrier. For more details on todds, see the [todds wiki](https://github.com/todds-encoder/todds/wiki).

## What is the Steam Workshop Database used for?

RimSort uses the Steam Workshop Database (Steam DB) for loading mod dependency data that is only available on Steam (the "required items" section). While modders should strive to specify this data also in their mods about.xml, the Steam DB allows RimSort to use a mods Steam data, in addition to its about.xml. For details, see the [user guide](/user-guide/databases)

## What is the Community Rules Database used for?

The Community Rules Database (Community Rules DB / CR DB) is used for getting RimSort to place mods in the correct load order. These rules are found and submitted by the community and then collected for shared use in the CR DB. You can contribute to the CR DB by submitting pull requests on GitHub. For details about the DB, see the [user guide](/user-guide/databases).

## How do I enable Steam client integration features like `Open mod in Steam` if I have Steam installed?

Go to `Settings > Advanced > Enable Steam client integration` and check the checkbox.

## Why do I get a `Could not initialize Steam API` error when starting RimWorld from RimSort?

{: .note}
> This is a known common issue on macOS. As a workaround, launch RimWorld directly via Steam.

First, make sure you have `Steam client integration` enabled in RimSort's settings. Additionally, ensure that Steam is running and authenticated with the user that owns RimWorld.

If the previous steps did not work, then try launching RimWorld from Steam instead of RimSort as a workaround. Unless you are using special run arguments, the mod list you created in RimSort should be the one used by RimWorld even if launched via Steam directly. If you use custom run arguments, you may need to pass them via Steam if launching from Steam. 