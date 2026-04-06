"""
kalshi_auth.py
Handles RSA-PSS HMAC signing authentication for the Kalshi API.
"""

import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiAuth:
    """
    Manages API authentication for Kalshi.

    Kalshi uses RSA-PSS signing with SHA-256. Each request requires three headers:
      - KALSHI-ACCESS-KEY   : your API key ID
      - KALSHI-ACCESS-SIGNATURE : base64-encoded RSA-PSS signature
      - KALSHI-ACCESS-TIMESTAMP : current millisecond timestamp

    The signed message is: timestamp + method.upper() + path
    e.g. "1741234567890GET/trade-api/ws/v2"
    """

    def __init__(self, api_key_id: str, private_key_path: str):
        self.api_key_id = api_key_id
        key_bytes = Path(private_key_path).read_bytes()
        self.private_key = serialization.load_pem_private_key(key_bytes, password=None)

    def _sign(self, message: str) -> str:
        """Sign a message string with RSA-PSS SHA-256 and return base64 string."""
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def get_headers(self, method: str, path: str) -> dict:
        """
        Build the three Kalshi auth headers for a given HTTP method and path.

        Args:
            method: HTTP method, e.g. "GET" or "POST"
            path:   Request path, e.g. "/trade-api/ws/v2"

        Returns:
            Dict of headers to add to the request.
        """
        timestamp_ms = str(round(time.time() * 1000))
        message = timestamp_ms + method.upper() + path
        signature = self._sign(message)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }
