---
title: Databases
parent: User Guide
nav_order: 7
permalink: user-guide/databases
---

# Databases
{: .no_toc}

RimSort uses external databases in order to improve certain functions like sorting and dependency handling. They are not included with the releases, but we provide tools to easily install and update them. They are completely optional and are not required for basic operations, but the extra data they provide RimSort can greatly improve the user experience.

Databases can be configured in the settings under `Databases`.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Community Rules Database

The community rules database is a collection of load order rules compiled by the community. While it is always best for mod authors to add the appropriate load order rules to their `about.xml` files, sometimes mod authors are unresponsive for one reason or another. As such, we instead compile these extra rules with notes into a public and community driven database. This database is also compatible with RimSort specific load rules such as `Force load at bottom of list`.

## User Rules Database

The user rules database (`userRules.json`) is a local, user-specific database that stores custom load order rules defined by the user. This file is automatically created in the databases folder if it does not exist, and it allows users to define their own rules for mod load ordering that persist across sessions. Rules in this database take precedence over community rules and can be edited through RimSort's rule editor interface.

## Use This Instead Database

The "Use This Instead" database is an optional external database that provides recommendations for alternative mods when outdated or incompatible mods are detected. This feature helps users identify updated versions or better alternatives for mods in their collection. The database source can be configured in settings and is typically sourced from the [Use This Instead mod](https://steamcommunity.com/sharedfiles/filedetails/?id=3396308787) repository, which maintains a community-curated list of mod replacements and updates.

## No Version Warning Database

The No Version Warning database (`ModIdsToFix.xml`) is an external database that contains a list of mod package IDs that should not trigger version mismatch warnings. This is useful for mods that intentionally do not include version information in their `about.xml` files or for mods that are compatible across multiple game versions. The database helps reduce false positive warnings by identifying mods that are known to be version-agnostic. The source can be configured in settings and is typically sourced from the [No Version Warning mod](https://steamcommunity.com/sharedfiles/filedetails/?id=2599504692) repository.

## Steam Workshop Database

{: .note}
> For information on how to build or update the Steam Workshop Database, see [this page](../user-guide/db-builder)

The Steam Workshop Database (Steam DB) is primarily used to provide additional dependency data. This information can only be gathered by crawling the Steam Workshop and downloading the workshop mods to parse mod data. By having a static database, users do not need to have these mods downloaded in order to access this information.

## Working with databases via RimSort Git integration

### _**Prerequisite:**_ Install [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) for your respective platform.

This is used to download/upload a Steam Workshop Database (`steamDB.json`) or a Community Rules Database (`communityRules.json`) so that it may be collaborated on and shared.

{: .important}
> Step 3, setting up a GitHub identity is only required if you wish to upload your database directly to a configured GitHub repository via a pull request through RimSort. It is *not* required for simply downloading the database via Git from a public repository or for modifying the database locally. You can also just make a pull request yourself on GitHub without configuring GitHub within RimSort.

1. [Create a remote repository](https://docs.github.com/en/get-started/quickstart/create-a-repo), or use an existing repository. GitHub repositories have additional optional integration within RimSort.

2. Configure the repository URL in RimSort via the Settings panel under `Databases`.

3. **Optional!** Configure your GitHub identity in RimSort under `Advanced`. You will need to know your GitHub username, as well as have a personal access token created for RimSort with `Repo` permission granted.

4. Once you are satisfied with the changes you made to your database, you can share it via the built-in functions for your respective database.

### Cloning a database for use with RimSort:

{: .warning}
> This video is outdated and may not be accurate for the latest versions of RimSort.

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/2c236e00-d963-4831-93e7-3effb10c6b5e" frameborder="0" allowfullscreen="true" alt="Download Database Demo Video"></iframe>

### Uploading a database (Write access to a repository is required for you to be able to upload):

{: .warning}
> This video is outdated and may not be accurate for the latest versions of RimSort.

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/60ced0ef-adba-436f-8fbc-e593a236e389" frameborder="0" allowfullscreen="true" alt="Upload Database Demo Video"></iframe>
