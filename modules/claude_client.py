import anthropic
import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def call_claude(prompt: str) -> str | None:
    try:
        with claude.messages.stream(
            model=MODEL,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            final = stream.get_final_message()

        usage = final.usage
        print(f"Tokens — input: {usage.input_tokens} | output: {usage.output_tokens}")

        text_parts = [b.text for b in final.content if b.type == "text"]
        return "\n".join(text_parts) if text_parts else None

    except anthropic.APIStatusError as e:
        print(f"API Error {e.status_code}: {e.message}")
        return None
    except Exception as e:
        print(f"Request error: {e}")
        return None
