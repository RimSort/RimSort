# Running RimSort

## Downloading a Release

[Releases can be found here.](https://github.com/RimSort/RimSort/releases)

This is an open-source project so feel free to build it yourself! Check out the [Development Guide here.](https://github.com/RimSort/RimSort/wiki/Development-Guide)

## Running the Executable

#### Windows
* Run the executable: `RimSort.exe`

#### MacOS
* Open the app bundle:`RimSort.app`
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

## Using RimSort

RimSort by default will prompt you to configure game configuration paths. Outside of that, there is a default settings applied and you are free to configure as you like from the Settings Panel

### Actions panel
Here you can find general purpose options to interact with RimWorld game, its mod lists, as well as accessing things like Steam Workshop or todds texture optimizer from within RimSort.

### "Game configuration" panel

Contains the required game configuration paths needed to manage your RimWorld game. You can also find a mechanism to check for RimSort client updates.

### Mod info panel
Displays general information from a selected mod, with it's preview image if found.

### Mod lists
Certain errors/warnings are produced based on dependency presence, incompatibilities, load rules, and any potential updates found. 

# External Metadata

RimSort has multiple external metadata options available. Historically, RimPy has provided a Steam Workshop Database, in conjunction with a "Community Rules" Database. RimPy also allows user configured rules in some capacity.

For the most part, RimSort will adhere to this functionality.

* Steam Workshop Database
    * Contains metadata queried from Steam WebAPI + Steamworks API
    * 

### Obtaining your Steam API key & using it with RimSort Dynamic Query

1. Open Steam's[ API Key signup page.](https://steamcommunity.com/login/home/?goto=%2Fdev%2Fapikey) It requires a Steam account and a domain name to register it to, but I've found the actual domain you use does not seem to matter:

![image](https://user-images.githubusercontent.com/2766946/223573964-ace0a4e6-872a-4b50-b37c-902f14469c43.png)


2. Here is what you should see after signing up for a Steam account and registering for a new API key:

![image](https://user-images.githubusercontent.com/2766946/223573999-5f15abc6-c9e4-43c3-955a-95f2b9523fa2.png)


3. _**Keep your new Steam key private and do not share with anyone.**_ After clicking the Register button, you will be shown your new Steam API key. To obtain a new Steam API key, it is as easy as clicking the Revoke button and then registering a new key.


4. You can add this to RimSort by right-clicking the "Build Database" button:


[add key demo](https://github.com/RimSort/RimSort/assets/2766946/57398ade-93fb-465c-95e8-3330df61fb8a)