"""4.ª medición de `tool_choice="none"` (pre-registro: `banco/specs/s3_prefijo_none.md`).

La pregunta es una: con el menú REAL del chat (system prompt real + las 30
tools), ¿el proveedor cuenta los esquemas en `prompt_tokens` cuando
`tool_choice="none"`, y comparte la caché del prefijo que dejó el request con
tools? Cuatro llamadas idénticas en contenido, en orden: base, base_repetida,
none, none_repetida. La base usa el builder del chat (`_kwargs_agente`), así
que es el request de hoy salvo la pregunta y el `max_tokens` del instrumento.

Sin red: `--autotest` decide sobre filas sintéticas (los cuatro estados, con
tres casos de SIN DATO) y
`--dry-run` imprime los cuatro requests sin mandarlos. La corrida real la corre
Chief con autorización del operador y escribe el JSONL en
`salidas/tool_choice_none_real/`.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openai import BadRequestError

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import nodes  # noqa: E402
from main import system_prompt  # noqa: E402
from utils.call_llm import _client, _kwargs_agente  # noqa: E402

PEDIDO = "Listá los archivos del directorio actual."
MAX_TOKENS = 64
SALIDA = RAIZ / "salidas" / "tool_choice_none_real"


def mensajes():
    return [{"role": "system", "content": system_prompt()},
            {"role": "user", "content": PEDIDO}]


def sha_prefijo():
    """Huella del bloque que se comparte: system prompt + esquemas de tools."""
    bloque = json.dumps(mensajes(), ensure_ascii=False) + json.dumps(nodes.TOOLS, ensure_ascii=False)
    return hashlib.sha256(bloque.encode()).hexdigest()[:16]


def requests():
    """Los cuatro kwargs, en orden; `none` es la base con el parámetro agregado."""
    base = _kwargs_agente(mensajes(), nodes.TOOLS)
    base["max_tokens"] = MAX_TOKENS
    none = dict(base, tool_choice="none")
    return [("base", dict(base)), ("base_repetida", dict(base)),
            ("none", dict(none)), ("none_repetida", dict(none))]


def llamada(etiqueta, kwargs):
    """Una llamada; solo un 400 que nombre `tool_choice` es dato (rechazo)."""
    try:
        r = _client().chat.completions.create(**kwargs)
    except BadRequestError as e:
        if "tool_choice" not in str(e).lower():
            raise
        return {"llamada": etiqueta, "acepta": False,
                "error": f"{type(e).__name__}: {e}"[:300]}
    msg, u = r.choices[0].message, r.usage
    return {"llamada": etiqueta, "acepta": True, "tool_calls": len(msg.tool_calls or []),
            "texto": (msg.content or "")[:120], "prompt": u.prompt_tokens,
            "completion": u.completion_tokens, "total": u.total_tokens,
            "cache_hit": getattr(u, "prompt_cache_hit_tokens", None),
            "cache_miss": getattr(u, "prompt_cache_miss_tokens", None)}


def veredicto(filas):
    """Estado de C0–C4 y el detalle legible; puro para poder probarlo con filas
    sintéticas sin red (`--autotest`)."""
    base, base_rep, none, none_rep = filas
    if not all(f.get("acepta") for f in (base, base_rep)):
        return "SIN DATO", "la base no respondió; error operativo, no es dato"
    if base.get("prompt") != base_rep.get("prompt"):
        return "SIN DATO", "el conteo de la base no es estable entre dos requests idénticos"
    if not none.get("acepta") or not none_rep.get("acepta"):
        rechazo = none.get("error") or none_rep.get("error")
        return "NO VIABLE", f"`none` rechazado con el menú real: {rechazo}"
    if none.get("tool_calls") or none_rep.get("tool_calls"):
        return "NO VIABLE", "`none` acepta pero devuelve tool calls con el menú real"
    if none.get("cache_hit") is None or base_rep.get("cache_hit") is None:
        return "SIN DATO", "el proveedor no informa caché"
    if not base_rep["cache_hit"]:
        return "SIN DATO", "control: el request idéntico con tools no reportó caché"
    delta = base["prompt"] - none["prompt"]
    if delta < 0:
        return "SIN DATO", f"`none` cuenta más que la base (delta {delta}): no es la omisión esperada"
    if delta == 0:
        if none["cache_hit"] and none_rep.get("cache_hit"):
            return "PREFIJO COMPARTIDO", f"mismo prompt ({base['prompt']} tokens) y caché compartida"
        return "PREFIJO NO COMPARTIDO", "mismo prompt contado pero `none` no reportó caché"
    if delta < 10:
        return "SIN DATO", f"delta {delta} tokens: indeterminado"
    dentro = 5231 <= abs(delta) <= 8718
    return "PREFIJO NO COMPARTIDO", (
        f"`none` cuenta {none['prompt']} vs {base['prompt']} (delta {delta}); "
        f"{'consistente' if dentro else 'NO consistente'} con el tamaño de las 30 tools")


def _head():
    """El commit con el que se corrió, si hay git (evidencia del instrumento)."""
    try:
        return subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return ""


def _fila(prompt, cache_hit, tool_calls=0):
    return {"acepta": True, "prompt": prompt, "cache_hit": cache_hit, "tool_calls": tool_calls}


def autotest():
    """Los cuatro estados del veredicto, con filas sintéticas: sin LLM ni red."""
    casos = [
        ("PREFIJO COMPARTIDO", [_fila(7400, 0), _fila(7400, 7296), _fila(7400, 7296), _fila(7400, 7296)]),
        ("PREFIJO NO COMPARTIDO", [_fila(7400, 0), _fila(7400, 7296), _fila(426, 0), _fila(426, 0)]),
        ("PREFIJO NO COMPARTIDO", [_fila(7400, 0), _fila(7400, 7296), _fila(7400, 0), _fila(7400, 0)]),
        ("NO VIABLE", [_fila(7400, 0), _fila(7400, 7296),
                       dict(_fila(7400, 0), tool_calls=1), _fila(7400, 0)]),
        ("SIN DATO", [_fila(7400, 0), _fila(7400, 0), _fila(7400, 0), _fila(7400, 0)]),
        ("SIN DATO", [_fila(7400, 0), _fila(7400, 7296), _fila(7397, 0), _fila(7397, 0)]),
        ("SIN DATO", [_fila(7400, 0), _fila(7400, 7296), _fila(7500, 0), _fila(7500, 0)]),
    ]
    for esperado, filas in casos:
        obtenido, detalle = veredicto(filas)
        if obtenido != esperado:
            print(f"autotest ❌ esperaba {esperado}, dio {obtenido} ({detalle})")
            return 1
        print(f"autotest ✅ {esperado}: {detalle}")
    print(f"autotest verde: {len(casos)} casos, sin LLM ni red")
    return 0


def dry_run(reqs):
    print(f"modelo: {reqs[0][1]['model']} · n_tools: {len(reqs[0][1]['tools'])} · "
          f"system: {len(reqs[0][1]['messages'][0]['content'])} chars · sha_prefijo: {sha_prefijo()}")
    for etiqueta, kw in reqs:
        print(json.dumps({"llamada": etiqueta, "tool_choice": kw.get("tool_choice", "(ausente)"),
                          "max_tokens": kw["max_tokens"], "extra_body": kw.get("extra_body"),
                          "chars_mensajes": len(json.dumps(kw["messages"], ensure_ascii=False))},
                         ensure_ascii=False))
    print("dry-run: no se mandó ningún request")
    return 0


def main():
    if "--autotest" in sys.argv:
        return autotest()
    reqs = requests()
    if "--dry-run" in sys.argv:
        return dry_run(reqs)
    filas = [llamada(etiqueta, kw) for etiqueta, kw in reqs]
    estado, detalle = veredicto(filas)
    resumen = {"llamada": "resumen", "estado": estado, "detalle": detalle,
               "modelo": reqs[0][1]["model"], "n_tools": len(reqs[0][1]["tools"]),
               "chars_system": len(reqs[0][1]["messages"][0]["content"]),
               "chars_tools": len(json.dumps(nodes.TOOLS, ensure_ascii=False)),
               "sha_prefijo": sha_prefijo(), "head": _head(),
               "fecha": datetime.now().isoformat(timespec="seconds")}
    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    destino.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in [*filas, resumen]),
                       encoding="utf-8")
    for fila in [*filas, resumen]:
        print(json.dumps(fila, ensure_ascii=False))
    print(f"VEREDICTO: {estado} — {detalle}")
    print(f"salida: {destino.relative_to(RAIZ)}")
    return 0 if estado != "SIN DATO" else 2


if __name__ == "__main__":
    sys.exit(main())
