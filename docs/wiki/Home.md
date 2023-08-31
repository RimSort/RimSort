# Welcome to the RimSort Wiki

RimSort is currently under active development. Contributors are welcome! If you are interested in helping develop RimSort, read the [Development Guide](https://github.com/oceancabbage/RimSort/wiki/Development-Guide) on to get started. This Wiki contains lots of information on how RimSort works under the hood.

For more information on how to run and generally use RimSort, check out the [User Guide](https://github.com/oceancabbage/RimSort/wiki/User-Guide).

RimSort provides a number of essential mod-managing features, as well as some additional integrations with external tools.

## Core features:
* Automatically sort mod lists with rules derived from mod data, community-submitted rules, and Steam data
* Clicking on a mod displays detailed information in the mod info panel
* Drag and drop mods between an Active and Inactive mods list to enable/disable/rearrange mods
* Import, export, and save mod lists
* Live view of warnings/errors for mod lists, such as missing dependencies, incompatibilities, load order violations, etc
* Search bar to filter for specific mods in big mod lists

## Additional features:
* Internal & external tool integrations, such as:
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