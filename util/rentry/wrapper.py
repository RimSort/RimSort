import http.cookiejar
from http.cookies import SimpleCookie
from json import loads as json_loads
import sys
import urllib.parse
import urllib.request

from logger_tt import logger

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
            logger.info(
                "RentryUpload successfully uploaded data!\n\nUrl:        {}\nEdit code:  {}".format(
                    response["url"], response["edit_code"]
                )
            )

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


if __name__ == "__main__":
    sys.exit()
