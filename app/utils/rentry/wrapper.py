import re
import sys
from json import loads as json_loads

import requests
from loguru import logger

from app.models.dialogue import show_dialogue_input, show_warning, show_fatal_error

# Constants
BASE_URL = "https://rentry.co"
BASE_URL_RAW = f"{BASE_URL}/raw"
API_NEW_ENDPOINT = f"{BASE_URL}/api/new"
_HEADERS = {"Referer": BASE_URL}


class HttpClient:
    def __init__(self):
        # Initialize a session for making HTTP requests
        self.session = requests.Session()

    def make_request(self, method, url, data=None, headers=None):
        # Perform a HTTP request and return the response
        headers = headers or {}
        request_method = getattr(self.session, method.lower())
        response = request_method(url, data=data, headers=headers)
        response.data = response.text
        return response

    def get(self, url, headers=None):
        return self.make_request("GET", url, headers=headers)

    def post(self, url, data=None, headers=None):
        return self.make_request("POST", url, data=data, headers=headers)

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
                    f"RentryUpload successfully uploaded data! Url: {self.url}, Edit code: {response['edit_code']}"
                )

    def handle_upload_failure(self, response):
        """
        Log and handle upload failure details.
        """
        error_content = response.get("content", "Unknown")
        errors = response.get("errors", "").split(".")
        logger.error(f"Error: {error_content}")
        for error in errors:
            error and logger.warning(error)
        show_fatal_error(
            title="Rentry Upload Error",
            text=f"Rentry.co upload failed! Error: {error_content}",
        )
        logger.error("RentryUpload failed!")

    def new(self, text):
        """
        Upload new entry to Rentry.co.
        """
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
        return json_loads(
            client.post(API_NEW_ENDPOINT, data=payload, headers=_HEADERS).data
        )


class RentryImport:
    """
    Class to handle importing Rentry.co links and extracting package IDs.
    """

    def __init__(self):
        """
        Initialize the Rentry Import instance.
        """
        self.package_ids: list[str] = (
            []
        )  # Initialize an empty list to store package_ids
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self):
        # Initialize the UI for entering Rentry.co links
        link_input = show_dialogue_input(
            title="Enter Rentry.co link",
            text="Enter the Rentry.co link:",
        )

        self.link_input = link_input
        self.import_rentry_link()
        logger.info("Rentry link Input UI initialized successfully!")

    def is_valid_rentry_link(self, link):
        """
        Check if the provided link is a valid Rentry link.
        """
        return link.startswith(BASE_URL) or link.startswith(BASE_URL_RAW)

    def import_rentry_link(self):
        """
        Import Rentry link and extract package IDs.
        """
        rentry_link = self.link_input[0]

        if not self.is_valid_rentry_link(rentry_link):
            logger.warning("Invalid Rentry link. Please enter a valid Rentry link.")
            # Show warning message box
            show_warning(
                title="Invalid Link",
                text="Invalid Rentry link. Please enter a valid Rentry link.",
            )
            return

        try:
            if rentry_link.endswith("/raw"):
                raw_url = rentry_link
            else:
                raw_url = f"{rentry_link}/raw"

            response = requests.get(raw_url)

            if response.status_code == 200:
                # Decode the content using UTF-8
                page_content = response.content.decode("utf-8")

                # Define regex pattern for both variations of 'packageid' and 'packageId'
                pattern = r"(?i){packageid:\s*([\w.]+)\}|packageid:\s*([\w.]+)"
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
            show_fatal_error(
                title="Error",
                text=f"An error occurred: {str(e)}",
            )


if __name__ == "__main__":
    sys.exit()
