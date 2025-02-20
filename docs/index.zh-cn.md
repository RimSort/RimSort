---
title: 主页
layout: home
nav_order: 1
description: "RimSort 是一款免费且开源的多平台 RimWorld 模组管理器。"
permalink: /
lang: zh-cn
---

{: .fs-9 }

# RimSort

{: .fs-6 .fw-300 }

一款免费且开源的多平台 RimWorld 模组管理器。

[开始使用](user-guide){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[前往 GitHub Releases 下载][Releases]{: .btn .fs-5 .mb-4 .mb-md-0 }


{% assign lang = site.active_lang %}

<p>
  {% for tongue in site.languages %}
  <a {% if tongue == site.active_lang %}style="font-weight: bold;"{% endif %} {% static_href %}href="{% if tongue == site.default_lang %}{{site.baseurl}}{{page.url}}{% else %}{{site.baseurl}}/{{ tongue }}{{page.url}}{% endif %}"{% endstatic_href %} >{{ tongue }}</a>{%- if forloop.last == false -%}{{" "}}{{ site.langsep }}{%- endif -%}
  {% endfor %}
</p>

---

![RimSort Preview](./assets/images/rimsort_preview.png)

RimSort 是社区主导的 [RimWorld](https://rimworldgame.com/) Mod 管理及排序工具，支持 Windows，macOS 和 Linux (Ubuntu) 系统。作为免费开源的软件，任何人都可以为其贡献代码或者自行编译。

除模组管理器的基础功能外，还提供更多增强特性！

---

## 核心功能：

- 依靠 Mod 数据规则、社区规则和 Steam 数据，自动对 Mod 进行排序
- 从 Mod 信息面板展示详细信息
- 导入、导出和保存 Mod 列表
- 实时在 Mod 列表展示警告/错误，如缺少依赖关系，不兼容，加载顺序错误等
- 提供搜索栏等功能，可轻松过滤大型模组列表
- 与可选的静态数据库集成，辅助改进排序和信息

## 附加功能：

- 与内外部工具的额外集成
  - Git Mod 和数据库的 Git 集成
  - [SteamworksPy](https://github.com/philippj/SteamworksPy) 的集成
  - 与 Steam 客户端交互，并提供 Steam API 游戏启动功能
- 分享日志至 [0x0.st](http://0x0.st/)
- 分享 Mod 列表至 [Rentry.co](https://rentry.co/)
- [todds DDS 编码器](https://github.com/joseasoler/todds)
  - 使用 3 种预设优化您的纹理
- 调用 Steam 浏览器，允许您通过 SteamCMD 和 Steam 客户端下载 Mod
  - 无需在 Steam 拥有 Rimworld 也可从创意工坊下载 Mod
- RimSort Steam 数据库构建器
  - 动态生成 Steam 创意工坊数据库（SteamDB）。该功能与 Paladin 的 RimPy 社区 Mod 管理器数据库 db.json 架构兼容且功能相同
  - 提供用于比较、合并和发布数据库的工具
- 社区规则数据库和用户规则的编辑器
  - 完全兼容 Paladin 的 RimPy 社区 Mod 管理器数据库 `communityRules.json` 架构
  - 提供用于比较、合并和发布数据库的工具

## 关于项目

### 协议

RimSort 采用 [GPL-3.0 协议](https://github.com/RimSort/RimSort/tree/main/LICENSE.md) 分发

### 感谢我们的贡献者！

<ul class="list-style-none">
{% for contributor in site.github.contributors %}
  <li class="d-inline-block mr-1">
     <a href="{{ contributor.html_url }}"><img src="{{ contributor.avatar_url }}" width="32" height="32" alt="{{ contributor.login }}"></a>
  </li>
{% endfor %}
</ul>

### 行为守则

我们旨在培养一个友好的社区。
在 GitHub 仓库中 [查看我们的行为守则](https://github.com/RimSort/RimSort/tree/main/CODE_OF_CONDUCT.md)。

[Wiki]: https://rimsort.github.io
[Repo]: https://github.com/RimSort/RimSort
[Issues]: https://github.com/RimSort/RimSort/issues
[Releases]: https://github.com/oceancabbage/RimSort/releases
[Discord]: https://discord.gg/aV7g69JmR2
