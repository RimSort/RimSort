import re
import sys
from json import loads as json_loads

import requests
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    )
from loguru import logger

# Constants
BASE_URL = "https://rentry.co"
API_NEW_ENDPOINT = f"{BASE_URL}/api/new"

_HEADERS = {"Referer": BASE_URL}


class HttpClient:
    def __init__(self):
        # Initialize a session for making HTTP requests
        self.session = requests.Session()

    def get(self, url, headers=None):
        # Perform a GET request and return the response
        headers = headers or {}
        response = self.session.get(url, headers=headers)
        response.data = response.text
        return response

    def post(self, url, data=None, headers=None):
        # Perform a POST request and return the response
        headers = headers or {}
        response = self.session.post(url, data=data, headers=headers)
        response.data = response.text
        return response

    def get_csrf_token(self):
        # Get CSRF token from the response cookies after making a GET request to the base URL
        response = self.get(BASE_URL)
        return response.cookies.get("csrftoken")


class RentryUpload:
    def __init__(self, text: str):
        self.upload_success = False
        self.url = None

        try:
            response = self.new(text)
            if response.get("status") != "200":
                self.handle_upload_failure(response)
            else:
                self.upload_success = True
                self.url = response["url"]
        finally:
            if self.upload_success:
                logger.debug(
                    f"RentryUpload successfully uploaded data! Url: {self.url}, Edit code: {response['edit_code']}")

    def handle_upload_failure(self, response):
        error_content = response.get("content", "Unknown")
        errors = response.get("errors", "").split(".")
        logger.error(f"Error: {error_content}")
        for error in errors:
            error and logger.warning(error)
        logger.error("RentryUpload failed!")

    def new(self, text):
        # Initialize an HttpClient for making HTTP requests
        client = HttpClient()

        # Get CSRF token for authentication
        csrf_token = client.get_csrf_token()

        # Prepare payload for the POST request
        payload = {
            "csrfmiddlewaretoken": csrf_token,
            "text": text,
            }

        # Perform the POST request to create a new entry
        return json_loads(client.post(API_NEW_ENDPOINT, payload, headers=_HEADERS).data)


class RentryImport(QDialog):
    def __init__(self):
        super().__init__()
        self.package_ids: list[str] = []  # Initialize an empty list to store package_ids
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self):
        # Initialize the UI for entering Rentry.co links
        logger.info("Rentry.co link Input UI initializing")
        self.setWindowTitle("Add Rentry.co link")

        layout = QVBoxLayout(self)

        self.link_input = QLineEdit(self)
        layout.addWidget(self.link_input)

        self.import_rentry_link_button = QPushButton("Import Rentry Link", self)
        self.import_rentry_link_button.clicked.connect(self.import_rentry_link)
        layout.addWidget(self.import_rentry_link_button)
        logger.info("Rentry.co link Input UI initialized successfully!")

    def is_valid_rentry_link(self, link):
        # Check if the provided link is a valid Rentry link
        return link.startswith(BASE_URL)

    def import_rentry_link(self):
        # Handle the import button click event
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
            raw_url = f"{rentry_link}/raw"
            response = requests.get(raw_url)

            if response.status_code == 200:
                # Decode the content using UTF-8
                page_content = response.content.decode("utf-8")
                pattern = r"\{packageid:\s*([\w.]+)\}|packageid:\s*([\w.]+)"
                matches = re.findall(pattern, page_content)
                self.package_ids = [
                    match[0] if match[0] else match[1]
                    for match in matches
                    if match[0] or match[1]
                    ]
                logger.info("Parsed package_ids successfully.")
        except Exception as e:
            logger.error(f"An error occurred while fetching rentry.co content: {str(e)}")

        # Close the dialog after processing the link
        self.accept()


if __name__ == "__main__":
    sys.exit()
