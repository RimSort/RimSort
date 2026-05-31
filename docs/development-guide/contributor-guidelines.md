---
title: Contributor Guidelines
nav_order: 2
layout: default
parent: Development Guide
permalink: development-guide/contributor-guidelines
---


# Contributor Guidelines

{: .no_toc}

Please follow the following guidelines when contributing to RimSort.

## Table of Contents

{: .no_toc .text-delta }

1. TOC
{:toc}

## Basic Guidelines

1. Pull Requests need to be made AFTER all guidelines are met. It's OK to miss some stuff because we can catch it in review, but we should be proactive with docstrings, code formatting, etc. If not ready, use a draft.

2. Please submit Pull Requests which contain feature-specific changes only. PRs should not lump multiple changes into one thing. This so we can be more selective in discussion. This is a requirement, and deviation will cause PR to be closed.

3. Make sure your Pull Request passes the basic linter and Pytest checks before asking for a review. If they don't, they will be the first thing we ask you to fix.

4. There are GitHub Issue templates available on RimSort repository. Bug Reports and Feature Requests are to be submitted there, and if there is consensus on a request, it will become an "Implement ...." Issue. Please do not deviate from template and allow maintainers to modify the Issue to include relevant tasks and title information once consensus is reached.

   - Consensus = consensus between maintainers. That being said, we rely on your feedback, so you will have a say.
   - You are also welcome to fork this repository and make whatever changes you deem fit privately.

5. ALL PRs need to have a corresponding Issue and/or Issue sub-task(s) to reference. This is for transparency and overall will help anybody else helping to keep track of things.
   - Anybody can contribute to RimSort. That being said, we are a community and these guidelines will help encourage and enforce consistency with RimSort growth.
   - Maintainer or not - you do not have to be a maintainer to submit PR! Please don't hesitate to work from a fork or something if that's how you roll.

6. In 99% of situations, you should not submit pull requests that are only dependency bumps. Basic dependency bumps are handled automatically using dependabot.

7. When running RimSort from source, dev mode is active by default. Your development data is stored in the `dev/` subdirectory of the repo — your production RimSort configuration is never touched. See [Development Setup](development-setup.md#dev-mode-data-isolation) for details and env var overrides.

## Versioning and Releases

We utilize automated semantic versioning based on a [GitHub action](https://github.com/PaulHatch/semantic-version/tree/v5.4.0/). This action will auto-increment the version based on keywords in commit messages, tags, and commits in general. The process is utilized by both the release and auto-build pipelines.

**Manual overrides using tags should be formatted with `v` as the prefix and follow the release format, e.g. `v1.1.1`.**

**SemVer will only monitor changes in specific directories for purposes of implicit types.** This is to ensure that changes to the repository that are irrelevant to the function of the code don't change the app version.

<details>
<summary> Currently monitored directories </summary>
  <ul>
    <li> app </li>
    <li> libs </li>
    <li> submodules </li>
    <li> themes </li>
  </ul>
</details>

### Release Description and Pipeline

|    Type    |                        Version Format                         | Trigger | Description                                                                                                                                      |
| :--------: | :-----------------------------------------------------------: | :-----: | :----------------------------------------------------------------------------------------------------------------------------------------------- |
|  Release   |                v\${major}.\${minor}.\${patch}                 | Manual  | Versions that can be safely used and are considered stable.                                                                                      |
|    Edge    | v\${major}.\${minor}.\${patch}-edge\${increment}+${short-sha} | Manual  | Versions that are released often and include the latest features and fixes, but may have significant breaking bugs in them.                      |
| Auto-Build | v\${major}.\${minor}.\${patch}-auto\${increment}+${short-sha} |  Auto   | Versions created by the auto-build pipeline triggered on every pull request and push to main. Not released. Builds created persist as artifacts. |

Releases are created through the manual triggering of the relevant GitHub workflow action. For safety, consider setting the release to only be created as a draft.

Edge releases will be overwritten, with a new edge tag created and the old release fully deleted. Stable releases will not be overwritten. By default, non-draft stable releases are protected, and the auto-action will fail if a release with the same version tag already exists.

If, for whatever reason, the build step completed, but the remaining steps of the release pipeline fails, you may re-run the workflow with an override to skip the build step by providing the action with the run ID of which it will grab the build artifacts from for release.

Beware that if a new commit was pushed to the target branch between the new release attempt and when the builds were actually made, there will be a commit mismatch between the builds and the release information. By default, the release pipeline will detect this and fail to maintain correct release info. **The version and version.xml in the build is always correct.**

### Versioning Keywords and Patterns

|   Type    |    Pattern     | Description                                                                                               |
| :-------: | :------------: | --------------------------------------------------------------------------------------------------------- |
|   major   |    (major)     | Major and breaking updates                                                                                |
|   minor   |    (minor)     | Minor updates. Not expected to be breaking, but may introduce new features and large amounts of bug fixes |
|   patch   | n/a (Implicit) | Non-breaking small changes. Incremented on PR if no other patterns.                                       |
| increment | n/a (Implicit) | Number of commits since last version change                                                               |
| short-sha | n/a (Implicit) | First seven characters of the commit sha identifier a build is made from                                  |

### Caveats and Potential Issues

#### Potential Race Condition

Due to how GitHub runner environments work, there is a potential race condition if a commit is made to the branch that the build and release action is running on. If something changes on the branch while the action is running, depending on what step the action is on, there may be differences in the version information in the release, and the commit being used for building. If especially unlucky where one runner for a specific build target loaded and checked out, but a commit is pushed to the branch before other runners for a different target, the builds created for the targets may all be on different commits.

**Note that the actual version.xml and subsequent app reported version will always be correct.**

To mitigate this issue, the version info for the release pipeline is grabbed first thing, before builds and testing has started. Additionally, a commit mismatch check is done just before release. If any of the artifact's target commits mismatch with the release commit, the workflow will fail by default.

## Developing Features

Please ensure if you have any feature request to check if there is already something planned. We are tracking features and issues related to RimSort in the GitHub repo's "Issues" tab. If it is not already in the issues tab, you can discuss this with maintainers first through the RimSort Discord server.

## Task Runner

We use [just](https://just.systems/) as our task runner. Run `just` with no arguments to list all available recipes.

Key recipes for contributors:

| Command | Description |
| :--- | :--- |
| `just check` | Run all code quality checks (ruff, ruff-format, typecheck, pyright, jscpd, shfmt, markdownlint) |
| `just fix` | Auto-fix linting and formatting issues |
| `just test` | Run tests with doctest modules enabled |
| `just test-coverage` | Run tests with coverage reports (XML, HTML, terminal) |
| `just test-verbose` | Run tests with verbose output and short tracebacks |
| `just ruff` | Check code for linting issues (ruff check) |
| `just ruff-format` | Check code for formatting issues (ruff format) |
| `just ruff-fix` | Auto-fix linting issues (ruff check --fix) |
| `just ruff-format-fix` | Auto-fix formatting issues (ruff format) |
| `just typecheck` | Run static type checking (mypy) |
| `just pyright` | Run static type checking (pyright) |
| `just jscpd` | Detect copy-paste code duplication (zero-tolerance) |
| `just shfmt` | Check shell script formatting (shfmt, diff-only) |
| `just shfmt-fix` | Auto-fix shell script formatting issues (shfmt -w) |
| `just markdownlint` | Check Markdown files for linting issues (markdownlint-cli2) |
| `just markdownlint-fix` | Auto-fix Markdown linting issues (markdownlint-cli2 --fix) |
| `just clean` | Remove build artifacts, caches, and generated files |
| `just run` | Run the RimSort application |
| `just dev-setup` | Install all dependencies including dev and build groups |
| `just build` | Build RimSort executable (inits submodules, runs checks) |
| `just build-version VERSION` | Build with a specific version string, e.g. "1.2.3.4" |
| `just update` | Update all dependencies to latest compatible versions |
| `just submodules-init` | Initialize and update git submodules (after cloning) |
| `just build-help` | Show help for distribute.py build script |
| `just ci` | Run full CI pipeline locally (checks + tests + coverage) |

**Run `just check` before submitting a PR.** CI runs all of these checks and will fail if any report issues.

## Coding Style

### Linting and Formatting

- **[Ruff](https://docs.astral.sh/ruff/)** is used for both linting and formatting (`just ruff` + `just ruff-format`).
  - [VS Code extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
  - Ruff replaces isort, flake8, and black. Disable those if you have them installed.
  - Configuration is in `pyproject.toml`.
- **[mypy](https://mypy.readthedocs.io/en/stable/)** is used for static type checking (`just typecheck`).
  - [VS Code extension](https://marketplace.visualstudio.com/items?itemName=matangover.mypy)
- **[JSCPD](https://github.com/kucherenko/jscpd)** is used for copy-paste detection (`just jscpd`).
  - CI enforces a 0% duplication threshold. If you have similar code blocks, extract a shared helper.
- For shell scripts, we use [shfmt](https://github.com/mvdan/sh#shfmt).
  - [VS Code extension](https://marketplace.visualstudio.com/items?itemName=mkhl.shfmt)
- **[markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)** is used for Markdown linting (`just markdownlint`).
  - [VS Code extension](https://marketplace.visualstudio.com/items?itemName=DavidAnson.vscode-markdownlint)
  - Configuration is in `.markdownlint-cli2.jsonc`.

### Conventions

- The preferred docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
- Type annotations should be added to function/method signatures.
  - Use Python 3.10+ standards. (Avoid importing Typing. [PEP 604](https://peps.python.org/pep-0604/) instead of Optional)
- VS Code workspace settings are included
