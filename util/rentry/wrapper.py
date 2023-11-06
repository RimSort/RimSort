import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from json import loads as json_loads
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from loguru import logger

_headers = {"Referer": "https://rentry.co"}


class UrllibClient:
    """Simple HTTP Session Client, keeps cookies."""

    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        urllib.request.install_opener(self.opener)

    def get(self, url, headers={}):
        request = urllib.request.Request(url, headers=headers)
        return self._request(request)

    def post(self, url, data=None, headers={}):
        postdata = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(url, postdata, headers)
        return self._request(request)

    def _request(self, request):
        response = self.opener.open(request)
        response.status_code = response.getcode()
        response.data = response.read().decode("utf-8")
        return response


class RentryUpload:
    """Uploader class to attempt to upload data to Rentry.co"""

    def __init__(self, text: str):
        response = self.new(text)
        if response["status"] != "200":
            self.upload_success = False
            self.url = None
            logger.error("error: {}".format(response["content"]))
            try:
                for i in response["errors"].split("."):
                    i and logger.warning(i)
                logger.error("RentryUpload failed!")
            except:
                logger.error("RentryUpload failed!")
        else:
            self.upload_success = True
            self.url = response["url"]
            logger.debug("RentryUpload successfully uploaded data!")
            logger.debug("Url: {}".format(self.url))
            logger.debug("Edit code: {}".format(response["edit_code"]))

    def new(self, text):
        client, cookie = UrllibClient(), SimpleCookie()

        cookie.load(vars(client.get("https://rentry.co"))["headers"]["Set-Cookie"])
        csrftoken = cookie["csrftoken"].value

        payload = {
            "csrfmiddlewaretoken": csrftoken,
            "text": text,
        }

        return json_loads(
            client.post("https://rentry.co/api/new", payload, headers=_headers).data
        )


class RentryImport(QDialog):
    def __init__(self):
        super().__init__()
        self.package_ids: list[str] = []  # Initialize an empty list to store package_ids
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self):
        logger.info("Rentry.co link Input UI initializing")
        self.setWindowTitle("Add Rentry.co link")

        layout = QVBoxLayout(self)

        self.link_input = QLineEdit(self)
        layout.addWidget(self.link_input)

        self.import_rentry_link_button = QPushButton("Import Rentry Link", self)
        self.import_rentry_link_button.clicked.connect(self.import_rentry_link)
        layout.addWidget(self.import_rentry_link_button)
        logger.info("Rentry.co link Input UI initialized successfully!")

    # Define the is_valid_rentry_link function within the class
    def is_valid_rentry_link(self, link):
        return link.startswith("https://rentry.co/")

    def import_rentry_link(self):
        logger.info("Import Rentry Link clicked")
        rentry_link = self.link_input.text()

        # Check if the input link is a valid Rentry link
        if not self.is_valid_rentry_link(rentry_link):
            logger.error("Invalid Rentry link. Please enter a valid Rentry link.")
            # Show an error message box
            error_message = "Invalid Rentry link. Please enter a valid Rentry link."
            QMessageBox.critical(self, "Invalid Link", error_message)
            return

        try:
            raw_url = rentry_link + "/raw"
            response = urllib.request.urlopen(raw_url)

            if response.getcode() == 200:
                page_content = response.read().decode("utf-8")
                pattern = r"\{packageid:\s*([\w.]+)\}|packageid:\s*([\w.]+)"
                matches = re.findall(pattern, page_content)
                self.package_ids = [
                    match[0] if match[0] else match[1]
                    for match in matches
                    if match[0] or match[1]
                ]
                logger.info("Parsed package_ids successfully.")

        except Exception as e:
            logger.error(
                f"An error occurred while fetching rentry.co content: {str(e)}"
            )

        # Close the dialog after processing
        self.accept()


if __name__ == "__main__":
    sys.exit()
