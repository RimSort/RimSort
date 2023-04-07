from functools import partial
from logger_tt import logger
import os
import platform

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QLineEdit,
    QSizePolicy,
    QToolBar,
    QWidget,
    QVBoxLayout,
)




class WebContentPanel(QWidget):
    """
    A generic panel used to browse web content
    """

    def __init__(self, startpage: str):
        super().__init__()
        logger.info("Initializing WebContentPanel")
        # https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support
        if platform.system() != "Windows":
            logger.info("Setting QTWEBENGINE_DISABLE_SANDBOX for non-Windows platform")
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

        self.location = QLineEdit(startpage)
        self.location.setSizePolicy(
            QSizePolicy.Expanding, self.location.sizePolicy().verticalPolicy()
        )
        self.location.returnPressed.connect(
            partial(self._changeLocation, self.location.text())
        )

        self.nav_bar = QToolBar()

        self.web_view = QWebEngineView()
        self._changeLocation(startpage)

        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Back))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Forward))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Stop))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Reload))
        self.nav_bar.addSeparator()

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.location)
        self.layout.addWidget(self.nav_bar)
        self.layout.addWidget(self.web_view)

        self.setLayout(self.layout)
        self.resize(800, 600)

    def _changeLocation(self, location: str):
        self.location.setText(location)
        self.web_view.load(QUrl(location))
