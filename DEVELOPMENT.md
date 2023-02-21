## Development

#### Introduction

RimSort is built in Python using the [PySide2](https://pypi.org/project/PySide2/) library and packaged for Mac, Linux, and Windows.

#### Prerequisites

* [Python](https://www.python.org/): programming language used to develop RimSort. Install version `3.9.6` if possible. You can do this by first installing [HomeBrew](https://docs.brew.sh/Installation) and then running `brew install python@3.9`.
* [PySide2](https://pypi.org/project/PySide2/): GUI toolkit for building the application. Install version `5.15.2.1` if possible. You can do this by running `pip3 install PySide2==5.15.2.1`.
* [PyInstaller](https://pyinstaller.org/en/stable/): packages application for distribution. Install version `5.7.0` if possible. You can do this by running `pip3 install PyInstaller==5.7.0`.
* [xmltodict](https://pypi.org/project/xmltodict/): parse RimWorld `xml` files. Install version `0.13.0` if possible. You can do this by running `pip3 install xmltodict==0.13.0`.
* [toposort](https://pypi.org/project/toposort/): sort mods! Install version `1.9` if possible. You can do this by running `pip3 install toposort==1.9`.

You can install all of the above dependencies by executing the command at the project root: 

`pip install -r requirements.txt`

#### Running the App

First, clone this repository to a local directory.
Then, from the project root, execute `python3 app.py`

#### Packaging the App

First, clone this repository to a local directory.

* Packaging with `pyinstaller`: 
    * From the project root, execute `pyinstaller app.spec app.py` - this will compile a binary release for your platform.
    * You can find the bundled application by navigating to `./dist/app.app`

#### Developing Features

Please discuss with maintainers first, but we are tracking features and issues related to RimSort in the Github repo's "Issues" tab

#### Misc Coding Style

* The preferred Python formatter is: black (`pip3 install black`)
* The preferred Docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
* Type annotations should be added to function/method signatures
