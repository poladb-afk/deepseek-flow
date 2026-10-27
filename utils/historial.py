"""El mensaje del asistente en forma canónica del historial (X14: una sola
copia de lo que el chat, el supervisor y el kernel hacían igual): solo
role/content/tool_calls — el reasoning_content del modo thinking no viaja."""


def as_dict(tc):
    """La tool call como dict canónico (lo que come run_tool_call): acepta
    el objeto del SDK o un dict ya armado."""
    if isinstance(tc, dict):
        return tc
    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
    }


def historiar(msg):
    m = {"role": "assistant", "content": getattr(msg, "content", None)}
    if getattr(msg, "tool_calls", None):
        m["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return m
