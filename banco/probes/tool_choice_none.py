"""Sonda de X158: ¿DeepSeek acepta `tool_choice="none"`?

S3 (esquema de tools fijo y cierre por arista) está bloqueado por este dato.
Hoy el cierre retira las tools (`tools=None`) en la última llamada, y eso
cambia el prefijo cacheado. Si el proveedor acepta mandar las MISMAS tools con
`tool_choice="none"` y no devuelve tool calls, el esquema queda fijo y S3 se
puede pre-registrar; si lo rechaza o igual devuelve tool calls, S3 se cierra
como imposible con este proveedor.

Tres llamadas chicas (max_tokens=40, ~centavos), con el modelo y el endpoint
del harness (`utils.call_llm`):
  1. base: tools y tool_choice por defecto, con un pedido que invita a usar una
     tool → muestra si el modelo pide tools;
  2. lo mismo con tool_choice="none" → ¿lo acepta? ¿devuelve tool calls?
  3. lo mismo que 2, repetida → el cache del prefijo (prompt_cache_hit_tokens).

Uso: python3 banco/probes/tool_choice_none.py  (necesita DEEPSEEK_API_KEY o LLM_API_KEY)
"""
import json

from utils.call_llm import _client, _model
from utils.fs_tools import TOOLS

PEDIDO = [{"role": "user", "content": "Listá los archivos del directorio actual."}]


def una(etiqueta, **extra):
    try:
        r = _client().chat.completions.create(model=_model(), messages=PEDIDO, tools=TOOLS,
                                              max_tokens=40, **extra)
    except Exception as e:  # noqa: BLE001 (sonda: el rechazo del proveedor ES el dato)
        fila = {"llamada": etiqueta, "acepta": False, "error": f"{type(e).__name__}: {e}"[:400]}
    else:
        msg, u = r.choices[0].message, r.usage
        fila = {"llamada": etiqueta, "acepta": True, "tool_calls": len(msg.tool_calls or []),
                "texto": (msg.content or "")[:120], "prompt": u.prompt_tokens,
                "cache_hit": getattr(u, "prompt_cache_hit_tokens", None)}
    print(json.dumps(fila, ensure_ascii=False))
    return fila


def main():
    print(f"modelo: {_model()}")
    filas = [una("base"), una("none", tool_choice="none"), una("none_repetida", tool_choice="none")]
    none = filas[1]
    if not none["acepta"]:
        veredicto = "NO ACEPTA tool_choice=none: S3 se cierra como imposible con este proveedor"
    elif none["tool_calls"]:
        veredicto = "ACEPTA el parámetro pero IGUAL devuelve tool calls: S3 no se puede apoyar en él"
    else:
        veredicto = "ACEPTA tool_choice=none y no devuelve tool calls: S3 se puede pre-registrar"
    print(f"VEREDICTO: {veredicto}")


if __name__ == "__main__":
    main()
