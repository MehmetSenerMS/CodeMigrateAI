import requests


class RemoteMigrationClient:
    """
    HTTP client for the CodeMigrate AI fine-tuned LLM service.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 180
    ):

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        if not self.base_url.startswith("https://"):
            raise ValueError("An HTTPS API URL is required")

        if not api_key:
            raise ValueError("API key cannot be empty")

        self.session = requests.Session()

        self.session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        })

    def health(self) -> dict:
        """
        Check the remote model service status.
        """

        response = self.session.get(
            f"{self.base_url}/health",
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    def migrate(
        self,
        instruction: str,
        legacy_code: str
    ) -> dict:
        """
        Generate modernized code using the fine-tuned LLM.
        """

        if not instruction.strip():
            raise ValueError(
                "Migration instruction cannot be empty"
            )

        if not legacy_code.strip():
            raise ValueError(
                "Legacy code cannot be empty"
            )

        payload = {
            "instruction": instruction,
            "legacy_code": legacy_code
        }

        response = self.session.post(
            f"{self.base_url}/migrate",
            json=payload,
            timeout=(15, self.timeout),
            allow_redirects=False
        )

        if response.status_code != 200:
            raise RuntimeError(
                "Migration API request failed "
                f"with HTTP {response.status_code}"
            )

        result = response.json()

        if not isinstance(result, dict):
            raise RuntimeError(
                "Invalid response format"
            )

        if "generated_code" not in result:
            raise RuntimeError(
                "Missing generated_code in API response"
            )

        return result

    def close(self):
        """
        Close the HTTP session.
        """

        self.session.close()