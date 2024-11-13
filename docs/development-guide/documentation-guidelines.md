---
title: Documentation Guidelines
nav_order: 3
layout: default
parent: Development Guide
---

# Documentation Guidelines
{: .no_toc}

User documentation is hosted via [GitHub Pages](https://pages.github.com/) using the [Jekyll][Jekyll] theme, [Just the Docs](https://github.com/just-the-docs/just-the-docs). It is deployed via a GitHub action automatically whenever a change to documentation under the folder `docs` is merged into the main branch.

Contributions should follow the [Contributor Guidelines]({% link development-guide/contributor-guidelines.md %}) and be submitted via a pull request.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Building Locally

{: .note}

> For more detailed information on how to install [Jekyll][Jekyll] and its prerequisites, please see the relevant [Jekyll documentation](https://jekyllrb.com/docs/).

1. Navigate to the root of the documentation, the folder `docs`.

2. Build the site and make it available on a local server by running `bundle exec jekyll serve`

3. Browse to [http://localhost:4000](http://localhost:4000).

## Guidelines

### Assets

Where possible, all assets should be hosted within the repository itself and not be hosted externally and embedded as links.[^1] Even if the assets are used by the RimSort application itself, a copy of it should be included under `docs/assets`. This means that the documentation portion of the repository can act standalone.

### Navigation Order

Navigation order should be determined by importance, and by similarity between the names of the page titles. For example, `Documentation Guidelines` and `Contributer Guidelines` should be next to each other in the navigation order as they share a similar structure and word. This is for the sake of usability and asthetics.

### Style

Navigation info such as `File > Settings` and filenames such as `About.xml` should always be code blocked.

---

[^1]: Some assets from the old wiki are grandfathered in and not hosted within the repository itself.

[Jekyll]: https://jekyllrb.com/