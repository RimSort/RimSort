---
title: 基本用法
nav_order: 2
layout: default
parent: 用户指南
permalink: user-guide/basic-usage
lang: zh-cn
---
# 基本用法
{: .no_toc}

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

## 初始设置

RimSort 会提示你配置游戏路径并安装 SteamCMD。它可能还会询问你对某些关键设置的偏好，例如是否启用 Steam 集成。除此之外的将使用默认设置，你可以通过 [设置](#设置) 自由调整配置。

## 菜单栏

根据操作系统和桌面环境的不同，菜单栏可能位于 RimSort 主窗口顶部，或集成在全局菜单栏中。这里会显示当前运行的 RimSort 版本（如 v2.8.3），和包含更多选项的下拉菜单。你可以在此找到特定功能，例如导出 Mod 列表、上传日志、使用 todds 纹理优化工具或访问 Steam 创意工坊。

## 设置

通过菜单栏的 `文件 > 设置 ...（File > Settings...）` 可进入设置面板。该窗口包含多个标签页，每个标签页都有明确分类。

### 最低必要设置

至少需要设置以下路径：
- RimWorld 安装目录（RimWorld install directory）
- RimWorld 配置目录（RimWorld Config directory）
- 本地 Mods 目录（Local Mods）

其他设置均为可选，但部分功能可能需要相关设置项。

## Mod 信息面板

位于主窗口左侧区域。当选中某个 Mod 时，此处会显示该 Mod 的概要，如果存在预览图也会一并展示。

## Mod 列表

会根据以下因素生成错误/警告提示：
- 依赖项是否存在
- Mod 兼容性问题
- 加载顺序规则
- 检测到可用更新

## 外部元数据

{: .note}
> RimSort 发布版本不包含这些额外的外部元数据。有关可选（但强烈推荐）外部元数据库的信息，及其获取方式，请参阅 [数据库](../user-guide/databases.zh-cn)。

RimSort 利用外部元数据来增强其功能，它们提供了已下载 Mod 的 `About.xml` 文件所含信息之外的附加数据。RimSort 中的外部元数据是用户可扩展的，可共享的。

### Steam 创意工坊元数据（`steamDB.json`）
{: .d-inline-block}

Steam 创意工坊元数据
{: .label .label-blue }

  包含从 Steam WebAPI 和 Steamworks API 获取的元数据，使用 Paladin RimPy Mod 管理器的数据库 db.json 定义的结构

  要自行构建 Steam 创意工坊数据库，请使用 [Steam 数据库构建器](../user-guide/db-builder.zh-cn).
  > 为什么需要这个？
  
  - 获取 Steam 上可用的依赖元数据 - Mod 开发者会在 Steam 上列出依赖的 DLC 和其他依赖 Mod
    - 理想情况下，这可以通过正确编写 About.xml 文件完全替代。但当开发者没有完善地编写时，SteamDB 可以补充所需数据
  - 包含来自 Mod 中 About.xml 文件的本地元数据，包括 PackageId（包名）和 gameVersions（游戏版本）
    - 提供完整的数据库后，有时用户尚未下载某些 Mod 时，也能找到依赖关系
      - 当导入包含本地未下载 Mod 的 Mod 列表时，需要 SteamDB 实现 PackageId -> PublishedFileId 的查询

### 规则元数据（社区规则数据库，用户规则）
{: .d-inline-block}

规则元数据
{: .label .label-red }

  RimSort 使用两个外部规则数据库：`userRules.json` 和 `communityRules.json`。两者功能相同，区别在于社区规则数据库由社区维护共享，用户规则数据库用于存储你个人的加载顺序规则。

  这两个数据库都采用与 Paladin RimPy Mod 管理器的社区规则数据库（communityRules.json）兼容的格式。

  {: .note}
  > 虽然你可以直接修改这些纯文本格式的数据库，但建议使用 RimSort 内置的 [规则编辑器](../user-guide/rule-editor.zh-cn) 来编辑其中定义的规则。

  > 为什么需要这个？

  通过自定义排序规则，我们可以解决 Mod 开发者响应不及时导致的兼容性问题。用户可以添加被社区广泛认可的额外排序规则。传统上 Paladin 通过 RimPy 社区数据库分发这些规则，而 RimSort 选择通过 git 进行分发。
   
   - `loadAfter` 和 `loadBefore`
      - RimWorld 原生支持的规则类型，通常定义在 Mod 的 About.xml 文件中
    - `loadBottom` - 由 Paladin 在 RimPy 社区规则数据库中首创
      - 强制将 Mod 排序至列表底部。RimSort 从外部元数据中读取此标记，将被标记 Mod 视为「第三梯队 Mod」，在排序时置于未标记 Mod 之后
    - `loadTop`
      - 强制将 Mod 排序至列表顶部。这是 RimSort 首创的自定义规则，将被标记 Mod 视为「第一梯队 Mod」，在排序时置于未标记 Mod 之前
    - _**开发中**_ `isFramework`
      - 「框架 Mod」指为其他 Mod 提供扩展支持，但单独使用时无实际内容的 Mod。这是 RimSort 首创的自定义规则
      - 典型示例：
        - Universum、Vanilla Expanded Framework、XMLExtensions 等
      - RimSort 会标记带有此规则的 Mod，当检测到这些框架模组未被其他 Mod 依赖时发出警告。毕竟单独使用框架 Mod 没有意义！

  有关使用规则编辑器创建和管理这些规则的详细说明，包括如何为特定 Mod 添加自定义加载顺序规则，请参阅 [规则编辑器](../user-guide/rule-editor.zh-cn) 页面。
