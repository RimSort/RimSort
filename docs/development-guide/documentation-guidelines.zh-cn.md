---
title: 文档指南
nav_order: 3
layout: default
parent: 开发指南
permalink: development-guide/documentation-guidelines
lang: zh-cn
---

# 文档指南
{: .no_toc}

用户文档托管在 [GitHub Pages](https://pages.github.com/)，使用 [Jekyll][Jekyll] 的 [Just the Docs](https://github.com/just-the-docs/just-the-docs) 主题构建。当 `docs` 文件夹中的文档变更被合并到主分支时，系统会通过 GitHub Action 自动完成部署。

贡献者请遵循 [贡献指南](/development-guide/contributor-guidelines)，通过 pull request 提交改动。

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

## 本地构建

{: .note}

> 如需详细了解如何安装 [Jekyll][Jekyll] 及其先决条件，你可以参考相关的 [Jekyll 文档](https://jekyllrb.com/docs/)。

1. 进入文档根目录 `docs` 文件夹。

2. 运行命令，构建网站并在本地启动服务：`bundle exec jekyll serve`。

3. 访问 [http://localhost:4000](http://localhost:4000)。

## 编写规范

### 资源文件

所有资源文件都应尽可能地托管在代码仓库内部，不要使用外部链接嵌入。[^1] 即使这些资源被 RimSort 应用程序本身使用，也应在 `docs/assets` 目录下保存副本，这使得文档部分可以独立运行。

### 导航排序

导航顺序应根据重要性以及页面标题的相似性来确定。例如，「文档指南」和「贡献指南」应该在导航中相邻排列，因为它们具有相似的用词结构。这是出于可用性和美观性考虑。

### 样式规范

导航栏信息（如 `文件 > 设置`）和文件名（如 `About.xml`）应始终使用代码块包裹。

### 页面内容

#### 目录（TOC）

{: .note}
> 父页面会自动生成并包含其子页面的目录。请不要禁用此功能。

大部分内容页面都应包含目录。目录应作为页面主标题之后的第一个二级标题。

页面主标题和目录标题本身不应包含在目录中，需添加 `.no_toc` 标记。页面内的其他标题都应包含在目录中。

目录标题应使用 `.text-delta` 标记以应用特定样式。

使用以下代码生成目录（Markdown 格式）：
```markdown{% raw %}
## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}
{% endraw %}```

---

[^1]: 旧版 Wiki 中的部分资源沿用原有托管方式，未存放在当前仓库中。

[Jekyll]: https://jekyllrb.com/
