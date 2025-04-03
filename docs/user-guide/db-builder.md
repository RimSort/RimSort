---
title: DB Builder
nav_order: 3
layout: default
parent: User Guide
permalink: user-guide/db-builder
---
# Steam Database Builder
{: .no_toc}

The Steam Database Builder is a special tool used to create and update your local copy of a steam workshop metadata database.

![DB Builder settings preview](/assets/images/previews/settings/db_builder.png)

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Getting started

_**NOTE:**_ DB Builder has some "soft requirements". If you are not a RimWorld Steam user, sadly, you will likely be limited in your DB building capabilities.

- You may need to have spent at least $5 USD on your Steam account to have general access to Steam WebAPI. This is a big part of how RimSort builds the full picture of mod dependency metadata, as well as some other things.
- In order to utilize SteamWorks, you also need to own RimWorld on Steam. This is required for Steam to allow access to certain mechanisms over the SteamWorks API.

### How to obtain your Steam WebAPI key for use with with DB Builder DynamicQuery

1. Open Steam's [API Key signup page.](https://steamcommunity.com/login/home/?goto=%2Fdev%2Fapikey) It requires a Steam account and a domain name to register it to, but I've found the actual domain you use does not seem to matter:

![image](https://user-images.githubusercontent.com/2766946/223573964-ace0a4e6-872a-4b50-b37c-902f14469c43.png)

2. Here is what you should see after signing up for a Steam account and registering for a new API key:

![image](https://user-images.githubusercontent.com/2766946/223573999-5f15abc6-c9e4-43c3-955a-95f2b9523fa2.png)

3. _**Keep your new Steam key private and do not share with anyone.**_ After clicking the Register button, you will be shown your new Steam API key. To obtain a new Steam API key, it is as easy as clicking the Revoke button and then registering a new key.

4. You can add this to RimSort by putting the key in the `Steam API Key` field under the `DB Builder` page of the settings panel.

DB Builder has 2 "Include" modes available. These modes can be used to create, manage, maintain, and update a SteamDB for use with RimSort. You can even interface with RimPy db.json as the formats are compatible.

Please review the following sections describing each mode, and why it is useful:

## Options

### DB Builder Modes (`When building the database:`)

#### All mods "Include" mode

- Can optionally look up & append DLC dependency data via SteamWorks API calls, after DB creation & WebAPI passes.
- Produces accurate, possibly "semi-incomplete" DB without looking up all PublishedFileIds via WebAPI, and instead needs to be supplied PublishedFileIds. Uses additional queries to lookup WebAPI metadata for the supplied PublishedFileIds.
- When used, DB Builder only includes metadata parsed from mods you have downloaded. Resultant DB contains metadata from locally available mods. Includes packageIds!
  - This mode _can_ produce a complete DB from scratch, but requires you to download the entire workshop to do so!
  - This mode can also produce partial DB updates _without_ downloading the entire workshop, but in doing so will only provide a _partial_ update to a SteamDB.

#### No local data "Include" mode

- Can optionally look up & append DLC dependency data via SteamWorks API calls, subsequent to DB creation & WebAPI passes.
- Produces accurate, "semi-complete" DB by looking up all available PublishedFileIds via WebAPI, instead of being supplied PublishedFileIds. Uses additional queries to lookup WebAPI metadata for a complete list of PublishedFileIds supplied from ALL available PublishedFileIDs (mods) it can find via Steam WebAPI.
- When used, DB Builder does _not_ include metadata from local mods. Resultant DB contains _no metadata_ from locally available mods. This means no packageIds!
  - Does not use metadata from locally available mods, and instead looks up PublishedFileIds by scraping Steam WebAPI.
  - You can create DB this way without any mods downloaded, and update local metadata to entries in the list via subsequent "All Mods" queries.

### Query DLC dependency data with Steamworks API
{: .d-inline-block}
Recommended Option
{: .label .label-green }

If you wish to include DLC dependency data in your database, ensure that you have the Steam client running & authenticated. Also, enable `Query DLC dependency data with Steamworks API` setting under `DB Builder`.

### Update database instead of overwriting
{: .d-inline-block}
Recommended Option
{: .label .label-green }

Optionally choose whether you want to overwrite, or update the selected database in-place when running DB Builder by configuring the `Update database instead of overwriting` setting under `DB Builder`.

If you choose to update, the existing database will be loaded into memory and updated with the new data before being written back to disk.

## Process for creating your own SteamDB

1. Open the DB Builder page within the RimSort Settings panel (`File > Settings > DB Builder`).

2. Ensure you have followed the steps above to configure your Steam WebAPI key!

3. Optionally configure your database expiry in seconds. This is the expiry in seconds used for the "version" key in your database. This is an epoch timestamp set at the current time of your database creation + the expiry duration. This will have an effect on when RimSort will warn you about the database being out of date. Default is 1 week. Note, this setting is under the `Databases` page.

4. Select the settings you prefer. See the previous section [Options](#options) for more details and recommendations.

5. Click "Build Database" to begin DB Builder process. DB Builder will prompt you to enter or select a JSON file path. This is where DB Builder will output your database when it is completed.

{: .warning}
> This video is outdated and may not be accurate for the latest versions of RimSort.

<iframe width="420" height="300" src="https://github.com/RimSort/RimSort/assets/2766946/bfdc5115-e349-4c92-86bc-96a6fcd1e9c6"  allowfullscreen="true" alt="Build Database Demo Video"></iframe>
