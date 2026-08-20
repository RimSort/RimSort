from collections.abc import Callable
from typing import Any

from loguru import logger

from app.ai.gemini_models import DEFAULT_GEMINI_MODEL, format_quota_error_message
from app.ai.provider_base import AIProvider
from app.ai.proxy import (
    ProxyParseError,
    ProxyUnavailableError,
    resolve_working_proxy,
)
from app.utils import http

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]
OnToolCall = Callable[[str, dict[str, Any], dict[str, Any]], None]
MAX_TOOL_ROUNDS = 16


class GeminiProvider(AIProvider):
    MODEL = DEFAULT_GEMINI_MODEL

    def __init__(
        self,
        api_key: str,
        proxy: str = "",
        model: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.proxy = proxy
        self.model = model or self.MODEL

    def _raise_for_gemini_error(self, response: Any) -> None:
        if response.ok:
            return
        try:
            payload = response.json()
            err = payload.get("error", {})
            message = str(err.get("message", response.text))
            status = response.status_code
        except Exception:
            response.raise_for_status()
            return

        lowered = message.lower()
        if status == 404 or "no longer available" in lowered:
            raise ValueError(
                "Gemini model is no longer available. Update RimSort or change the model."
            )
        if "location is not supported" in lowered:
            raise ValueError(
                "Gemini API is not available in your region. Configure a proxy or VPN."
            )
        if status in (401, 403):
            raise ValueError("Invalid Gemini API key.")
        if status == 429 or any(
            token in lowered
            for token in (
                "resource_exhausted",
                "quota",
                "rate limit",
                "rate_limit",
                "too many requests",
                "exceeded your current quota",
            )
        ):
            raise ValueError(format_quota_error_message(self.model))
        raise ValueError(f"Gemini API error ({status}): {message}")

    def _request_kwargs(self) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = {
            "headers": {"Content-Type": "application/json"},
            "timeout": 60,
        }
        if self.proxy.strip():
            try:
                resolved = resolve_working_proxy(self.proxy)
            except ProxyParseError as exc:
                raise ValueError(f"Could not parse proxy: {exc}") from exc
            except ProxyUnavailableError as exc:
                raise ValueError(str(exc)) from exc
            if resolved is not None:
                request_kwargs["proxies"] = resolved[0]
        return request_kwargs

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        response = http.post(url, json=body, **self._request_kwargs())
        self._raise_for_gemini_error(response)
        return response.json()

    def _build_initial_body(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        system_instruction: str | None = None
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                system_instruction = msg.get("content", "")
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                {"role": gemini_role, "parts": [{"text": msg.get("content", "")}]}
            )

        body: dict[str, Any] = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]
        return body

    def _extract_text(self, data: dict[str, Any]) -> str | None:
        try:
            parts = data["candidates"][0]["content"].get("parts", [])
        except (KeyError, IndexError, TypeError):
            return None
        texts = [part["text"] for part in parts if "text" in part]
        if texts:
            return "".join(texts)
        return None

    def _extract_function_calls(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        candidate = data["candidates"][0]
        content = candidate["content"]
        parts = content.get("parts", [])
        function_calls = [
            part["functionCall"] for part in parts if "functionCall" in part
        ]
        return content, function_calls

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: ToolExecutor | None = None,
        on_tool_call: OnToolCall | None = None,
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key is not configured")

        body = self._build_initial_body(messages, tools)

        for _ in range(MAX_TOOL_ROUNDS):
            data = self._post(body)
            text = self._extract_text(data)
            if text is not None:
                return text

            if not tools or tool_executor is None:
                logger.error(f"Unexpected Gemini response without text: {data}")
                raise ValueError("Invalid response from Gemini API")

            model_content, function_calls = self._extract_function_calls(data)
            if not function_calls:
                logger.error(f"Unexpected Gemini response: {data}")
                raise ValueError("Invalid response from Gemini API")

            response_parts: list[dict[str, Any]] = []
            for function_call in function_calls:
                name = str(function_call.get("name", ""))
                args = function_call.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                logger.debug(f"Gemini tool call: {name}({args})")
                result = tool_executor(name, args)
                if on_tool_call is not None:
                    on_tool_call(name, args, result)
                response_parts.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "response": result,
                        }
                    }
                )

            contents = body["contents"]
            contents.append(model_content)
            contents.append({"role": "user", "parts": response_parts})
            body["contents"] = contents

        raise ValueError("Gemini tool calling exceeded maximum rounds")
