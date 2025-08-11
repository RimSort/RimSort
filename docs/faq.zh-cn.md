---
title: 常见问题
nav_order: 2
description: "常见问题"
layout: default
permalink: faq/
lang: zh-cn
---
# 常见问题
{: .no_toc }
以下是常见问题及解决方案

<details open markdown="block">
  <summary>
    目录
  </summary>
  {: .text-delta }
1. TOC
{:toc}
</details>


## macOS Gatekeeper/Windows Defender 提示 RimSort 已损坏/不安全/是恶意软件

RimSort 不是恶意软件，可以安全使用。你可以放心忽略任何杀毒软件检测警告。

由于 RimSort 是编译后的 Python 程序，它容易触发误报，尤其发布的新版本。有一些方法可以减少这些误报，但这需要昂贵的签名证书。如果你仍然不确定，可以使用 Virus Total 扫描可执行程序/文件。通常可能会有一些误报，但绝大多数扫描结果都会是安全的。

对于 **_Windows Defender_**，我们通常会尝试向微软提交样本，以便在出现误报时将 RimSort 版本加入白名单。这个过程可能至少需要一整天，并且每次发布都需要重复。因此，如果 WD 误报 RimSort，我们仍然感谢你的报告，但你可以安全地忽略 WD 的警告。

对于 **_macOS_**，我们需要向苹果支付类似的年费才能在 macOS 上签名应用程序。目前，Mac 用户可以使用 [这个临时解决方案](https://rimsort.github.io/RimSort/zh-cn/user-guide/downloading-and-installing#macos)。除了向苹果支付费用外，我们在 macOS 上没有其他方案解决这个问题。

## 游戏路径在哪里？

游戏路径和其他位置设置位于设置面板中的 `位置（Locations）` 下。

## 什么是 todds？

[Todds](https://github.com/todds-encoder/todds) 是由 [joseasoler](https://github.com/joseasoler) 开发的一款工具，用于将 RimWorld 的纹理文件编码为另一种格式——.dds。.dds 文件在加载时消耗的内存更少，且不会明显变模糊。有关 todds 的更多详细信息，请参阅 [todds wiki](https://github.com/todds-encoder/todds/wiki)。

## Steam 创意工坊数据库有什么用？

RimSort 使用 Steam 创意工坊数据库（Steam DB）来加载 Steam 平台提供的 Mod 依赖数据（指工坊中「必需物品」部分）。尽管 Mod 作者应尽量在其 Mod 的 about.xml 文件中也明确指定这些数据，但通过 Steam DB，RimSort 可以同时利用 Mod 的 Steam 数据和 about.xml 文件中的信息。有关详细信息，请参阅 [用户指南](https://rimsort.github.io/RimSort/zh-cn/user-guide/databases)。

## 社区规则数据库有什么作用？

社区规则数据库（Community Rules DB）用于指导 RimSort 将 Mod 按正确顺序加载。这些规则由社区发现并提交，之后被收集到社区规则库中共用。你可以通过在 GitHub 上提交 pull request 来为社区规则库做贡献。有关该数据库的详细信息，请参阅 [用户指南](https://rimsort.github.io/RimSort/zh-cn/user-guide/databases)。

## 如果已安装 Steam，如何启用如 `在 Steam 打开 Mod（Open mod in Steam）` 等 Steam 客户端集成功能？

前往 `设置 > 高级 > 启用 Steam 客户端集成（Settings > Advanced > Enable Steam client integration）` 并勾选。

## 为什么通过 RimSort 启动 RimWorld 时会出现 `无法初始化 Steam API（Could not initialize Steam API）` 错误？

{: .note}
> 这是 macOS 上已知的常见问题。临时解决方案是直接通过 Steam 启动 RimWorld。

首先确保已在 RimSort 设置中启用 `Steam 客户端集成（Steam client integration）` 功能。同时确认 Steam 客户端正在运行，并使用拥有 RimWorld 的账户登录认证。

如果上述步骤无效，请尝试改用 Steam 直接启动 RimWorld 临时解决。即使直接通过 Steam 启动，RimWorld 仍会使用你在 RimSort 中创建的 Mod 列表（除非使用了特殊运行参数）。如果配置了自定义运行参数，在通过 Steam 启动时可能需要通过 Steam 传递这些参数。
