---
title: Sorting Algorithms
nav_order: 6
parent: User Guide
---
# Sorting Algorithms
RimSort exposes two sorting algorithms by default for sorting the active mod list. The default as of `v1.0.10` is [topological](#topological-sorting).

{: .warning}
> Different sorting Algorithms may result in different orderings that are both "correct". 
> 
> A correct ordering in terms of sorting is just one that follows all the defined rules (results in no order warnings in RimSort). It is likely that if you encounter issues in game when using certain algorithms that there is a "missing" order rule that went under the radar. You'll need to manually define that rule using the rule editor. In this case, we strongly suggest you report this new rule to the mod authors, and the community rules database!

---
## Alphabetical Sorting Algorithm

The first algorithm, `Alphabetical`, which is a more simplistic approach to properly sorting. This method alphabetizes your mods after splitting it into tiers.

The RimPy sorting algorithm follows, roughly, the steps described in [RimPy's Autosorting Wiki](https://github.com/rimpy-custom/RimPy/wiki/Autosorting).

1. The mod list is sorted alphabetically (by mod name).
2. Rules provided froma mod's `About.xml` files are compiled with externally provided metadata regarding that mod, are _forcefully_ applied (details on what this means below).

The result is a mod list that is, for the most part, sorted alphabetically, aside from the shuffling that provided load order rules impose. Mods that need to be loaded before other mods are already loaded before (due to alphabetized sorting), or are forcefully inserted before the dependent mod.

> What does _forcefully_ applied mean?

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

Essentially _forcefully applied_ refers to how the sorting algorithm recursively injects dependencies right before the mod that depends on them.

> What does this algorithm guarantee?

Assuming there are no conflicting load order rules, this algorithm guarantees that all load order rules are respected. This is because, as the algorithm iterates through the alphabetized list of mods and inserts them one by one, the current mod will either have dependencies that need to be forcefully injected befor it (in which case, the algorithm will do), or the mod has dependencies that already exist further up the list.

---

## Topological sorting
{: .d-inline-block}

Default (v1.0.10)
{: .label .label-green }

The second algorithm, "Topological", sorts mods with [Topological sorting](https://en.wikipedia.org/wiki/Topological_sorting).

The Toposort algorithm uses the [Toposort](https://pypi.org/project/toposort/) module to mathematically sort the mod list into "topological levels": mods in the first "topolevel" contains no dependencies to any other mod; once mods in the first topolevel are removed from consideration, mods in the second topolevel now contain no dependencies to other mods; once mods in the second topolevel are removed from consideration, mods in the third topolevel now contain no dependencies to other mods, and so on. This is a mathematical solution to a linear ordering of a directed graph (a directed graph is essentially what mods and their `loadAfter`s and `loadBefore`s entail).

The order of mods within topolevels does not matter at all. However, RimSort's implementation of Toposort will sort the mods alphabetically within their topolevels before appending the topolevel to the final mod load order.

> What does this algorithm guarantee?

Assuming there are no conflicting load order rules, this algorithm guarantees a mathematically optimal ordering of the mods. Note that the resulting load order will often be significantly different from one produced by the RimPy algorithm; this is expected behavior, as the RimPy algorithm sorts mods in a completely different manner.