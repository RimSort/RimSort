import base64
import json
import zlib
from unittest.mock import MagicMock, patch

from app.utils.privatebin import _build_paste_payload, upload_to_privatebin

FAKE_SERVER = "https://logs.example.com"


class TestBuildPastePayload:
    """Tests for the internal encryption + payload construction."""

    def test_returns_dict_with_required_keys(self) -> None:
        payload, paste_url_key = _build_paste_payload("hello world")
        assert "v" in payload
        assert payload["v"] == 2
        assert "adata" in payload
        assert "ct" in payload
        assert "meta" in payload
        assert payload["meta"] == {"expire": "6month"}

    def test_paste_url_key_is_nonempty_string(self) -> None:
        _, paste_url_key = _build_paste_payload("hello world")
        assert isinstance(paste_url_key, str)
        assert len(paste_url_key) > 0

    def test_adata_structure(self) -> None:
        payload, _ = _build_paste_payload("test content")
        adata = payload["adata"]
        # adata is a list of 4 elements
        assert len(adata) == 4
        # First element is crypto params list of 8
        crypto_params = adata[0]
        assert len(crypto_params) == 8
        assert crypto_params[2] == 100000  # iterations
        assert crypto_params[3] == 256  # key size
        assert crypto_params[4] == 128  # tag size
        assert crypto_params[5] == "aes"
        assert crypto_params[6] == "gcm"
        assert crypto_params[7] == "zlib"
        # Formatter, discussion, burn-after-reading
        assert adata[1] == "plaintext"
        assert adata[2] == 0
        assert adata[3] == 0

    def test_ciphertext_is_valid_base64(self) -> None:
        payload, _ = _build_paste_payload("some log data")
        ct = payload["ct"]
        decoded = base64.b64decode(ct)
        # Must be at least 16 bytes (GCM tag alone is 16)
        assert len(decoded) > 16

    def test_different_calls_produce_different_keys(self) -> None:
        _, key1 = _build_paste_payload("same text")
        _, key2 = _build_paste_payload("same text")
        assert key1 != key2

    def test_ciphertext_decrypts_correctly(self) -> None:
        """Round-trip: encrypt then decrypt to verify correctness."""
        import base58
        from Cryptodome.Cipher import AES
        from Cryptodome.Hash import HMAC, SHA256
        from Cryptodome.Protocol.KDF import PBKDF2

        plaintext = "test log content\nline 2\n"
        payload, paste_url_key = _build_paste_payload(plaintext)

        paste_key = base58.b58decode(paste_url_key)
        adata = payload["adata"]
        crypto_params = adata[0]

        iv = base64.b64decode(crypto_params[0])
        kdf_salt = base64.b64decode(crypto_params[1])

        key = PBKDF2(
            paste_key,
            kdf_salt,
            dkLen=32,
            count=100000,
            prf=lambda p, s: HMAC.new(p, s, SHA256).digest(),
        )

        ct_raw = base64.b64decode(payload["ct"])
        ciphertext = ct_raw[:-16]
        tag = ct_raw[-16:]

        adata_json = json.dumps(adata, separators=(",", ":")).encode()

        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        cipher.update(adata_json)
        compressed = cipher.decrypt_and_verify(ciphertext, tag)

        decompressed = zlib.decompress(compressed)
        paste_data = json.loads(decompressed)
        assert paste_data == [{"paste": plaintext}]


class TestUploadToPrivatebin:
    """Tests for the upload function with mocked HTTP."""

    @patch("app.utils.privatebin.http")
    @patch("app.utils.privatebin.AppInfo")
    def test_successful_upload_returns_url(
        self, mock_appinfo: MagicMock, mock_http: MagicMock
    ) -> None:
        mock_appinfo.return_value.app_version = "1.0.0"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 0,
            "id": "abc123",
            "url": f"{FAKE_SERVER}/?abc123",
            "deletetoken": "del456",
        }
        mock_http.post.return_value = mock_response

        success, url = upload_to_privatebin("test data", server=FAKE_SERVER)

        assert success is True
        assert url.startswith(f"{FAKE_SERVER}/?abc123#")
        assert len(url) > len(f"{FAKE_SERVER}/?abc123#")

        # Verify HTTP call
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[0][0] == FAKE_SERVER  # positional url arg
        headers = call_kwargs[1]["headers"]
        assert headers["X-Requested-With"] == "JSONHttpRequest"
        assert headers["Content-Type"] == "application/json"
        assert "RimSort/" in headers["User-Agent"]
        assert call_kwargs[1]["timeout"] == 60

    @patch("app.utils.privatebin.http")
    @patch("app.utils.privatebin.AppInfo")
    def test_server_error_status_returns_failure(
        self, mock_appinfo: MagicMock, mock_http: MagicMock
    ) -> None:
        mock_appinfo.return_value.app_version = "1.0.0"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 1,
            "message": "Rate limit exceeded",
        }
        mock_http.post.return_value = mock_response

        success, error = upload_to_privatebin("test data", server=FAKE_SERVER)

        assert success is False
        assert "Rate limit" in error

    @patch("app.utils.privatebin.http")
    @patch("app.utils.privatebin.AppInfo")
    def test_http_error_returns_failure(
        self, mock_appinfo: MagicMock, mock_http: MagicMock
    ) -> None:
        mock_appinfo.return_value.app_version = "1.0.0"
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http.post.return_value = mock_response

        success, error = upload_to_privatebin("test data", server=FAKE_SERVER)

        assert success is False
        assert "500" in error

    @patch("app.utils.privatebin.http")
    @patch("app.utils.privatebin.AppInfo")
    def test_connection_error_returns_failure(
        self, mock_appinfo: MagicMock, mock_http: MagicMock
    ) -> None:
        import requests

        mock_appinfo.return_value.app_version = "1.0.0"
        mock_http.post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        success, error = upload_to_privatebin("test data", server=FAKE_SERVER)

        assert success is False
        assert "Connection" in error or "refused" in error
