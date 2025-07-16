import re
import sys
from json import loads as json_loads
from typing import Any

import requests
from loguru import logger
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox

from app.controllers.settings_controller import SettingsController
from app.views.dialogue import (
    InformationBox,
    show_dialogue_input,
    show_fatal_error,
    show_warning,
)

# Constants for Rentry API endpoints
BASE_URL = "https://rentry.co"
API_NEW_ENDPOINT = f"{BASE_URL}/api/new"
_HEADERS = {
    "Referer": BASE_URL,
    "rentry-auth": "",  # This header allows access to /raw endpoint. Updated with auth code from user settings
}

translate = QCoreApplication.translate


class HttpClient:
    """A simple HTTP client for making requests to the Rentry API."""

    def __init__(self) -> None:
        """Initialize a session for making HTTP requests."""
        self.session = requests.Session()

    def make_request(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """
        Perform an HTTP request and return the response.

        Args:
            method (str): The HTTP method (GET, POST, etc.).
            url (str): The URL for the request.
            data (dict | None): Optional data to send with the request.
            headers (dict | None): Optional headers to include in the request.

        Returns:
            requests.Response: The response object from the request.
        """
        headers = headers or {}
        request_method = getattr(self.session, method.lower())
        response = request_method(url, data=data, headers=headers)
        response.data = response.text  # Store the response text for convenience
        return response

    def get(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        """Perform a GET request."""
        return self.make_request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """Perform a POST request."""
        return self.make_request("POST", url, data=data, headers=headers)

    def get_csrf_token(self) -> str | None:
        """
        Get CSRF token from the response cookies after making a GET request to the base URL.

        Returns:
            str | None: The CSRF token if available, otherwise None.
        """
        response = self.get(BASE_URL)
        return response.cookies.get("csrftoken")


class RentryUpload:
    """Class to handle uploading text to Rentry.co."""

    def __init__(self, text: str) -> None:
        """
        Initialize the RentryUpload instance and attempt to upload the provided text.

        Args:
            text (str): The text content to upload to Rentry.co.
        """
        self.upload_success = False
        self.url = None

        try:
            response = self.new(text)  # Attempt to upload the text
            self.handle_response(response)  # Handle the response from the upload
        except requests.RequestException as e:
            # Handle any exceptions that occur during the process
            RentryError().show_request_exception(e)
        except Exception as e:
            # Handle any other exceptions that occur during the process
            logger.error(
                f"An error occurred while Uploading rentry.co content: {str(e)}"
            )
            show_fatal_error(
                title=translate("RentryUpload", "Error"),
                text=translate("RentryUpload", "An error occurred: {e}").format(
                    e=str(e)
                ),
            )

    def handle_response(self, response: dict[str, Any]) -> None:
        """
        Handle the response from the upload attempt.

        Args:
            response (dict): The response dictionary from the upload attempt.
        """
        if response.get("status") == "200":
            self.upload_success = True
            self.url = response.get("url")  # Extract the URL from the response

            if self.upload_success:
                logger.debug(
                    f"RentryUpload successfully uploaded data! Url: {self.url}, Edit code: {response['edit_code']}"
                )
            else:
                # Handle upload failure
                RentryError().handle_upload_failure(response)

    def new(self, text: str) -> Any:
        """
        Upload a new entry to Rentry.co.

        Args:
            text (str): The text content to upload.

        Returns:
            Any: Parsed response from the upload attempt.
        """
        client = HttpClient()  # Initialize an HttpClient for making requests
        csrf_token = client.get_csrf_token()  # Get CSRF token for authentication

        # Prepare payload for the POST request
        payload = {
            "csrfmiddlewaretoken": csrf_token,
            "text": text,
        }

        # Perform the POST request to create a new entry
        response = client.post(API_NEW_ENDPOINT, data=payload, headers=_HEADERS)
        return json_loads(response.text)  # Parse and return the JSON response


class RentryImport:
    """Class to handle importing Rentry.co links and extracting package IDs."""

    def __init__(
        self, settings_controller: SettingsController, rentry_auth_code: bool = False
    ) -> None:
        """Initialize the Rentry Import instance and prompt for a link."""
        self.package_ids: list[
            str
        ] = []  # Initialize an empty list to store package IDs
        self.publishedfileids: list[
            str
        ] = []  # Initialize an empty list for publishedfileids
        self.settings_controller = settings_controller
        self.rentry_auth_code = rentry_auth_code

        # If user does not have an auth code, show a warning
        if settings_controller.settings.rentry_auth_code == "":
            self.rentry_auth_code = False
            RentryError().show_missing_rentry_auth_warning()
            self.input_dialog()  # Call the input_dialog method to set up the UI
        else:
            # Retrieve auth code from user settings
            _HEADERS.update(
                {"rentry-auth": settings_controller.settings.rentry_auth_code}
            )
            self.rentry_auth_code = True
            self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self) -> None:
        """Initialize the UI for entering Rentry.co links."""
        self.link_input = show_dialogue_input(
            title=translate("RentryImport", "Enter Rentry.co link"),
            label=translate("RentryImport", "Enter the Rentry.co link:"),
        )
        logger.info("Rentry link Input UI initialized successfully!")
        if self.link_input[1]:
            self.import_rentry_link()  # Proceed to import the link if user input is valid
        else:
            logger.info("User exited rentry import window.")

    def is_valid_rentry_link(self, link: str) -> bool:
        """
        Check if the provided link is a valid Rentry link.

        Args:
            link (str): The link to validate.

        Returns:
            bool: True if the link is valid, False otherwise.
        """
        return link.startswith(BASE_URL) or link.startswith(f"{BASE_URL}/raw")

    def import_rentry_link(self) -> None:
        """
        Import Rentry link and extract package IDs from the content.
        """
        rentry_link = self.link_input[0]  # Get the link from user input

        if not self.is_valid_rentry_link(rentry_link):
            logger.warning("Invalid Rentry link. Please enter a valid Rentry link.")
            # Show warning if rentry link is invalid
            show_warning(
                title=translate("RentryImport", "Invalid Rentry Link"),
                text=translate(
                    "RentryImport",
                    "Invalid Rentry link, Please enter a valid Rentry link.",
                ),
            )
            return self.input_dialog()  # Re-initialize the UI for new input

        try:
            # Determine the raw URL based on the provided link
            if self.rentry_auth_code:
                logger.debug("Using rentry-auth code to fetch rentry.co content.")
                raw_url = (
                    rentry_link
                    if rentry_link.endswith("/raw")
                    else f"{rentry_link}/raw"
                )
                response = requests.get(
                    raw_url, headers=_HEADERS
                )  # Fetch the content from the raw URL
            else:
                logger.debug("Fetching rentry.co content without rentry-auth.")
                raw_url = (
                    rentry_link
                    if rentry_link.endswith("/edit")
                    else f"{rentry_link}/edit"
                )
                response = requests.get(raw_url)  # Fetch the content from the edit URL

            if response.status_code == 200:
                # Decode the content using UTF-8
                page_content = response.content.decode("utf-8")
                logger.debug(
                    f"Fetched rentry.co content successfully. Content: {page_content}"
                )

                # Define regex pattern for both variations of 'packageid' and 'packageId'
                packageid_pattern = (
                    r"(?i){packageid:\s*([\w.]+)\}|packageid:\s*([\w.]+)"
                )
                matches = re.findall(packageid_pattern, page_content)
                # Find all matches in the content
                self.package_ids = [
                    match[0] if match[0] else match[1]
                    for match in matches
                    if match[0] or match[1]
                ]
                logger.info("Parsed package_ids successfully.")
                logger.debug(
                    f"Number of package_ids found: {str(len(self.package_ids))}"
                )
                # Define regex pattern for publishedfileid in format '?id=digits'
                publishedfileid_pattern = r"\?id=(\d+)"
                # Find all publishedfileid matches in the content
                self.publishedfileids = re.findall(
                    publishedfileid_pattern, page_content
                )
                logger.info("Parsed publishedfileid successfully.")
                logger.debug(
                    f"Number of publishedfileid found: {str(len(self.publishedfileids))}"
                )
            else:
                # Handle non-200 responses
                RentryError().show_response_error(response)

        except requests.RequestException as e:
            # Handle any exceptions that occur during the process
            RentryError().show_request_exception(e)
        except Exception as e:
            # Handle any other exceptions that occur during the process
            logger.error(
                f"An error occurred while fetching rentry.co content: {str(e)}"
            )
            show_fatal_error(
                title=translate("RentryImport", "Error"),
                text=translate("RentryImport", "An error occurred: {e}").format(
                    e=str(e)
                ),
            )


class RentryError:
    """Class to handle errors and warnings related to Rentry operations."""

    def handle_upload_failure(self, response: dict[str, Any]) -> None:
        """
        Log and handle upload failure details.

        Args:
            response (dict[str, Any]): A dictionary containing the response details from the upload attempt.
        """
        error_content = response.get("content", "Unknown")  # Extract error content
        errors = [
            error.strip()
            for error in response.get("errors", "").split(".")
            if error.strip()
        ]

        logger.error(
            f"Rentry upload process failed with Error: {error_content}"
        )  # Log main error

        if errors:
            for error in errors:
                logger.error(f"Detail: {error}")  # Log individual errors
        else:
            logger.error("No specific error details available.")

        logger.error(
            f"Rentry.co upload failed! Error: {error_content}. Details: {', '.join(errors) if errors else 'None'}"
        )

    def show_response_error(self, response: requests.Response) -> None:
        """
        Show information about a failed fetch attempt.

        Args:
            response (requests.Response): The response object containing status code and reason.
        """
        logger.warning(
            f"Rentry returned status code: {response.status_code}. Reason: {response.reason}"
        )
        InformationBox(
            title=translate("RentryError", "Failed to fetch Rentry Content"),
            text=translate("RentryError", "Rentry returned status code: {code}").format(
                code=response.status_code
            ),
            information=translate(
                "RentryError",
                "RimSort failed to fetch the content from the provided Rentry link. This may be due to an invalid link, your internet connection, or Rentry.co being down. It may also be the result of a captcha. Please try again later.",
            ),
            details=response.reason,
            icon=QMessageBox.Icon.Warning,
        ).exec()

    def show_request_exception(self, e: requests.RequestException) -> None:
        """
        Show a warning for network errors.

        Args:
            e (Exception): The exception that occurred during the network operation.
        """
        logger.error(f"A network error occurred while processing Rentry: {str(e)}")
        show_warning(
            title=translate("RentryError", "Network Error"),
            text=translate(
                "RentryError",
                "Network error occurred while processing Rentry, Please check your internet connection.",
            ),
            details=f"{str(e)}",
        )
        return None  # Return None to indicate failure

    def show_missing_rentry_auth_warning(self) -> None:
        """Show a warning for missing Rentry Auth code."""
        logger.info("Rentry Auth code not found in user settings.")
        show_warning(
            title=translate("RentryError", "Rentry Auth Code Not Found"),
            text=translate(
                "Rentry Auth Code Not Found ",
                "RimSort can work without rentry auth code. But "
                "To enable full functionality of renry.co you need to email support@rentry.co and request an auth code. "
                "Then paste it into Settings -> Advanced -> Rentry Auth.",
            ),
        )


if __name__ == "__main__":
    sys.exit()
