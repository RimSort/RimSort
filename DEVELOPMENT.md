## Development

#### Introduction

RimSort is built in Python using the [PySide2](https://pypi.org/project/PySide2/) library and packaged for Mac, Linux, and Windows.

#### Prerequisites

* [Python](https://www.python.org/): programming language used to develop RimSort. Install version `3.9.6` if possible. You can do this by first installing [HomeBrew](https://docs.brew.sh/Installation) and then running `brew install python@3.9`.
* [PySide2](https://pypi.org/project/PySide2/): GUI toolkit for building the application. Install version `5.15.2.1` if possible. You can do this by running `pip3 install PySide2==5.15.2.1`.
* [PyInstaller](https://pyinstaller.org/en/stable/): packages application for distribution. Install version `5.7.0` if possible. You can do this by running `pip3 install PyInstaller==5.7.0`.
* [xmltodict](https://pypi.org/project/xmltodict/): parse RimWorld `xml` files. Install version `0.13.0` if possible. You can do this by running `pip3 install xmltodict==0.13.0`.

#### Running the App

First, clone this repository to a local directory.
Inside the local directory, run `python3 app.py`.

#### Packaging the App

First, clone this repository to a local directory.

* Packaging for mac: inside the local directory, run `pyinstaller --clean --windowed --noconfirm app.py`. Open the newly bundled app by going opening `./dist/app.app`.

#### Developing Features



#### Misc Coding Style

* The preferred Python formatter is: black (`pip3 install black`)
* The preferred Docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
* Type annotations should be added to function/method signatures
