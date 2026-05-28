---
title: 贡献指南
nav_order: 2
layout: default
parent: 开发指南
permalink: development-guide/contributor-guidelines
lang: zh-cn
---


# 贡献指南

{: .no_toc}

为 Rimsort 做出贡献时，请遵循以下准则。

## 目录

{: .no_toc .text-delta }

1. TOC
{:toc}

## 基本准则

1. 请在满足所有准则要求后再提交 Pull Request。允许存在少量疏漏（我们会在审核时修正），但请确保文档注释、代码格式等基础事项已妥善处理。如未准备就绪，请使用草案（Draft）模式提交。

2. Pull Request 必须仅包含单一功能的相关改动。请勿将多项改动混杂在一个 PR 中，这有助于更高效地开展讨论。未遵守此要求的 PR 将被关闭。

3. 提交审核前请确保通过基础 linter 检查和 Pytest 测试。若未通过，这将是我们要求优先修复的内容。

4. 请使用 RimSort 仓库提供的 GitHub Issue 模板。Bug 报告和功能请求需通过模板提交。当某项请求达成共识后，将转为对应的实现 Issue。请保持模板格式规范，并允许维护者在达成共识后修改 Issue，以关联相关任务和标题信息。
   - 共识指的是维护团队内部达成一致，但我们也依赖你的反馈，你有发言权。
   - 也欢迎通过 fork 仓库，进行你认为合适的个性化修改

5. 所有 PR 必须关联对应的 Issue 或子任务。这旨在确保开发过程透明化，便于社区协作追踪进度。
   - 任何人都可以向 RimSort 做贡献，但作为一个社区，这些准则有助于鼓励和加强一致性，帮助 RimSort 成长
   - 维护者与否都不影响你提交 PR！请不要犹豫，如果你喜欢从 fork 仓库或其他方式开始贡献，那也完全可以。

6. 在 99% 的情况下，你不应该提交仅更新依赖版本的 Pull Request。基本的依赖更新由 dependabot 自动处理。

## 版本管理与发布

我们基于 [GitHub Action](https://github.com/PaulHatch/semantic-version/tree/v5.4.0/) 自动化进行发布，使用语义版本控制。Action 会根据提交信息中的关键词、标签以及提交内容，自动递增版本号。此流程同时适用于正式发布和自动构建流水线。

**手动覆盖标签时应使用 `v` 作为前缀并遵循发布格式规范，例如：`v1.1.1`**

**SemVer 将仅监控特定目录的变更，以确定隐含的提交目的。**此举旨在确保与代码功能无关的仓库变更，不会影响应用程序版本。

<details>
<summary> 当前监控目录 </summary>
  <ul>
    <li> app </li>
    <li> libs </li>
    <li> submodules </li>
    <li> themes </li>
  </ul>
</details>

### 发布说明和流水线

|    类型    |                        版本号格式                         | 触发 | 描述                                                                                                                                      |
| :--------: | :-----------------------------------------------------------: | :-----: | :----------------------------------------------------------------------------------------------------------------------------------------------- |
|  Release   |                v\${major}.\${minor}.\${patch}                 | 手动  | 可以安全使用，被认为稳定的版本。                                                                                      |
|    Edge    | v\${major}.\${minor}.\${patch}-edge\${increment}+${short-sha} | 手动  | 这些版本发布频繁，包含最新功能和修复，但可能存在显著的破坏性 Bug。                      |
| Auto-Build | v\${major}.\${minor}.\${patch}-auto\${increment}+${short-sha} |  自动   | 自动构建流水线在每个 Pull Request 和向 main 分支推送时触发生成的版本。不会正式发布，构建产物以 artifact 形式保留。 |

正式版通过手动触发相关 GitHub 工作流操作创建。为保证安全，建议将发布流程设置为仅创建草稿。

前瞻版会被覆盖：每次都会创建新的前瞻版标签并删除旧的 release，而稳定版不会被覆盖。默认情况下，非草稿稳定版会受到保护，当已存在相同版本号的发布时，自动操作将会失败。

如果构建步骤完成了，但发布流水线后续步骤失败，可以通过提供工作流的运行 ID 来重新运行该工作流并跳过构建步骤；系统会从对应运行记录中获取构建产物用于发布。

注意：如果在开始尝试发布与实际完成发布之间，目标分支又有新的提交，那么构建使用的提交版本与发布信息可能不一致。默认情况下，发布流水线会检测到这种提交不匹配并失败，以保证发布信息正确。**构建产物中的 version 文件和 version.xml 始终是正确的。**

### 版本关键词与模式

|   类型    |    模式     | 描述                                                                                               |
| :-------: | :----------: | --------------------------------------------------------------------------------------------------------- |
|   major   |    (major)  | 重大且具有破坏性的更新                                                                                |
|   minor   |    (minor)  | 次要更新。通常不期望造成破坏，但可能引入新功能或大量错误修复                                        |
|   patch   | n/a（隐式） | 非破坏性的小改动。如果没有其他关键词匹配，在合并 PR 时自动递增版本号                                        |
| increment | n/a（隐式） | 距离上次版本变更以来的提交次数                                                                      |
| short-sha | n/a（隐式） | 构建所对应的提交 SHA 的前七位字符                                                                    |

### 注意事项与潜在问题

#### 潜在竞态条件

由于 GitHub runner 环境的工作方式，如果在工作流运行期间对所构建分支又进行了提交，可能会出现竞态条件。根据工作流运行到的步骤不同，可能会导致发布的版本信息与实际用于构建的提交版本不一致。

如果在最不理想的情况下，某个构建目标的 runner 已完成检出并开始构建，而在其他目标 runner 开始之前又发生提交，那么各构建目标最终可能基于不同的提交。

**注意：实际的 version.xml 文件以及随后的应用程序报告版本始终会是正确的。**

为缓解此问题，发布流水线会在构建和测试开始之前就先获取版本信息。同时，在发布前会执行提交一致性检查。如果任意构建产物的目标提交与发布时记录的提交不匹配，工作流默认会失败。

## 功能开发指南

提交新功能请求前，请先确认是否已有相应计划。我们会在 GitHub 仓库的「Issues」页跟踪 RimSort 的功能和问题。如果在 Issues 页没有找到对应条目，建议先通过 RimSort Discord 服务器与维护者进行讨论。

## 任务执行器

我们使用 [just](https://just.systems/) 作为任务运行器。你可以直接运行 `just` 查看所有可用 recipes。

给贡献者的关键命令：

| 命令 | 描述 |
| :--- | :--- |
| `just check` | 运行所有代码质量检查（ruff、ruff-format、typecheck、jscpd、shfmt） |
| `just fix` | 自动修复 lint 和格式化问题 |
| `just test` | 运行测试（启用 doctest 模块） |
| `just test-coverage` | 运行测试并生成覆盖率报告（XML、HTML、终端） |
| `just test-verbose` | 运行测试（详细输出和简短回溯） |
| `just ruff` | 检查代码 lint 问题（ruff check） |
| `just ruff-format` | 检查代码格式问题（ruff format） |
| `just ruff-fix` | 自动修复 lint 问题（ruff check --fix） |
| `just ruff-format-fix` | 自动修复格式问题（ruff format） |
| `just typecheck` | 运行静态类型检查（mypy） |
| `just jscpd` | 检测代码拷贝粘贴重复（零容忍） |
| `just shfmt` | 检查 Shell 脚本格式（shfmt，仅显示差异） |
| `just shfmt-fix` | 自动修复 Shell 脚本格式问题（shfmt -w） |
| `just clean` | 删除构建产物、缓存和生成的文件 |
| `just run` | 运行 RimSort 应用程序 |
| `just dev-setup` | 安装所有依赖（包括 dev 和 build 组） |
| `just build` | 构建 RimSort 可执行文件（初始化子模块并运行检查） |
| `just build-version VERSION` | 使用指定版本字符串构建，例如 "1.2.3.4" |
| `just update` | 将所有依赖更新至最新兼容版本 |
| `just submodules-init` | 初始化和更新 git 子模块（克隆后需要运行） |
| `just build-help` | 显示 distribute.py 构建脚本的帮助信息 |
| `just ci` | 本地运行完整 CI 流水线（检查 + 测试 + 覆盖率） |

**提交 PR 前请先运行 `just check`。**CI 会执行全部这些检查，并且若检测到问题将失败。

## 代码风格

### Linting 与格式化

- **[Ruff](https://docs.astral.sh/ruff/)** 同时用于 lint 和格式化（`just ruff` + `just ruff-format`）。
  - VS Code 扩展：<https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff>
  - Ruff 替代 isort、flake8 和 black。请确保禁用这些工具以避免冲突。
  - 配置位于 `pyproject.toml`。

- **[mypy](https://mypy.readthedocs.io/en/stable/)** 用于静态类型检查（`just typecheck`）。
  - VS Code 扩展：<https://marketplace.visualstudio.com/items?itemName=matangover.mypy>

- **[JSCPD](https://github.com/kucherenko/jscpd)** 用于检测代码拷贝粘贴（`just jscpd`）。
  - CI 会强制要求 0% 重复率。如果你的代码块相似，请抽取为共享 helper。

- 对于 shell 脚本，我们使用 [shfmt](https://github.com/mvdan/sh#shfmt)。
  - VS Code 扩展：<https://marketplace.visualstudio.com/items?itemName=mkhl.shfmt>

### 约定

- 推荐的 docstring 格式是： [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
- 函数/方法的签名需要添加类型注解。
  - 使用 Python 3.10+ 标准。（避免导入 Typing；使用 [PEP 604](https://peps.python.org/pep-0604/) 的 `| None` 代替 Optional）
- 已包含 VS Code 工作区设置
