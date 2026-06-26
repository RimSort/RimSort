"""PrivateBin v2 client with client-side encryption.

Implements the PrivateBin v2 encryption format (AES-256-GCM + PBKDF2)
for uploading pastes where the server has zero knowledge of the content.
"""

import base64
import json
import secrets
import zlib
from typing import Any

import base58
import requests
from Cryptodome.Cipher import AES
from Cryptodome.Hash import HMAC, SHA256
from Cryptodome.Protocol.KDF import PBKDF2
from loguru import logger

from app.utils import http
from app.utils.app_info import AppInfo

_KDF_ITERATIONS = 100000
_KDF_KEY_SIZE = 256
_GCM_TAG_SIZE = 128
_EXPIRATION = "6month"


def _build_paste_payload(text: str) -> tuple[dict[str, Any], str]:
    """
    Encrypt text using PrivateBin v2 format and return the API payload.

    :param text: The plaintext content to encrypt
    :return: (payload_dict, base58_paste_key) ready for POST + URL construction
    """
    paste_key = secrets.token_bytes(32)
    iv = secrets.token_bytes(16)
    kdf_salt = secrets.token_bytes(8)

    def _hmac_sha256(password: bytes, salt: bytes) -> bytes:
        return HMAC.new(password, salt, SHA256).digest()

    key = PBKDF2(
        paste_key,  # type: ignore[arg-type]
        kdf_salt,
        dkLen=32,
        count=_KDF_ITERATIONS,
        prf=_hmac_sha256,  # type: ignore[arg-type]
    )

    adata: list[Any] = [
        [
            base64.b64encode(iv).decode(),
            base64.b64encode(kdf_salt).decode(),
            _KDF_ITERATIONS,
            _KDF_KEY_SIZE,
            _GCM_TAG_SIZE,
            "aes",
            "gcm",
            "zlib",
        ],
        "plaintext",
        0,
        0,
    ]

    paste_blob = json.dumps([{"paste": text}]).encode()
    compressed = zlib.compress(paste_blob)

    adata_json = json.dumps(adata, separators=(",", ":")).encode()

    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    cipher.update(adata_json)
    ciphertext, tag = cipher.encrypt_and_digest(compressed)

    ct_b64 = base64.b64encode(ciphertext + tag).decode()

    payload = {
        "v": 2,
        "adata": adata,
        "ct": ct_b64,
        "meta": {"expire": _EXPIRATION},
    }

    paste_url_key = base58.b58encode(paste_key).decode("ascii")

    return payload, paste_url_key


def upload_to_privatebin(
    text: str,
    server: str = "https://logs.rimsort.dev",
) -> tuple[bool, str]:
    """
    Upload text to a PrivateBin v2 instance with client-side encryption.

    :param text: The plaintext content to upload
    :param server: The PrivateBin server URL
    :return: (success, url_or_error) — on success, url includes the decryption key fragment
    """
    logger.info(f"Uploading data to PrivateBin: {server}")

    payload, paste_url_key = _build_paste_payload(text)

    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "JSONHttpRequest",
        "User-Agent": f"RimSort/{AppInfo().app_version}",
    }

    try:
        response = http.post(
            server,
            data=json.dumps(payload, separators=(",", ":")),
            headers=headers,
            timeout=60,
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error uploading to PrivateBin: {e}")
        return False, str(e)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error uploading to PrivateBin: {e}")
        return False, str(e)

    if response.status_code != 200:
        body_snippet = response.text.strip()[:200]
        logger.warning(
            f"PrivateBin upload failed. Status: {response.status_code}; body: {body_snippet}"
        )
        return False, f"Status code: {response.status_code}\n{body_snippet}"

    data = response.json()
    if data.get("status") != 0:
        message = data.get("message", "Unknown error")
        logger.warning(f"PrivateBin API error: {message}")
        return False, message

    paste_id = data["id"]
    url = f"{server}/?{paste_id}#{paste_url_key}"
    logger.info(f"Uploaded! Paste available at: {url}")
    return True, url
