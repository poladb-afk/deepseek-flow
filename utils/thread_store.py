"""Persistencia del thread del chat: checkpoints incrementales a disco (exp/48).

El gap nº1 del análisis 12-factor: `shared` muere con el proceso — un flujo
largo interrumpido pierde todo el trabajo. Esta pieza cierra ese agujero para
el CHAT (v1): cada ciclo del grafo appendea el `shared` COMPLETO a un JSONL por
corrida y un `resume` lo rehidrata.

Diseño: funciones PURAS, sin LLM. El checkpoint es bookkeeping de la casa —
cualquier fallo (disco, permisos, JSON roto) se traga: JAMÁS rompe el chat.
`THREAD_PERSIST=0` apaga TODO (ni siquiera crea el directorio).

Cada línea: `{"ts", "evento": "checkpoint", "nodo", "accion", "shared": {...}}`.

`cargar` lee la ÚLTIMA LÍNEA COMPLETA del archivo: un crash a mitad de escritura
deja una cola cortada (JSON que no parsea) y esas líneas parciales se descartan
desde el final — se sigue retrocediendo hasta encontrar una línea válida.

El validador de invariantes NO se reimplementa: `valido` reusa
`utils.compaccion.validar_historial` (los 4 invariantes del modo thinking ya
tienen validador y tests)."""

import json
import time
from pathlib import Path

from utils.call_llm import _setting

_DEFAULT_DIR = "salidas/threads"


def _ruta_dir(ruta_dir):
    """La carpeta de threads: el argumento explícito gana, si no el setting."""
    return Path(ruta_dir or _setting("THREADS_DIR", _DEFAULT_DIR))


def _persist_activo():
    """THREAD_PERSIST=0 apaga TODO (ni crea dir). Default: "1" (encendido)."""
    return _setting("THREAD_PERSIST", "1") != "0"


def checkpoint(id_thread, nodo, accion, shared, ruta_dir=None):
    """Appendea UNA línea con el `shared` COMPLETO a `<ruta_dir>/<id>.jsonl`.

    Bookkeeping: cualquier fallo se traga — un checkpoint jamás corta el chat.
    Con THREAD_PERSIST=0 no hace nada (ni siquiera crea el directorio)."""
    if not _persist_activo():
        return
    try:
        destino = _ruta_dir(ruta_dir) / f"{id_thread}.jsonl"
        destino.parent.mkdir(parents=True, exist_ok=True)
        linea = {
            "ts": round(time.time(), 3),
            "evento": "checkpoint",
            "nodo": nodo,
            "accion": accion,
            "shared": shared,
        }
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def cargar(id_thread, ruta_dir=None):
    """Devuelve el `shared` de la ÚLTIMA LÍNEA COMPLETA del archivo, o None.

    Tolerante a una cola cortada a mitad por un crash: el JSON que no parsea se
    saltea desde el final y se retrocede hasta la primera línea que sí parsea.
    Si no existe el archivo o no hay ninguna línea válida, devuelve None."""
    try:
        archivo = _ruta_dir(ruta_dir) / f"{id_thread}.jsonl"
        if not archivo.exists():
            return None
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linea in reversed(lineas):
        if not linea.strip():
            continue
        try:
            evento = json.loads(linea)
        except (json.JSONDecodeError, ValueError):
            continue  # cola cortada a mitad: se descarta y se sigue
        if isinstance(evento, dict) and isinstance(evento.get("shared"), dict):
            return evento["shared"]
    return None


def reparar_pendientes(shared):
    """Repara los `tool_calls` HUÉRFANOS del ÚLTIMO assistant: devuelve cuántos.

    Un proceso muerto entre la SELECCIÓN y la EJECUCIÓN de las tools (exp/49)
    deja el historial con un assistant con `tool_calls` SIN sus mensajes tool:
    viola el invariante de la API y el resume lo rechazaría. Por CADA tool_call
    huérfano se appendea un mensaje tool honesto: la llamada no llegó a
    registrarse como ejecutada — puede haber corrido a medias, y el modelo debe
    verificarla antes de repetirla.

    PURA y acotada al FINAL: solo mira el último assistant si sus `tool_calls`
    no tienen sus mensajes tool inmediatos. Pares viejos rotos en el MEDIO NO
    se tocan (eso es corrupción, no interrupción — que el validador los siga
    cazando). Idempotente: llamarla dos veces repara 0 la segunda."""
    if not isinstance(shared, dict):
        return 0
    mensajes = shared.get("messages")
    if not isinstance(mensajes, list) or not mensajes:
        return 0
    ultimo = mensajes[-1]
    if not isinstance(ultimo, dict) or ultimo.get("role") != "assistant":
        return 0
    tool_calls = ultimo.get("tool_calls")
    if not tool_calls:
        return 0
    reparados = 0
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        mensajes.append({
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "content": (
                "(interrumpido: esta llamada no llegó a registrarse ejecutada — "
                "puede haber corrido a medias; si sigue siendo necesaria, volvé "
                "a emitirla y verificá el efecto antes de repetirlo)"
            ),
        })
        reparados += 1
    return reparados


def valido(shared):
    """Lista de violaciones del historial del `shared` (vacía = válido).

    Reusa `utils.compaccion.validar_historial` — los 4 invariantes del modo
    thinking. NUNCA levanta: ante cualquier problema estructural devuelve una
    violación descriptiva en vez de propagar la excepción."""
    from utils.compaccion import validar_historial

    if not isinstance(shared, dict):
        return ["el shared no es un dict"]
    mensajes = shared.get("messages")
    try:
        return validar_historial(mensajes)
    except Exception as e:  # el validador es un instrumento, no un candado  # noqa: BLE001 (el validador es un instrumento, no un candado)
        return [f"el validador falló: {type(e).__name__}: {e}"]
