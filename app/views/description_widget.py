import re

from PySide6.QtWidgets import (
    QTextBrowser,
    QWidget,
)


class DescriptionWidget(QTextBrowser):
    """
    Subclass for QTextBrowser. Creates a read-only
    text box for the mod info description.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.horizontalScrollBar().setValue(0)

        self.setObjectName("descriptionWidget")

    def setHtml(self, text: str) -> None:
        self.clear()
        self.insertHtml(text)

    def setText(self, text: str, convert: bool = False) -> None:
        if convert:
            text = self._convertUnityRichText(text)

        super().setText(text)

    def _convertUnityRichText(self, unity_text: str, remove_img: bool = True) -> str:
        """Helper function to convert Unity Rich Text to HTML.

        :param unity_text: The Unity Rich Text to convert.
        :type unity_text: str
        :param ignore_img: Whether or not to ignore image tags instead of converting them, defaults to True
        :type ignore_img: bool, optional
        :return: The converted HTML text.
        :rtype: str
        """
        tag_mapping_type1 = {
            r"\[b\]": "<strong>",
            r"\[/b\]": "</strong>",
            r"\[u\]": "<u>",
            r"\[/u\]": "</u>",
            r"\[i\]": "<em>",
            r"\[/i\]": "</em>",
            r"\[table\]": "<table>",
            r"\[/table\]": "</table>",
            r"\[tr\]": "<tr>",
            r"\[/tr\]": "</tr>",
            r"\[td\]": "<td>",
            r"\[/td\]": "</td>",
            r"\[list\]": '<ul style="white-space: normal">',
            r"\[/list\]": "</ul>",
            r"\[code\]": '<code style="white-space: pre-wrap">',
            r"\[/code\]": "</code>",
            r"\[hr\]": "<hr>",
            r"\[/hr\]": "",
            r"\[br\]": "<br>",
            r"\[p\]": "<p>",
            r"\[/p\]": "</p>",
            r"\[\*\]": "<li>",
            r"\[strike\]": "<strike>",
            r"\[/strike\]": "</strike>",
        }
        tag_mapping_type2 = {
            r"<color=(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)>": r'<span style="color:\1">',
            r"<color=\"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)\">": r'<span style="color:\1">',
            r"</color>": "</span>",
            r"<size=(\d+)>": r'<span style="font-size:\1px">',
            r"</size>": "</span>",
        }

        tag_mapping = {**tag_mapping_type1, **tag_mapping_type2}

        white_space = "pre-wrap"
        html_text = unity_text

        # If any tags of mapping type2 are found, set white-space to pre-wrap
        for unity_tag, _ in tag_mapping_type1.items():
            if re.search(unity_tag, unity_text):
                white_space = "normal"
                # Convert double \n to <br>
                html_text = html_text.replace("\n\n", "<br>")
                break

        # Map h tags like [h1] to <h1>
        for i in range(1, 7):
            tag_mapping[r"\[h" + str(i) + r"\]"] = "<h" + str(i) + ">"
            tag_mapping[r"\[/h" + str(i) + r"\]"] = "</h" + str(i) + ">"

        # Replace Unity tags with HTML tags
        for unity_tag, html_tag in tag_mapping.items():
            html_text = re.sub(unity_tag, html_tag, html_text)

        # [url] tags
        url_pattern = r"\[url=(.*?)\](.*?)\[/url\]"
        html_text = re.sub(url_pattern, r'<a href="\1">\2</a>', html_text)

        # Span text size
        span_size_pattern = r'<span style="font-size:(\d+)px">(.*?)</span>'
        html_text = re.sub(
            span_size_pattern, r'<span style="font-size:\1px">\2</span>', html_text
        )

        # Convert explicit string \n to <br>
        html_text = html_text.replace("\\n", "<br>")

        # Image tags
        img_pattern = r"\[img\](.*?)\[/img\]"
        html_text = re.sub(
            img_pattern, "" if remove_img else r'<img src="\1">', html_text
        )
        html_text = html_text.strip()

        # Remove empty tr, td, tables and lists if they exist
        html_text = re.sub(r"<table>\s*</table>", "", html_text)
        html_text = re.sub(r"<ul>\s*</ul>", "", html_text)

        # If there are any html tags, wrap with html
        if re.search(r"<[^>]+>", html_text):
            html_text = (
                f'<html style="white-space: {white_space}">' + html_text + "</html>"
            )

        return html_text
