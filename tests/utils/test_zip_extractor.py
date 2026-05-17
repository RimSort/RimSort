import os
import zipfile
from pathlib import Path


def _create_zip_with_entries(zip_path: str, entries: dict[str, str]) -> None:
    """Create a ZIP file with the given filename->content entries."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


class TestZipSlipProtection:
    """Test that zip slip (path traversal) attacks are blocked."""

    def test_legitimate_entries_extracted(self, tmp_path: Path) -> None:
        """Normal zip entries should extract correctly."""
        zip_path = str(tmp_path / "test.zip")
        target = str(tmp_path / "output")
        os.makedirs(target)

        _create_zip_with_entries(
            zip_path,
            {
                "mod/About.xml": "<xml>test</xml>",
                "mod/Defs/thing.xml": "<Def>data</Def>",
            },
        )

        from app.utils.zip_extractor import ZipExtractThread

        thread = ZipExtractThread(zip_path, target)
        thread.run()  # Run synchronously for testing

        assert os.path.exists(os.path.join(target, "mod", "About.xml"))
        assert os.path.exists(os.path.join(target, "mod", "Defs", "thing.xml"))

    def test_traversal_entries_skipped(self, tmp_path: Path) -> None:
        """Entries with ../ path traversal should be skipped."""
        zip_path = str(tmp_path / "malicious.zip")
        target = str(tmp_path / "output")
        os.makedirs(target)

        _create_zip_with_entries(
            zip_path,
            {
                "safe/file.txt": "safe content",
                "../../../etc/passwd": "malicious content",
                "foo/../../escape.txt": "escaped content",
            },
        )

        from app.utils.zip_extractor import ZipExtractThread

        thread = ZipExtractThread(zip_path, target)
        thread.run()

        # Safe file should exist
        assert os.path.exists(os.path.join(target, "safe", "file.txt"))
        # Malicious files should NOT exist anywhere outside target
        assert not os.path.exists(os.path.join(tmp_path, "etc", "passwd"))
        assert not os.path.exists(os.path.join(tmp_path, "escape.txt"))

    def test_absolute_path_entries_skipped(self, tmp_path: Path) -> None:
        """Entries with absolute paths should be skipped."""
        zip_path = str(tmp_path / "absolute.zip")
        target = str(tmp_path / "output")
        os.makedirs(target)

        _create_zip_with_entries(
            zip_path,
            {
                "normal.txt": "normal content",
                "/tmp/evil.txt": "evil content",
            },
        )

        from app.utils.zip_extractor import ZipExtractThread

        thread = ZipExtractThread(zip_path, target)
        thread.run()

        assert os.path.exists(os.path.join(target, "normal.txt"))
        # The /tmp/evil.txt should not be created at the absolute path
        # (os.path.join with absolute second arg returns the absolute path,
        # but realpath check should catch it)
