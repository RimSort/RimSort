# RimSort

![RimSort Preview](./docs/rimsort_preview.png)

RimSort is an **open source** [RimWorld](https://store.steampowered.com/app/294100/RimWorld/) mod manager for Linux, Mac, and Windows, built from the ground up to be a reliable, community-managed alternative to [RimPy Mod Manager](https://github.com/rimpy-custom/RimPy/releases). RimSort also has the option to utilize the [RimPy Mod Manager Database](https://steamcommunity.com/sharedfiles/filedetails/?id=1847679158). RimSort currently provides a number of essential mod-managing features, including (but not limited to):

## Core features:
* Automatically sort mod lists with rules derived from mod data, community-submitted rules, and Steam data
* Clicking on a mod displays detailed information in the mod info panel
* Drag and drop mods between an Active and Inactive mods list to enable/disable/rearrange mods
* Import, export, and save mod lists
* Live view of warnings/errors for mod lists, such as missing dependencies, incompatibilities, load order violations, etc
* Search bar to filter for specific mods in big mod lists

## Additional features - internal & external tool integrations, such as:
* Git integration using GitPython & PyGithub modules
* Integration with [SteamworksPy](https://github.com/philippj/SteamworksPy)
    * This is used to interact with Steam client, as well as provide Steam API game launch
* Log sharing to [0x0.st](http://0x0.st/)
* Mod list sharing with [Rentry.co](https://rentry.co/)
* [todds DDS encoder](https://github.com/joseasoler/todds)
    * Optimize your textures with 3 available presets
* Steam Browser that allows you to download mods via SteamCMD, as well as Steam client
* RimSort DB Builder
    * Generate Steam Workshop Database (SteamDB) on the fly. This is compatible with & synonymous to Paladin's RimPy Community Mod Manager Database db.json schema
    * Tools to compare, merge, and publish databases using this tool
* Rule Editor for configured Community Rules database, as well as User Rules
    * Fully compatible with Paladin's RimPy Community Mod Manager Database communityRules.json schema
    * Tools to compare, merge, and publish databases using this tool
* Support for creating additional sorting modes (in code)
    * "Alphabetical" sorting algorithm
    * "Topological" sorting algorithm

To run RimSort, visit the [Releases](https://github.com/oceancabbage/RimSort/releases) page and download the latest zipped release for your operating system. For Windows and Linux, unzip the download and run the `RimSort` executable inside the unzipped folder. For MacOS, unzip the download and run the `.app` directly. For more information on how to run and use RimSort, visit the [User Guide](https://github.com/oceancabbage/RimSort/wiki/User-Guide).

RimSort is currently under active development. Contributors are welcome! If you are interested in helping develop RimSort, read the [Development Guide](https://github.com/oceancabbage/RimSort/wiki/Development-Guide) on to get started-- this Wiki contains lots of information on how RimSort works under the hood.

There are lots of planned features for RimSort. Most of them are tracked in the [Issues](https://github.com/oceancabbage/RimSort/issues) section of this repo. If you have a feature suggestion, feel free to create an Issue here yourself!

<a href="https://discord.gg/aV7g69JmR2">
    <img src="https://github.com/RimSort/RimSort/assets/2766946/486f4f8c-fed5-4fe1-832f-6461b7ce3a55" alt="Join us on Discord">
</a>

[**Click here to join!**](https://discord.gg/aV7g69JmR2)
