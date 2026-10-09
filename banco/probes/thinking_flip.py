"""Sonda del flip de modo thinking (exp/38) — 3 llamadas REALES a la API.

Pregunta que responde: la barrida midió que la primera vuelta directa va con
thinking ON (sin extra_body) y la siguiente —que ya trae las tools— lo manda
disabled. El flip ON->OFF dentro de una conversación es el 400 que
docs/design.md:96-97 documenta como crash medido, y hoy la regla pegajosa solo
cubre el orden inverso (agéntica -> directa). ¿Sigue pasando?

La secuencia replica la del chat, con los MISMOS esquemas de tools:
  1. system + user, SIN tools y SIN extra_body        -> thinking ON
  2. + assistant(sin reasoning) + user, CON tools y thinking disabled
  3. + assistant + user, SIN tools y SIN extra_body    -> thinking ON otra vez

Cada paso reporta status, si volvió reasoning_content y el error si lo hay.
Costo: 3 llamadas cortas (~10 s). Uso: python3 banco/probes/thinking_flip.py
"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from openai import OpenAI  # noqa: E402

from nodes import TOOLS  # noqa: E402
from utils.call_llm import _setting, get_api_key  # noqa: E402

MODELO = _setting("LLM_MODEL", "deepseek-flash")
BASE = _setting("LLM_BASE_URL", "https://api.deepseek.com")
DESHABILITADO = {"thinking": {"type": "disabled"}}


def llamar(cliente, messages, tools=None, extra_body=None, etiqueta=""):
    """Una llamada; devuelve (mensaje, error, segundos, si hubo reasoning)."""
    inicio = time.time()
    try:
        resp = cliente.chat.completions.create(
            model=MODELO, messages=messages, tools=tools,
            extra_body=extra_body, max_tokens=200,
        )
        msg = resp.choices[0].message
        seg = time.time() - inicio
        razon = getattr(msg, "reasoning_content", None)
        estado = "SI" if razon else "no"
        cuantas = len(msg.tool_calls or [])
        print(f"  {etiqueta}: OK en {seg:.1f}s | reasoning_content: {estado} | tool_calls: {cuantas}")
        return msg, None, seg, bool(razon)
    except Exception as e:
        seg = time.time() - inicio
        detalle = getattr(e, "message", None) or str(e)
        print(f"  {etiqueta}: EXCEPCION {type(e).__name__} en {seg:.1f}s -> {detalle[:200]}")
        return None, e, seg, False


def main():
    cliente = OpenAI(api_key=get_api_key(), base_url=BASE)
    print(f"# Sonda thinking-flip | modelo {MODELO} | {len(TOOLS)} tools")
    print("")
    print("Paso 1 - vuelta directa (thinking ON, sin tools)")
    messages = [
        {"role": "system", "content": "Respondé breve."},
        {"role": "user", "content": "¿Quién ganó el último mundial de fútbol?"},
    ]
    msg1, err1, _, razon1 = llamar(cliente, messages, etiqueta="turno 1")
    if err1 or msg1 is None:
        print("")
        print("Sin turno 1 no hay flip que medir.")
        return 1
    messages += [
        {"role": "assistant", "content": msg1.content},   # SIN reasoning: como el historial real
        {"role": "user", "content": "¿Cuántos archivos .py hay en el repo? Usá list_files."},
    ]
    print("")
    print("Paso 2 - vuelta con tools (thinking disabled): el flip ON->OFF")
    msg2, err2, _, _ = llamar(cliente, messages, tools=TOOLS, extra_body=DESHABILITADO, etiqueta="turno 2")
    if msg2 is not None:
        messages.append({"role": "assistant", "content": msg2.content})
    messages.append({"role": "user", "content": "¿Y la capital de Francia?"})
    print("")
    print("Paso 3 - vuelta directa otra vez (thinking ON): el flip OFF->ON")
    _, err3, _, _ = llamar(cliente, messages, etiqueta="turno 3")
    print("")
    print("== Veredicto ==")
    fallos = [n for n, e in (("1", err1), ("2", err2), ("3", err3)) if e is not None]
    if not fallos:
        print("Sin 400: los dos flips pasaron. El hallazgo NO se reproduce hoy.")
    elif "2" in fallos:
        print("CONFIRMADO: el flip ON->OFF (turno 1 directo -> turno 2 con tools) revienta. Es el crash del chat.")
    else:
        print("Falla en los turnos " + ",".join(fallos) + ": ver el detalle de arriba.")
    print("Nota: el turno 1 devolvió reasoning_content: " + ("SI" if razon1 else "no") + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
