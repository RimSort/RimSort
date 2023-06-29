## User Guide

### Downloading a Release
[Releases can be found here.](https://github.com/RimSort/RimSort/releases)

This is an open-source project so feel free to build it yourself! Check out the [Development Guide here.](https://github.com/RimSort/RimSort/wiki/Development-Guide)

#### Windows
* Run the executable: `RimSort.exe`

#### MacOS
* Open the app bundle: `RimSort.app`
    * Mac users should keep in mind that Apple has it's own Runtime Protection called [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
        * This can cause issues when trying to run RimSort (or execute dependent libs)!
        * You can circumvent this issue by using `xattr` command to manually whitelist:
            * `xattr -d com.apple.quarantine RimSort.app`
            * `xattr -d com.apple.quarantine libsteam_api.dylib`
* If your Mac has M1/M2 Apple Silicon arm64 CPU...
    * Don't enable watchdog. I think that's what messes it up when being run through Rosetta 2
    * todds texture tool also does not currently (as of May 2023) support Mac M1/M2 arm64 CPU

#### Linux
* Run the executable: `./RimSort`

### Using RimSort
RimSort by default will prompt you to configure game configuration paths. Outside of that, there is a default settings applied and you are free to configure as you like from the Settings Panel

#### Actions panel
Here you can find general purpose options to interact with RimWorld game, its mod lists, as well as accessing things like Steam Workshop or todds texture optimizer from within RimSort.

#### "Game configuration" panel
Contains the required game configuration paths needed to manage your RimWorld game. You can also find a mechanism to check for RimSort client updates.

#### Mod info panel
Displays general information from a selected mod, with it's preview image if found.

#### Mod lists
Certain errors/warnings are produced based on dependency presence, incompatibilities, load rules, and any potential updates found.

#### External Metadata
RimSort has multiple external metadata options available. 
* Historically, RimPy has provided a Steam Workshop Database, in conjunction with a "Community Rules" Database. RimPy also allows user configured rules in some capacity.

For the most part, RimSort will adhere to this functionality.

* Steam Workshop Database (See: Paladin's `db.json`, RimSort's `steamDB.json`)
    * Contains metadata queried from Steam WebAPI + Steamworks API, utilizing the schema defined by Paladin's RimPy Mod Manager Database db.json
    * Why is this necessary?
        * Dependency metadata that is available on Steam - mod developers list DLC dependencies as well as additional mod dependencies on Steam.
            * In an ideal world, this can be taken care of completely by proper About.xml creation. However, SteamDB can supplement the available data if this is not done.
        * Some local metadata is included from mods' About.xml. This includes PackageId and gameVersions.
            * Providing a complete database, this allows the user to be able to sometimes find mod dependencies even without having the mods already downloaded downloaded.
                * When trying to import a mod list that contains mods that are not already available locally, in order to try to lookup PackageId -> PublishedFileId, SteamDB is necessary.
* Community Rules Database (Paladin's/RimSort's `communityRules.json`)
    * Contains a database of custom sorting rules compiled by a community, utilizing the schema defined by Paladin's RimPy Mod Manager Database communityRules.json
    * Why is this necessary?
        * This also allows us to load in custom sorting rules! Mod developers are not always as responsive when conflicts or incompatibilities are found. This allows people to define additional sorting rules that are generally agreed upon by others as required. Traditionally, Paladin distributed these via RimPy Community Mod Manager Database. RimSort has chosen a different path of distribution, utilizing git - more will be documented on that in a later section.
            * `loadAfter` and `loadBefore`
                * These are rules native to RimWorld. These are typically defined in a mod's About.xml
            * `loadBottom` - Originally defined by Paladin in RimPy Community Mod Manager Database community rules.
                * Used to force mods to the bottom of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 3 mod" and sorting it _after_ any mods not tagged with this.
            * _**WIP**_ `loadTop`
                * Used to force mods to the top of a list when sorting. RimSort tags mods with this from external metadata when populated, allowing it to be considered as a "tier 1 mod" and sorting it _before_ any mods not tagged with this. This custom rule is original to RimSort.
            * _**WIP**_ `isFramework`
                * A "framework mod" is a mod which provides extension to other mods, but does not provide actual content when used by itself. This custom rule is original to RimSort.
                * Examples of such mods:
                    * Universum, Vanilla Expanded Framework, XMLExtensions, etc
                * RimSort will tag such mods that have this rule, so that it can display a warning when these mods are not being "depended on". There is not much point to using such mods without the mods that use them, it is a framework after all!

### DB Builder

#### Getting started
_**NOTE:**__ DB Builder has some "soft requirements". If you are not a RimWorld Steam user, sadly, you will likely be limited in your DB building capabilities.
* I believe you need to have spent at least $5 USD on your Steam account to have general access to Steam WebAPI. This is a big part of how RimSort builds the full picture of mod dependency metadata, as well as some other things.
* In order to utilize SteamWorks, you also need to own RimWorld on Steam. This is required as far as I can tell for Steam to allow access to certain mechanisms over the SteamWorks API

##### How to obtain your Steam WebAPI key for use with with DB Builder DynamicQuery
1. Open Steam's [API Key signup page.](https://steamcommunity.com/login/home/?goto=%2Fdev%2Fapikey) It requires a Steam account and a domain name to register it to, but I've found the actual domain you use does not seem to matter:

![image](https://user-images.githubusercontent.com/2766946/223573964-ace0a4e6-872a-4b50-b37c-902f14469c43.png)

2. Here is what you should see after signing up for a Steam account and registering for a new API key:

![image](https://user-images.githubusercontent.com/2766946/223573999-5f15abc6-c9e4-43c3-955a-95f2b9523fa2.png)

3. _**Keep your new Steam key private and do not share with anyone.**_  After clicking the Register button, you will be shown your new Steam API key. To obtain a new Steam API key, it is as easy as clicking the Revoke button and then registering a new key.

4. You can add this to RimSort by right-clicking the "Build Database" button:

[add key demo](https://github.com/RimSort/RimSort/assets/2766946/57398ade-93fb-465c-95e8-3330df61fb8a)

DB Builder has 2 "Include" modes available. These modes can be used to create, manage, maintain, and update a SteamDB for use with RimSort. You can even interface with RimPy db.json as the formats are compatible.

Please review the following sections describing each mode, and why it is useful:

#### Overview of DB Builder modes

##### All mods "Include" mode
* Can optionally lookup & append DLC dependency data via SteamWorks API calls, subsequent to DB creation & WebAPI passes.
* Produces accurate, possibly "semi-incomplete" DB without looking up all PublishedFileIds via WebAPI, and instead needs to be supplied PublishedFileIds. Uses additional queries to lookup WebAPI metadata for the supplied PublishedFileIds.
* When used, DB Builder only includes metadata parsed from mods you have downloaded. Resultant DB contains metadata from locally available mods. Includes packageIds!
    * This mode _can_ produce a complete DB from scratch, but requires you to download the entire workshop to do so!
    * This mode can also produce partial DB updates _without_ downloading the entire workshop, but in doing so will only provide a _partial_ update to a SteamDB.

##### No local data "Include" mode
* Can optionally lookup & append DLC dependency data via SteamWorks API calls, subsequent to DB creation & WebAPI passes.
* Produces accurate, "semi-complete" DB by looking up all available PublishedFileIds via WebAPI, instead of being supplied PublishedFileIds. Uses additional queries to lookup WebAPI metadata for a complete list of PublishedFileIds supplied from ALL available PublishedFileIDs (mods) it can find via Steam WebAPI.
* When used, DB Builder does _not_ include metadata from local mods. Resultant DB contains _no metadata_ from locally available mods. This means no packageIds!
    * Does not use metadata from locally available mods, and instead looks up PublishedFileIds by scraping Steam WebAPI.
    * You can create DB this way without any mods downloaded, and update local metadata to entries in the list via subsequent "All Mods" queries.

#### Process for creating your own SteamDB
1. Open RimSort Settings panel

[settings panel](https://github.com/RimSort/RimSort/assets/2766946/77351f44-613c-40cc-89ba-7bfae857e717)

2. Ensure you have followed the steps above to configure your Steam WebAPI key!

3. Optionally configure your database expiry in seconds. This is the expiry in seconds used for the "version" key in your database. This is an epoch timestamp set at the current time of your database creation + the expiry duration. Default is 1 week.

[database expiry](https://github.com/RimSort/RimSort/assets/2766946/e767eb36-2ec9-45a0-b35f-9d7a155875bc)

4. Choose an "Include" mode - "All mods" or "No local data"

[include mode](https://github.com/RimSort/RimSort/assets/2766946/0b5bb952-b867-43f8-a94f-4dfdc9646284)

5. _**Recommended:**_ If you wish to include DLC dependency data in your database, ensure that you have Steam client authenticated to & running.
    * You will also need to enable this option in Settings:

[dlc dependency data](https://github.com/RimSort/RimSort/assets/2766946/135425de-40da-413f-9a0e-d44664f29a8d)

6. _**Recommended:**_ Optionally choose whether or not you want to overwrite, or update the selected database in-place when running DB Builder:
    * If you choose to update, the existing database will be loaded into memory and updated with the new data before being written back to disk.

[update database](https://github.com/RimSort/RimSort/assets/2766946/36593ca7-d2a8-4f19-a5dc-62afb9124418)

7. Click "Build Database" to begin DB Builder process. DB Builder will prompt you to enter or select a JSON file path. This is where DB Builder will output your database when it is completed.

[build database](https://github.com/RimSort/RimSort/assets/2766946/bfdc5115-e349-4c92-86bc-96a6fcd1e9c6)

#### Working with RimSort git integration

_**Prerequisite:**_ Install [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) for your respective platform.

This is used to download/upload a Steam Workshop Database (steamDB.json) or a Community Rules Database (communityRules.json) so that it may be collaborated on and shared.

1. Using Github, [create a repository](https://docs.github.com/en/get-started/quickstart/create-a-repo), or use an existing repository. 

2. Configure the repository URL in RimSort via the Settings panel:

[configure repo](https://github.com/RimSort/RimSort/assets/2766946/7897f2f8-fbc4-4671-8e9a-551203ebb844)

3. Configure your Github identity in RimSort. You will need to know your Github username, as well as have a personal access token created for RimSort with `Repo` permission granted.

[configure identity](https://github.com/RimSort/RimSort/assets/2766946/fa05b3ad-b29e-4284-a27c-430599f865fd)

4. Once you are satisfied with the changes you made to your database, you can share it via the built-in functions for your respective database.
* Cloning a database for use with RimSort:

[download database](https://github.com/RimSort/RimSort/assets/2766946/2c236e00-d963-4831-93e7-3effb10c6b5e)

* Uploading a database (Write access to a repository is required for you to be able to upload):

[upload database](https://github.com/RimSort/RimSort/assets/2766946/60ced0ef-adba-436f-8fbc-e593a236e389)

