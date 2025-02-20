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
   - 无论是否具有维护者身份都可以提交 PR！如果你愿意做出贡献，请不要犹豫，从 fork 仓库或其他东西开始吧。

6. 通常不应提交仅更新依赖版本的 PR。基本的依赖更新由 dependabot 自动进行，例外情况需在相关 Issue 中说明必要性。

## 版本管理与发布

我们基于 [GitHub Action](https://github.com/PaulHatch/semantic-version/tree/v5.4.0/) 自动化进行发布，使用语义版本控制。Action 会根据提交信息中的关键词、标签以及提交内容，自动递增版本号。此流程同时适用于正式发布和自动构建流水线。

**手动覆盖标签时应使用 `v` 作为前缀并遵循发布格式规范，例如：`v1.1.1`**

**语义版本控制只会监控特定目录的变更，以确定隐含的提交目的。**此举旨在确保与代码功能无关的仓库变更，不会影响应用程序版本。

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

|    发布类型    |                        版本号格式                         | 何时触发 | 描述                                                                                                                                      |
| :--------: | :-----------------------------------------------------------: | :-----: | :----------------------------------------------------------------------------------------------------------------------------------------------- |
|  稳定版（Release）   |                v\${major}.\${minor}.\${patch}                 | 手动  | 可以安全使用，被认为稳定的版本。                                                                                      |
|    前瞻版（Edge）    | v\${major}.\${minor}.\${patch}-edge\${increment}+${short-sha} | 手动  | 频繁发布的版本，包含最新功能和修复，但可能存在重大的破坏性 Bug。                      |
| 自动构建 | v\${major}.\${minor}.\${patch}-auto\${increment}+${short-sha} |  自动   | 自动构建流水线生成的版本，由每个 Pull Request 和向 main 分支的推送触发。这些构建版本不会正式发布，生成的构建产物将以 artifact 保留。 |

正式版需要通过手动触发相关的 GitHub 工作流操作来创建。为确保安全，发布仅创建为草稿。

前瞻版会被覆盖，每次将创建新的前瞻版标签并完全删除旧的发布，而稳定版不会被覆盖。默认情况下，非草稿的稳定版受到保护，已存在相同版本号的发布时，自动操作将会失败。

若构建步骤已完成，但发布流水线的后续步骤失败，你可以通过提供运行 ID 来重新运行工作流（跳过构建步骤），系统将从指定运行记录中获取构建产物进行发布。

注意，如果在启动新发布与实际发布完成期间，目标分支又有新的提交，这可能导致构建产物与发布信息的提交版本不匹配。默认情况下，发布流水线会检测到这种情况，会终止操作以保持发布信息的准确性。**构建产物中的 version 文件和 version.xml 始终包含正确版本信息。**

### 版本关键词与模式

|   类型    |     模式      | 描述                                                                                    |
| :-------: | :-----------: | -------------------------------------------------------------------------------------- |
|   major   |    (major)    | 重大且破坏性的更新                                                                      |
|   minor   |    (minor)    | 次要更新。预计不会造成破坏性变动，但可能引入新功能或大量错误修复                        |
|   patch   | n/a（隐式）   | 非破坏性的小改动。当没有其他模式时，在合并请求时递增                                    |
| increment | n/a（隐式）   | 自上次版本变更以来的提交次数                                                            |
| short-sha | n/a（隐式）   | 构建所对应提交 sha 标识的前七位字符                                                       |

### 注意事项与潜在问题

#### 潜在竞态条件

由于 GitHub runner 环境的工作机制，当构建发布流程正在运行的代码分支有新提交时，可能会出现竞态条件。如果工作流运行期间分支内容发生变化，根据工作流所处的阶段，可能会导致发布版本信息与构建所用提交版本之间存在差异。在极端情况下，若某个构建目标的运行器已完成代码检出，而其他目标的运行器在开始前又收到了新提交，则不同构建目标可能会基于不同的代码提交进行构建。

**注意：实际的 version.xml 文件和程序报告的版本号始终是准确的。**

为缓解此问题，发布流程会首先获取版本信息（早于构建和测试步骤）。此外，在发布前会进行提交一致性检查。如果任何构建产物的目标提交与发布提交不匹配，工作流默认会终止并报错。

## 功能开发指南

提交新功能请求前，请先确认是否已有相关计划。我们通过 GitHub 仓库的「Issues」页追踪 RimSort 的功能需求和问题报告。若尚未存在相关 Issue，建议先通过 RimSort Discord 服务器与维护团队讨论。

## 编码风格指南

- 推荐使用 Python 格式化工具：[ruff](https://docs.astral.sh/ruff/) (`pip install ruff`)
  - VS Code 用户可安装 [Ruff 扩展](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
  - 注意：Ruff 已替代 isort、flake8 和 black，确保禁用这些工具以避免冲突
- 文档字符串格式建议采用：[Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
- 函数/方法签名需添加类型注解
  - 使用 Python 3.10+ 标准（避免导入 Typing 模块，采用 [PEP604](https://peps.python.org/pep-0604/) 的 `| None` 代替 `Optional`）
- 静态类型检查使用：[mypy](https://mypy.readthedocs.io/en/stable/)
  - VS Code/VS Codium 用户推荐安装 [mypy 扩展](https://marketplace.visualstudio.com/items?itemName=matangover.mypy)
- 为了快速配置开发环境，你可以安装上面描述的一些依赖项，以及用于类型检查的其他模块，实现开发自动化
  - `pip install -r requirements_develop.txt`
- 仓库包含预置的 VS Code 工作区设置
- Shell 脚本格式化使用：[shfmt](https://github.com/mvdan/sh#shfmt)
  - [VS Code 扩展](https://marketplace.visualstudio.com/items?itemName=mkhl.shfmt)
