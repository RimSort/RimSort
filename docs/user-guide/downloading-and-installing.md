---
title: Downloading and Installing
parent: User Guide
nav_order: 1
---

# Downloading and Installing
{: .no_toc}

{: .warning }

> Most users should be utilizing [pre-built releases](https://github.com/RimSort/RimSort/releases) and **_not_** downloading the repository code from `Code > Download ZIP`. This option downloads the source code which is not compiled. You only need the source code if you plan on contributing, building RimSort yourself, or running RimSort via a Python interpreter.

There are two types of RimSort releases. Stable releases, and edge releases. Edge releases come out much more often then stable releases, but are more likely to have bugs.

When downloading a release, make sure to select the file more appropriate for your operating system, CPU architecture, and needs. Launch instructions may be platform specific.

[Stable Release][Stable Release]{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[Edge Release][Edge Release]{: .btn .fs-5 .mb-4 .mb-md-0 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Windows
{: .d-inline-block}

Windows
{: .label .label-blue }

{: .important }
> On Windows, the executable RimSort.exe may sometimes be incorrectly flagged by your anti-virus solution such as Windows Defender and deleted.
>
> Unfortunately this is a side effect of using [Nuikta](https://nuitka.net/) to compile a Python program into an easy to distribute executable, and not signing it. Signing the release costs a significant amount of money and is a re-occuring cost which is infeasible for us. It is safe to override your anti-virus to allow RimSort. If you are unsure about this, feel free to scan the executable using [Virus Total](https://www.virustotal.com/gui/) which will give you the opinion of multiple anti-virus solutions and then form your own opinion.



- Download and extract the `Windows x86-64` release
- Run the executable: `RimSort.exe`

![](../../assets/images/previews/windows_preview.png)

## macOS
{: .d-inline-block}

macOS
{: .label .label-red }

{: .important }
> You may get an error saying that RimSort is "damaged" from Gatekeeper.
> Apple has it's own Runtime Protection called [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web) that can cause issues when trying to run RimSort (or execute dependent libs)!
> You can circumvent this issue by using `xattr` command to manually whitelist:
>
>     xattr -d com.apple.quarantine RimSort.app
>     xattr -d com.apple.quarantine libsteam_api.dylib
> 
> If you are for some reason trying to run the `i386` build on Apple silicon, don't enable watchdog when running the build through Rosetta

{: .note }

> todds texture tool does not currently (as of May 2023) support Apple silicon (Mac M1/M2 ARM64 CPU).

- Download the and extract the Darwin/macOS release that matches your CPU architecture (ARM64 for Apple Silicon, i386 for Intel)
- Use the `xattr` command to circumvent [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web) and whitelist `RimSort.app` and `libsteam_api.dylib`
- Open the app bundle: `RimSort.app`

<img alt="Macpreview" src="https://github.com/RimSort/RimSort/assets/28567881/7731911b-cc7c-47c8-9c34-6f925fc5b188">

## Linux
{: .d-inline-block}

Linux
{: .label .label-yellow}

{: .warning }

> Certain Linux distros/flavors may not have all the required shared libraries for QT, the graphics library that RimSort uses. Namely, `xcb/libxcb`. If you get an error about loading these when attempting to launch RimSort, you will need to install one or the other. Even after installing the library, there may be additional files that are missing that need to be downloaded separately. For example, `libxcb-cursor-dev`
> 
> The easiest way to find what package has the library you need is the command `apt-file`.
>
> A mismatch of kernel versions may lead to version errors for shared libraries such as `glibc`

{: .important }

> We only release compiled releases for Ubuntu. If you use a different distribution or a special flavor, you may run into unexpected issues. If none of our offered pre-built releases work for you, you may need to [build RimSort yourself from the source code, or run RimSort from the Python interpreter]({% link development-guide/development-setup.md%}).



- Download and extract the appropriate Linux release
- Run the executable: `./RimSort`

<img alt="Linuxpreview" src="https://github.com/RimSort/RimSort/assets/102756485/d26577e4-d488-406b-b9a2-dc2eeea8de25">

[Releases]: https://github.com/oceancabbage/RimSort/releases
[Stable Release]: https://github.com/oceancabbage/RimSort/releases/latest
[Edge Release]: https://github.com/RimSort/RimSort/releases/tag/Edge
