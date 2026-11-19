"""Thin Claude wrapper: JSON-only calls validated by Pydantic, with retry, controlled repair and a disk cache.

Every stage that uses Claude goes through `ClaudeJSON.call`, so the guarantees are uniform:
  * transient API errors (429 / 5xx / connection) retry with exponential backoff;
  * malformed or schema-invalid JSON triggers up to `max_repairs` repair requests that show
    Claude the validation error — invalid output is never silently accepted;
  * identical prompts are served from cache, so `--resume` does not repeat paid calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """Claude is not configured or failed permanently — callers switch to the labelled fallback."""


def extract_json_block(text: str) -> str:
    """Pull the first top-level JSON object out of a response (tolerates ```json fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model output")
    return text[start:end + 1]


class ClaudeJSON:
    def __init__(self, api_key: str, model: str, cache_dir: Path, client=None, max_repairs: int = 2,
                 server_fallback: bool = True):
        self.model = model
        self.max_repairs = max_repairs
        self.server_fallback = server_fallback
        self.cache_dir = cache_dir / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if client is not None:
            self.client = client
        else:
            if not api_key:
                raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key, max_retries=0)  # tenacity owns retries
        self.calls = 0

    def _key(self, system: str, user: str, schema_name: str) -> Path:
        h = hashlib.sha256(f"{self.model}|{schema_name}|{system}|{user}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{schema_name}_{h}.json"

    def _send(self, system: str, messages: list[dict]) -> str:
        import anthropic

        @retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30),
               retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError,
                                              anthropic.InternalServerError)))
        def _do(use_fallback: bool):
            kwargs = dict(model=self.model, max_tokens=16000, system=system, messages=messages)
            extra: dict = {"output_config": {"effort": "medium"}}
            headers: dict = {}
            if use_fallback:  # server-side refusal fallback (routes by refusal category)
                extra["fallbacks"] = "default"
                headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
            return self.client.messages.create(**kwargs, extra_body=extra, extra_headers=headers or None)

        try:
            resp = _do(self.server_fallback)
        except anthropic.BadRequestError as exc:
            if self.server_fallback and "fallback" in str(exc).lower():
                log.info("Server-side fallback not accepted for this key/model; retrying without it")
                self.server_fallback = False
                resp = _do(False)
            else:
                raise
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable("Claude rejected the API key (401)") from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f"Model '{self.model}' not found — check ANTHROPIC_MODEL") from exc
        self.calls += 1
        if getattr(resp, "stop_reason", None) == "refusal":
            raise LLMUnavailable("Claude declined this request (stop_reason=refusal)")
        return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")

    def call(self, system: str, user: str, schema: Type[T]) -> T:
        """Return a validated `schema` instance or raise LLMUnavailable after controlled repair attempts."""
        cache = self._key(system, user, schema.__name__)
        if cache.exists():
            try:
                return schema.model_validate_json(cache.read_text())
            except ValidationError:
                cache.unlink()
        messages: list[dict] = [{"role": "user", "content": user}]
        last_error = ""
        for attempt in range(self.max_repairs + 1):
            try:
                text = self._send(system, messages)
            except LLMUnavailable:
                raise
            except Exception as exc:
                raise LLMUnavailable(f"Claude API request failed: {exc.__class__.__name__}") from exc
            try:
                obj = schema.model_validate(json.loads(extract_json_block(text)))
                cache.write_text(obj.model_dump_json())
                return obj
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:1500]
                log.warning("Claude returned invalid %s JSON (attempt %d): %s", schema.__name__, attempt + 1, last_error[:200])
                messages = messages + [
                    {"role": "assistant", "content": text or "(empty)"},
                    {"role": "user", "content": "Your previous reply was not valid against the required JSON schema.\n"
                                                f"Validation error:\n{last_error}\n\nReturn ONLY the corrected JSON object."},
                ]
        raise LLMUnavailable(f"Claude output failed schema validation after {self.max_repairs} repairs: {last_error[:300]}")


def load_prompt(prompts_dir: Path, name: str) -> str:
    return (prompts_dir / name).read_text(encoding="utf-8")


def make_llm(settings, client=None) -> Optional[ClaudeJSON]:
    """Return a ClaudeJSON when Claude is configured (or a test client is injected), else None."""
    if client is not None:
        return ClaudeJSON("test", settings.anthropic_model, settings.cache_dir, client=client)
    if not settings.claude_enabled:
        return None
    return ClaudeJSON(settings.anthropic_api_key, settings.anthropic_model, settings.cache_dir)
