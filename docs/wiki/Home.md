# RimSort Wiki

### Introduction

RimSort is an **open source** [RimWorld](https://store.steampowered.com/app/294100/RimWorld/) mod manager (WIP) for Linux, Mac, and Windows, based heavily on [RimPy](https://steamcommunity.com/sharedfiles/filedetails/?id=1847679158). Contributors are welcome!

## Table of contents
- [RimSort Wiki](#rimsort-wiki)
    - [Introduction](#introduction)
  - [Table of contents](#table-of-contents)
  - [Mod Dependencies ](#mod-dependencies-)
  - [Sorting Algorithm ](#sorting-algorithm-)
      - [RimPy Sorting Algorithm](#rimpy-sorting-algorithm)
      - [Toposort](#toposort)
      - [Writing Your Own Algorithm](#writing-your-own-algorithm)

## Mod Dependencies <a name="moddependencies"></a>

WIP

## Sorting Algorithm <a name="sortingalgorithm"></a>

RimSort exposes two sorting algorithms for sorting the active mod list.
The first algorithm, tentatively named `RimPy`, emulates the manner in which RimPy sorts mods.
The second algorithm, named Toposort, sorts mods with [Topological Sort](https://en.wikipedia.org/wiki/Topological_sorting).

#### RimPy Sorting Algorithm

The RimPy sorting algorithm follows, roughly, the steps described in [RimPy's Autosorting Wiki](https://github.com/rimpy-custom/RimPy/wiki/Autosorting).

1. The mod list is sorted alphabetically (by mod name).
2. Rules provided in `About.xml` files and the RimPy `communityRules.json` are *forcefully* applied (details on what this means below).

The result is a mod list that is, for the most part, sorted alphabetically; mods that need to be loaded before other mods are already loaded before (due to alphabetized sorting), or are forcefully inserted before the dependent mod.

> What does *forcefully* applied mean?

This can be illustrated with an example: let's say this is the list of mods: `[A, B, C, D, E]`. These are already alphabetically sorted so RimPy starts inserting them into the final load order one by one, starting with `A`. Mod `A` has no dependencies, so on iteration 1 it is inserted into the final load order, which is now `[A]`.

On the next iteration, `B` is inserted. However, `B` has dependencies `loadAfter: [D, E]` (maybe this was specified in its `About.xml`). What RimPy does here is forcefully inserts `D` and `E` before `B`, but after `A`. If `D` and `E` have no dependencies of their own, then the load order looks like this after inserting `B` and its dependencies: `[A, D, E, B]`.

However, there is a case where `B`'s dependencies have rules for each other, e.g. `D` should load after `E`. To cover these cases, if we inserted `D` and `E` in order, then we would violate this rule. Therefore, when inserting each dependency, we need to iterate through the sublist of already-inserted dependencies and find the latest occurrence of a dependency that is a dependency of the current dependency that we're trying to insert. The iterations for the final mod load order look like this:

```
[A]
[A, B]
[A, E, B]
[A, E, D, B]
...
```

Essentially *forcefully applied* refers to how the sorting algorithm recursively injects dependencies right before the mod that depends on them.

> What does this algorithm guarantee?

Assuming there are no conflicting load order rules, this algorithm guarantees that all load order rules are respected. This is because, as the algorithm iterates through the alphabetized list of mods and inserts them one by one, the current mod will either have dependencies that need to be forcefully injected befor it (in which case, the algorithm will do), or the mod has dependencies that already exist further up the list.

#### Toposort

The Toposort algorithm uses the [Toposort](https://pypi.org/project/toposort/) library to mathematically sort the mod list into "topological levels": mods in the first "topolevel" contains no dependencies to any other mod; once mods in the first topolevel are removed from consideration, mods in the second topolevel now contain no dependencies to other mods; once mods in the second topolevel are removed from consideration, mods in the third topolevel now contain no dependencies to other mods, and so on. This is a mathematical solution to a linear ordering of a directed graph (a directed graph is essentially what mods and their `loadAfter`s and `loadBefore`s entail).

The order of mods within topolevels does not matter at all. However, RimSort's implementation of Toposort will sort the mods alphabetically within their topolevels before appending the topolevel to the final mod load order.

> What does this algorithm guarantee?

Assuming there are no conflicting load order rules, this algorithm guarantees a mathematically optimal ordering of the mods. Note that the resulting load order will often be significantly different from one produced by the RimPy algorithm; this is expected behavior, as the RimPy algorithm sorts mods in a completely different manner.

#### Writing Your Own Algorithm

This project is open source, so you can easily write and use your own sorting algorithm in the application. Sorting algorithms are contained in the [sort](./../sort/) folder. The existing algorithms are modularized to only need the dependency graph and the list of active mods as an input. Switching between different sorting algorithms is done programmatically in [main_content_panel](./../view/main_content_panel.py). On the UI, it is done by selecting the algorithm through the settings drop-down menu, configured in the [settings panel](./../panel/settings_panel.py).