---
layout: default
title: 翻译指南
nav_order: 4
parent: 开发指南
permalink: development-guide/translation-guidelines
lang: zh-cn
---

# 翻译指南
{: .no_toc}

本指南说明如何为 RimSort 贡献翻译。项目使用 PySide6 的 Qt 国际化 (i18n) 系统和 QTranslator。

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

## 翻译系统概述

RimSort 使用 Qt 翻译系统，包含以下组件：
- **`.ts` 文件**：源翻译文件（XML 格式），供翻译者编辑
- **`.qm` 文件**：编译后的二进制翻译文件，供应用程序使用
- **QTranslator**：Qt 的翻译引擎，加载和应用翻译

## 项目结构

```
RimSort/
├── locales/           # 翻译文件目录
│   ├── en_US.ts      # 英语（源语言）
│   ├── zh_CN.ts      # 简体中文
│   ├── fr_FR.ts      # 法语
│   ├── de_DE.ts      # 德语
│   ├── es_ES.ts      # 西班牙语
│   ├── ja_JP.ts      # 日语
│   ├── pt_BR.ts      # 巴西葡萄牙语
│   ├── ru_RU.ts      # 俄语
│   └── tr_TR.ts      # 土耳其语
└── app/
    └── controllers/
        └── language_controller.py  # 语言管理
```

## 当前支持的语言

| 语言代码 | 语言名称 | 状态 |
|----------|----------|------|
| `en_US` | English | 完整（源语言） |
| `zh_CN` | 简体中文 | 完整 |
| `fr_FR` | Français（法语） | 完整 |
| `de_DE` | Deutsch（德语） | 完整 |
| `es_ES` | Español（西班牙语） | 完整 |
| `ja_JP` | 日本語（日语） | 完整 |
| `pt_BR` | Português（巴西葡萄牙语） | 完整 |
| `ru_RU` | Русский（俄语） | 完整 |
| `tr_TR` | Türkçe（土耳其语） | 完整 |

## 翻译助手工具

项目提供了全面的 `translation_helper.py` 脚本来帮助翻译工作。

**重要提示**：该工具基于 PySide6 的命令实现，需要先设置好项目的开发环境。请参考 [开发环境设置指南](development-setup.zh-cn.md) 完成环境配置后再使用此工具。

### 可用命令

翻译助手工具提供以下命令：

#### 基本命令
- **`check [language]`**：检查特定语言或所有语言（如果未指定语言）的翻译完整性
- **`stats`**：显示所有语言的翻译统计信息
- **`validate [language]`**：验证翻译文件格式和内容，自动修复占位符不匹配等常见问题
- **`update-ts [language]`**：使用源语言的新字符串更新 .ts 文件
- **`compile [language]`**：将 .ts 文件编译为二进制 .qm 格式

#### 高级命令
- **`auto-translate [language] --service [google|deepl|openai]`**：使用各种翻译服务自动翻译未完成的字符串
  - 支持 Google Translate、DeepL 和 OpenAI GPT 模型
  - 选项：`--api-key` 用于服务认证，`--model` 用于 OpenAI 模型选择，`--continue-on-failure` 用于跳过失败的翻译
- **`process [language] --service [google|deepl|openai]`**：一键工作流程，按顺序运行 update-ts → auto-translate → compile
  - 与 auto-translate 相同的选项：`--api-key`、`--model`、`--continue-on-failure`

### 命令示例

```bash
# 检查所有语言的完整性
python translation_helper.py check

# 检查特定语言
python translation_helper.py check zh_CN

# 查看所有语言的统计信息
python translation_helper.py stats

# 验证并自动修复所有语言
python translation_helper.py validate

# 更新所有语言的翻译文件
python translation_helper.py update-ts

# 使用 Google 自动翻译（免费，无需 API 密钥）
python translation_helper.py auto-translate zh_CN --service google

# 使用 DeepL 自动翻译（需要 API 密钥）
python translation_helper.py auto-translate zh_CN --service deepl --api-key YOUR_DEEPL_KEY

# 使用 OpenAI 自动翻译（需要 API 密钥）
python translation_helper.py auto-translate zh_CN --service openai --api-key YOUR_OPENAI_KEY --model gpt-4

# 一键完整工作流程
python translation_helper.py process zh_CN --service google

# 编译所有语言
python translation_helper.py compile
```

### 功能特性

- **批量操作**：大多数命令在未指定特定语言时支持对所有语言进行操作
- **自动修复验证**：validate 命令自动修复占位符和 HTML 标签不匹配问题
- **多种翻译服务**：支持 Google Translate（免费）、DeepL 和 OpenAI，可配置模型
- **错误处理**：强大的错误处理，包括重试逻辑和 Google Translate 的 SSL 修复
- **进度跟踪**：实时进度条和详细统计信息
- **缓存**：翻译缓存以避免重复的 API 调用
- **并发**：优化的并行处理以加快批量操作速度

具体使用方法请参见"[测试翻译](#步骤-5测试翻译)"部分。

## 快速开始

如果你只想快速开始翻译工作，可以按照以下简化流程：

1. **Fork 并克隆项目**
2. **设置开发环境**（按照[开发环境设置指南](development-setup.zh-cn.md)）
3. **选择语言文件**：打开 `locales/YOUR_LANGUAGE.ts`
4. **编辑翻译**：找到 `type="unfinished"` 的条目进行翻译
5. **自动翻译剩余字符串**（可选）：运行 `python translation_helper.py auto-translate YOUR_LANGUAGE --service google`
6. **编译测试**：运行 `python translation_helper.py compile YOUR_LANGUAGE`
7. **提交代码**：提交 `.ts` 和 `.qm` 文件

详细步骤请参考下面的完整指南。

## 如何贡献翻译

### 先决条件

在开始翻译工作之前，你需要准备以下内容：

1. **开发环境**（必需）
   - 按照 [开发环境设置指南](development-setup.zh-cn.md) 配置项目开发环境
   - 包括 Python 3.12、PySide6 以及项目依赖项的安装

2. **翻译编辑器**
   - **推荐**：支持 XML 语法高亮的文本编辑器（VS Code、Sublime Text、Notepad++ 等）
   - **可选**：Qt Linguist（专业的翻译工具，需要单独安装 Qt 开发环境）

3. **版本控制工具**
   - Git 版本控制系统
   - GitHub 账户用于贡献代码

### 步骤 1：设置环境

1. 在 GitHub 上 Fork RimSort 仓库
2. 克隆你的 fork：
   ```bash
   git clone https://github.com/YOUR_USERNAME/RimSort.git
   cd RimSort
   ```

3. 为你的翻译创建新分支：
   ```bash
   git checkout -b translation-LANGUAGE_CODE
   # 例如：git checkout -b translation-pt_BR
   ```

### 步骤 2：选择贡献类型

#### 选项 A：改进现有翻译
{: .no_toc}

1. 导航到 `locales/` 目录
2. 打开你的语言的现有 `.ts` 文件（例如 `zh_CN.ts`）
3. 查找标记为 `type="unfinished"` 或空的 `<translation>` 标签的条目

#### 选项 B：创建新语言翻译
{: .no_toc}

1. 使用 PySide6 工具生成新的翻译文件：

   **Linux/macOS 系统**：
   ```bash
   pyside6-lupdate $(find app -name "*.py") -ts locales/NEW_LANGUAGE_CODE.ts -no-obsolete
   # 例如：
   pyside6-lupdate $(find app -name "*.py") -ts locales/pt_BR.ts -no-obsolete
   ```

   **Windows 系统（推荐使用翻译助手工具）**：
   ```powershell
   # 使用翻译助手工具（推荐，更简单）
   python translation_helper.py update-ts pt_BR
   ```
   
   如果需要手动使用 PySide6 工具，可以参考 Linux/macOS 的命令格式，但建议使用翻译助手工具以避免复杂的路径处理。

2. 更新文件中的语言属性：
   ```xml
   <TS version="2.1" language="pt_BR">
   ```

3. 在语言控制器中注册新语言：
   
   打开 `app/controllers/language_controller.py` 文件，找到 `populate_languages_combobox` 方法中的 `language_map` 字典，添加你的语言：
   
   ```python
   language_map = {
       "en_US": "English",
       "es_ES": "Español", 
       "fr_FR": "Français",
       "de_DE": "Deutsch",
       "zh_CN": "简体中文",
       "ja_JP": "日本語",
       "pt_BR": "Português (Brasil)",  # 添加新语言条目
   }
   ```
   
   其中 `"pt_BR"` 是语言代码，`"Português (Brasil)"` 是在设置界面中显示的语言名称。

### 步骤 3：翻译过程

#### 使用文本编辑器（推荐）
{: .no_toc}

1. 在你喜欢的文本编辑器中打开 `.ts` 文件
2. 找到需要翻译的 `<message>` 块：
   ```xml
   <message>
       <location filename="../app/views/settings_dialog.py" line="896"/>
       <source>Select Language (Restart required to apply changes)</source>
       <translation type="unfinished"></translation>
   </message>
   ```

3. 用你的翻译内容替换空的翻译标签并删除 `type="unfinished"`：
   ```xml
   <message>
       <location filename="../app/views/settings_dialog.py" line="896"/>
       <source>Select Language (Restart required to apply changes)</source>
       <translation>选择语言（需要重启以应用更改）</translation>
   </message>
   ```

#### 使用 Qt Linguist（可选）
{: .no_toc}

如果你已经安装了 Qt Linguist，也可以使用它：

1. 打开 Qt Linguist
2. 文件 → 打开 → 选择你的 `.ts` 文件
3. 翻译每个字符串：
   - 从列表中选择未翻译的项目
   - 在"翻译"字段中输入你的翻译
   - 满意时标记为"完成"
   - 如需要可添加翻译者注释

4. 保存工作：文件 → 保存

### 步骤 4：翻译指南

#### 上下文理解
{: .no_toc}

每个可翻译字符串都有上下文信息：
- **文件名**：显示包含该字符串的文件
- **行号**：源代码中的确切位置
- **上下文名称**：通常是类名（例如"SettingsDialog"、"ModInfo"）

#### 翻译最佳实践
{: .no_toc}

1. **保留格式**：
   - 保持 `\n` 换行符
   - 维护 `%s`、`%d`、`{0}`、`{variable_name}` 占位符
   - 如果存在，保留 HTML 标签

2. **UI 界面考虑**：
   - 按钮标签保持简洁明了
   - 考虑文本长度变化（某些语言需要更多显示空间）
   - 保持与应用程序整体风格一致的语调

3. **技术术语处理原则**：
   - **"Mod"**：在所有语言中保持为"Mod"（已成为国际通用术语）
   - **"Workshop"**：可以翻译为本地化术语，也可保持原文
   - **软件特定术语**：保持一致性，建议先查看现有翻译作为参考
   - **UI 元素名称**：如"Settings"、"Options"等应翻译为对应语言
   - **文件格式和扩展名**：如".ts"、".qm"等保持原文

#### 翻译示例
{: .no_toc}

```xml
<!-- 英语源 -->
<source>Sort mods</source>
<translation>排序模组</translation>

<!-- 带占位符 -->
<source>Found {count} mods</source>
<translation>找到 {count} 个模组</translation>

<!-- 带换行符 -->
<source>Click OK to save settings
and restart the application</source>
<translation>点击确定保存设置
并重启应用程序</translation>
```

### 步骤 5：测试翻译

#### 5.1 验证翻译文件
{: .no_toc}

使用翻译助手工具进行文件验证：

```bash
# 检查特定语言的翻译完整性
python translation_helper.py check YOUR_LANGUAGE
# 例如：python translation_helper.py check zh_CN

# 验证翻译文件格式和内容
python translation_helper.py validate YOUR_LANGUAGE
# 检查占位符不匹配、HTML 标签问题等

# 查看所有语言的完成状态
python translation_helper.py stats
```

#### 5.2 编译和测试翻译
{: .no_toc}

1. **编译翻译文件**：
   ```bash
   # 使用翻译助手工具编译（推荐）
   python translation_helper.py compile YOUR_LANGUAGE
   # 例如：python translation_helper.py compile zh_CN
   
   # 或直接使用 PySide6 工具
   pyside6-lrelease locales/YOUR_LANGUAGE.ts
   ```

   **注意**：编译后会在 `locales/` 目录中生成对应的 `.qm` 文件。在本项目中，这些 `.qm` 文件也需要提交到版本控制系统中，以确保用户下载后可以直接使用翻译功能。

#### 5.3 在应用程序中测试
{: .no_toc}

1. **启动 RimSort 并切换语言**：
   - 运行 `python -m app` 启动应用程序
   - 点击菜单栏的"设置"或"Settings"
   - 找到"语言"或"Language"选项
   - 从下拉菜单中选择你的语言
   - 按提示重启应用程序以应用更改

2. **功能性测试**：
   - **主界面**：检查菜单栏、工具栏、状态栏的文本
   - **设置对话框**：验证所有选项和按钮都已翻译
   - **模组管理**：测试模组列表、排序、筛选功能的标签
   - **错误信息**：触发一些警告或错误，检查消息是否已翻译

3. **视觉检查**：
   - **文本适应性**：确保翻译文本能完全显示在 UI 元素中
   - **按钮尺寸**：检查按钮是否能容纳较长的翻译文本
   - **对话框布局**：验证对话框在显示翻译后尺寸仍然正常
   - **工具提示**：悬停在各个元素上检查工具提示翻译

### 步骤 6：提交贡献

1. **提交更改**：
   ```bash
   # 添加翻译文件（包括 .ts 源文件和编译后的 .qm 文件）
   git add locales/YOUR_LANGUAGE.ts
   git add locales/YOUR_LANGUAGE.qm
   # 如果添加了新语言，也要更新语言控制器
   git add app/controllers/language_controller.py
   git commit -m "添加/更新 [语言名称] 翻译"
   ```

   **注意**：在本项目中，需要同时提交 `.ts` 源文件和编译后的 `.qm` 文件，以确保用户可以直接使用翻译功能而无需额外的编译步骤。

2. **推送到你的 fork**：
   ```bash
   git push origin translation-LANGUAGE_CODE
   ```

3. **创建 Pull Request**：
   - 前往 GitHub 上你的 fork 页面
   - 点击"Compare & pull request"或"新建 Pull Request"
   - 选择你的翻译分支作为源分支
   - 在标题中明确标注语言，例如："添加巴西葡萄牙语翻译"或"更新简体中文翻译"
   - 在描述中详细说明：
     - 翻译的完成度（例如："完成了 80% 的字符串翻译"）
     - 主要更改内容
     - 是否需要进一步测试

**Pull Request 示例标题**：
- `添加法语翻译 (fr_FR)`
- `完善德语翻译 - 修复界面术语`
- `更新日语翻译 - 新增设置页面翻译`

## 翻译状态跟踪

你可以通过查找以下标记来检查翻译完整性：
- `type="unfinished"` 条目（需要翻译）
- 空的 `<translation></translation>` 标签
- `type="obsolete"` 条目（可能需要重新审查）

## 维护和更新

### 当源代码更新时

当 RimSort 的源代码更新后，可能会有新的可翻译字符串添加或现有字符串被修改。这时你需要更新翻译文件：

```bash
# 更新翻译文件以包含最新的可翻译字符串
python translation_helper.py update-ts YOUR_LANGUAGE
```

更新后，你只需要翻译新增的或被修改的字符串，已有的翻译内容会保持不变。

### 翻译文件格式
{: .no_toc}

`.ts` 文件使用 XML 格式，结构如下：
```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="LANGUAGE_CODE">
<context>
    <name>ClassName</name>
    <message>
        <location filename="../path/to/file.py" line="123"/>
        <source>English text</source>
        <translation>翻译文本</translation>
    </message>
</context>
</TS>
```

感谢你帮助让 RimSort 为全世界用户提供服务！🌍