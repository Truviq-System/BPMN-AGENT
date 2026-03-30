import anthropic
import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def call_claude(prompt: str, system: str = "", max_tokens: int = 8000) -> str | None:
    """
    Call Claude API with optional prompt caching.

    Parameters
    ----------
    prompt     : dynamic user content (process description, XML, etc.)
    system     : large static instructions — marked for prompt caching so repeated
                 calls with the same system text are served from cache (~90% cheaper).
    max_tokens : right-sized per use case (BPMN=8000, tests=4000, SB=6000, React=5000).
    """
    try:
        kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        if system:
            # cache_control marks this block for Anthropic prompt caching.
            # Cache persists 5 min, refreshed on each use.
            # Minimum cacheable block: 1024 tokens on Sonnet models.
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            kwargs["extra_headers"] = {"anthropic-beta": "prompt-caching-2024-07-31"}

        with claude.messages.stream(**kwargs) as stream:
            final = stream.get_final_message()

        usage = final.usage
        cache_read  = getattr(usage, "cache_read_input_tokens",     0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_info  = f" | cache_hit:{cache_read} written:{cache_write}" if system else ""
        print(f"Tokens — in:{usage.input_tokens} out:{usage.output_tokens}{cache_info}")

        text_parts = [b.text for b in final.content if b.type == "text"]
        return "\n".join(text_parts) if text_parts else None

    except anthropic.APIStatusError as e:
        print(f"API Error {e.status_code}: {e.message}")
        return None
    except Exception as e:
        print(f"Request error: {e}")
        return None
