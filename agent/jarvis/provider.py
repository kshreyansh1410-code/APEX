"""The provider seam: the only module that talks to the model SDK.

Everything else calls `Provider.respond()` and never imports `anthropic` directly,
so swapping models, adding retries, or logging cost happens here and only here.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import anthropic

from .config import ModelConfig

# Server-side refusal fallback: if the model declines, the API re-runs the request
# on a suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ProviderError(Exception):
    """A failed model call, with a message that is safe to show the user."""


@dataclass
class Reply:
    text: str
    # The assistant turn exactly as the model produced it. Appended to history
    # unchanged so thinking blocks stay valid on the next request.
    content: list[Any]
    stop_reason: str | None
    usage: dict[str, int] = field(default_factory=dict)


class Provider(Protocol):
    def respond(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> Reply: ...


class ClaudeProvider:
    def __init__(self, config: ModelConfig):
        self.config = config
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(timeout=self.config.timeout_seconds, max_retries=2)
        return self._client

    def respond(self, system, messages, tools=None, on_text=None) -> Reply:
        extra = {}
        if self.config.fallbacks:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        if tools:
            extra["tools"] = tools
        # Tool inputs stream eagerly, so the SDK can hit JSON it can't parse at all.
        # That raises ValueError mid-stream; re-issue the request a couple of times.
        for attempt in range(3):
            try:
                return self._respond_once(system, messages, on_text, extra)
            except ValueError:
                if attempt == 2:
                    raise ProviderError("The model kept producing a malformed tool call. Try rephrasing.") from None
        raise AssertionError("unreachable")

    def _respond_once(self, system, messages, on_text, extra) -> Reply:
        try:
            with self._get_client().beta.messages.stream(
                model=self.config.name,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=messages,
                output_config={"effort": self.config.effort},
                # Cache the growing conversation prefix so long sessions stay cheap.
                cache_control={"type": "ephemeral"},
                **extra,
            ) as stream:
                for chunk in stream.text_stream:
                    if on_text:
                        on_text(chunk)
                message = stream.get_final_message()
        except anthropic.AuthenticationError:
            raise ProviderError("My API key was rejected. Check ANTHROPIC_API_KEY in agent/.env.") from None
        except anthropic.PermissionDeniedError:
            raise ProviderError("My API key doesn't have access to that model. Check the model name in config.toml.") from None
        except anthropic.NotFoundError:
            raise ProviderError(f"The model '{self.config.name}' wasn't found. Check the model name in config.toml.") from None
        except anthropic.RateLimitError:
            raise ProviderError("I'm being rate-limited right now. Give it a moment and try again.") from None
        except anthropic.BadRequestError as e:
            raise ProviderError(f"The request was rejected: {e.message}") from None
        except anthropic.APITimeoutError:
            raise ProviderError("The model took too long to answer. Try again.") from None
        except anthropic.APIConnectionError:
            raise ProviderError("I can't reach the model. Check your internet connection.") from None
        except anthropic.APIStatusError as e:
            raise ProviderError(f"The model service had a problem (HTTP {e.status_code}). Try again shortly.") from None
        except anthropic.AnthropicError as e:
            raise ProviderError(f"I couldn't start a model call: {e}") from None
        except TypeError as e:
            # The SDK raises TypeError when no credentials are configured at all.
            if "authentication" not in str(e):
                raise
            raise ProviderError("I don't have an API key yet. Set ANTHROPIC_API_KEY in agent/.env.") from None

        if message.stop_reason == "refusal":
            raise ProviderError("I can't help with that one.")

        text = "".join(b.text for b in message.content if b.type == "text")
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "cache_read_input_tokens": message.usage.cache_read_input_tokens or 0,
        }
        return Reply(text=text, content=message.content, stop_reason=message.stop_reason, usage=usage)
