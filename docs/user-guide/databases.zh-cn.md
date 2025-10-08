---
title: 数据库
parent: 用户指南
nav_order: 7
permalink: user-guide/databases
lang: zh-cn
---

# 数据库
{: .no_toc}

RimSort 使用外部数据库来增强排序和依赖项处理等功能。这些数据库不包含在发行版中，但我们提供了便捷的安装和更新工具。它们完全可选，基础功能无需数据库支持，但额外的数据能显著提升用户体验。

数据库配置路径在 `文件 > 设置 > 数据库（File > Settings > Databases）`。

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

## 社区规则数据库

社区规则数据库是由社区整理的 Mod 加载顺序规则合集。虽然最佳实践是 Mod 作者在 `about.xml` 文件中添加适当的加载规则，但可能有时作者无法及时响应。因此，我们通过这个公开的社区驱动数据库，收集带有注释的额外规则。该数据库也兼容 RimSort 特有的加载规则（例如 `强制排序至列表底部（Force load at bottom of list）`）。

## Steam 创意工坊数据库

{: .note}
> 关于如何构建或更新 Steam 创意工坊数据库，请参阅 [此页面](../user-guide/db-builder.zh-cn)

Steam 创意工坊数据库（Steam DB）主要用于提供额外的依赖项数据。这些信息需要通过抓取 Steam 创意工坊并下载 Mod 来解析获取。通过静态数据库，用户无需实际下载 Mod 即可访问这些信息。

## 通过 RimSort 的 Git 集成管理数据库

### _**前置条件:**_ 为你的系统安装 [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

此功能用于下载/上传 Steam 创意工坊数据库（`steamDB.json`）或社区规则数据库（`communityRules.json`），便于协作与共享。

{: .important}
> 步骤 3 的 GitHub 身份配置，仅在你希望通过 RimSort 直接向配置的 GitHub 仓库提交 pull request 时才必需。若仅需通过 Git 从公共仓库下载数据库或仅在本地修改，无需此步骤。你也可以不通过 RimSort 配置，直接手动在 GitHub 提交 pull request。

1. [创建远程仓库](https://docs.github.com/en/get-started/quickstart/create-a-repo) 或使用现有仓库。GitHub 仓库可与 RimSort 实现额外集成功能。

2. 在 RimSort 设置下的 `数据库（Databases）` 中配置仓库 URL。

3. **（可选）** 在 RimSort 的 `高级设置（Advanced）` 中配置 GitHub 账户。你需要准备 GitHub 用户名，并为 RimSort 创建具有 `Repo` 权限的个人访问令牌。

4. 完成数据库修改后，可通过内置功能分享你的数据库改动。

### 克隆数据库到 RimSort

{: .warning}
> 此视频内容已过时，可能不适用于最新版 RimSort

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/2c236e00-d963-4831-93e7-3effb10c6b5e" frameborder="0" allowfullscreen="true" alt="下载数据库演示视频"></iframe>

### 上传数据库（需要仓库写入权限）

{: .warning}
> 此视频内容已过时，可能不适用于最新版 RimSort

<iframe width="420" height="315" src="https://github.com/RimSort/RimSort/assets/2766946/60ced0ef-adba-436f-8fbc-e593a236e389" frameborder="0" allowfullscreen="true" alt="上传数据库演示视频"></iframe>