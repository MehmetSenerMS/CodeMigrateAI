import requests

from crewai import BaseLLM


class CodeMigrateLLM(BaseLLM):

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_new_tokens: int = 256
    ):

        super().__init__(
            model="codellama/CodeLlama-7b-Instruct-hf",
            temperature=0.0
        )

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_new_tokens = max_new_tokens

    def call(
        self,
        messages,
        tools=None,
        callbacks=None,
        available_functions=None,
        **kwargs
    ):

        if isinstance(messages, str):
            messages = [
                {
                    "role": "user",
                    "content": messages
                }
            ]

        normalized_messages = []

        for message in messages:

            role = message.get("role", "user")
            content = message.get("content", "")

            if role not in {"system", "user", "assistant"}:
                role = "user"

            if not isinstance(content, str):
                content = str(content)

            if content.strip():
                normalized_messages.append({
                    "role": role,
                    "content": content
                })

        if not normalized_messages:
            raise ValueError("No valid LLM messages")

        response = requests.post(
            f"{self.base_url}/chat",
            headers={
                "X-API-Key": self.api_key
            },
            json={
                "messages": normalized_messages,
                "max_new_tokens": self.max_new_tokens
            },
            timeout=(15, 180),
            allow_redirects=False
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code}\n"
                f"FastAPI validation details:\n"
                f"{response.text[:1500]}"
                )

        result = response.json()

        text = result.get("text", "")

        if not text:
            raise RuntimeError("Empty LLM response")

        return text

    def supports_function_calling(self):
        return False

    def supports_stop_words(self):
        return False

    def get_context_window_size(self):
        return 4096