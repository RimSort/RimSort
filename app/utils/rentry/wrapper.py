import os
import re
import sys
from json import loads as json_loads
from typing import Any

import requests
from loguru import logger
from PySide6.QtWidgets import QMessageBox

from app.views.dialogue import (
    InformationBox,
    show_dialogue_input,
    show_fatal_error,
    show_warning,
)

# Constants for Rentry API endpoints
BASE_URL = "https://rentry.co"
API_NEW_ENDPOINT = f"{BASE_URL}/api/new"
RENTRY_RAW_AUTH = os.getenv("RENTRY_RAW_AUTH", "")  # Provided with every build, if using interpreter set it manually using your own auth code
_HEADERS = {
    "Referer": BASE_URL,
    "rentry-auth": RENTRY_RAW_AUTH,  # This header allows access to /raw endpoint
}


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
                title="Error",
                text=f"An error occurred: {str(e)}",
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

    def __init__(self) -> None:
        """Initialize the Rentry Import instance and prompt for a link."""
        self.package_ids: list[
            str
        ] = []  # Initialize an empty list to store package IDs
        if RENTRY_RAW_AUTH == "":
            logger.debug("Rentry Raw Auth is blank.")
        else:
            logger.debug("Rentry Raw Auth is set.")
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self) -> None:
        """Initialize the UI for entering Rentry.co links."""
        self.link_input = show_dialogue_input(
            title="Enter Rentry.co link",
            label="Enter the Rentry.co link:",
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
                title="Invalid Rentry Link",
                text="Invalid Rentry link, Please enter a valid Rentry link.",
            )
            return self.input_dialog()  # Re-initialize the UI for new input

        try:
            # Determine the raw URL based on the provided link
            raw_url = (
                rentry_link if rentry_link.endswith("/raw") else f"{rentry_link}/raw"
            )
            response = requests.get(raw_url, headers=_HEADERS)  # Fetch the content from the raw URL

            if response.status_code == 200:
                # Decode the content using UTF-8
                page_content = response.content.decode("utf-8")

                # Define regex pattern for both variations of 'packageid' and 'packageId'
                pattern = r"(?i){packageid:\s*([\w.]+)\}|packageid:\s*([\w.]+)"
                matches = re.findall(pattern, page_content)
                # Find all matches in the content
                self.package_ids = [
                    match[0] if match[0] else match[1]
                    for match in matches
                    if match[0] or match[1]
                ]
                logger.info("Parsed package_ids successfully.")
                logger.debug(f"Number of package_ids found: {str(len(self.package_ids))}")
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
                title="Error",
                text=f"An error occurred: {str(e)}",
            )


class RentryError:
    """Class to handle errors related to Rentry operations."""

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
            title="Failed to fetch Rentry Content",
            text=f"Rentry returned status code: {response.status_code}",
            information="RimSort failed to fetch the content from the provided Rentry link. This may be due to an invalid link, your internet connection, or Rentry.co being down. It may also be the result of a captcha. Please try again later.",
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
            title="Network Error",
            text="Network error occurred while processing Rentry, Please check your internet connection.",
            details=f"{str(e)}",
        )
        return None  # Return None to indicate failure


if __name__ == "__main__":
    sys.exit()
