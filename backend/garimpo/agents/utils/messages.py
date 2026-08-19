from __future__ import annotations

from typing import Any, Sequence

from langchain_core.messages import BaseMessage


def get_message_text(message: Any) -> str:
    """
    Returns the plain text of a chat message, regardless of the provider.

    OpenAI-style models put a plain string in `message.content`, but Anthropic
    (Claude) returns a list of content blocks — e.g.
    `[{"type": "thinking", ...}, {"type": "text", "text": "..."}]` — so calling
    string methods on `.content` directly raises `AttributeError`. This joins the
    text blocks and drops the rest (thinking, tool calls, images).

    Parameters:
    ----------
    message : Any
        A LangChain message, a raw `content` value, or a plain string.

    Returns:
    -------
    str
        The message text, or an empty string when there is none.
    """
    if message is None:
        return ""
    if isinstance(message, str):
        return message

    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
            elif getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts)

    return str(content)


def get_tool_call_names(messages):
    """
    Method to extract the tool call names from a list of LangChain messages.
    
    Parameters:
    ----------
    messages : list
        A list of LangChain messages.
        
    Returns:
    -------
    tool_calls : list
        A list of tool call names.
    
    """
    tool_calls = []
    for message in messages:
        try: 
            if "tool_call_id" in list(dict(message).keys()):
                tool_calls.append(message.name)
        except:
            pass
    return tool_calls


def get_last_user_message_content(messages: Sequence[BaseMessage]) -> str:
    """
    Returns the content of the most recent human/user message in a list.
    Falls back to an empty string when missing.
    """
    for msg in reversed(messages or []):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            return get_message_text(msg).strip()
    return ""
