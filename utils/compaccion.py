"""Compacción de contexto (Mesa 6, 12-factor #5) — CÓDIGO PURO, sin LLM.

El problema medido: `shared['messages']` crece sin techo y cada vuelta
reenvía TODO el historial a la API (una sesión de 115 tools como
evidencia). El contexto se paga entero cada turno aunque lo viejo ya no
aporte.

Diseño: la ventana caliente (system + últimos N mensajes) queda intacta;
la zona fría (el medio) se reemplaza por UN mensaje de user con prefijo
fijo `[compacción]` que cuenta las vueltas omitidas y deja un placeholder
instructivo. El resumen REAL lo escribe el agente a sí mismo en un
segundo paso (acá no hay LLM: esta pieza es determinista y pura, mismo
input → mismo output).

Invariantes de seguridad (los exige el modo thinking pegajoso de la API;
ver utils/call_llm.py):

1. Sin `reasoning_content` en ningún mensaje.
2. Dicts canónicos (solo role/content/tool_calls/tool_call_id).
3. Ningún assistant con `tool_calls` sin sus `tool` inmediatas después.
4. Primer mensaje = system.

`validar_historial` verifica los cuatro. Se corre en los tests ANTES y
DESPUÉS de compactar: compactar jamás puede romper un historial válido.
"""

import hashlib
import json

# Prefijo fijo e inconfundible del resumen sintético. Un solo lugar para
# cambiarlo; los tests y la integración lo leen de acá.
PREFIJO_COMPACCION = "[compacción]"

# Ventana caliente por default: últimos N mensajes que NUNCA se tocan.
VENTANA_DEFAULT = 6

# Claves canónicas permitidas por rol (contrato de la API DeepSeek).
_CLAVES = {
    "system": {"role", "content"},
    "user": {"role", "content"},
    "assistant": {"role", "content", "tool_calls"},
    "tool": {"role", "tool_call_id", "content"},
}


# ---------------------------------------------------------------------------
# Serialización y tamaño
# ---------------------------------------------------------------------------

def serializar(messages):
    """Representación determinista del historial para medir y hashear."""
    return json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)


def _tamano(messages):
    return len(serializar(messages))


def huella(messages):
    """sha1 del historial serializado: dos historiales idénticos dan la
    misma huella. La integración la usa para no re-compactar la misma ronda."""
    return hashlib.sha1(serializar(messages).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validación de invariantes
# ---------------------------------------------------------------------------

def validar_historial(messages):
    """Devuelve la lista de violaciones (vacía = historial válido).

    NUNCA levanta: es un instrumento, no un candado de flujo. Clava los
    invariantes que el modo thinking pegajoso exige.
    """
    fallas = []
    if not isinstance(messages, list) or not messages:
        return ["el historial está vacío o no es una lista"]

    primero = messages[0]
    if not (isinstance(primero, dict) and primero.get("role") == "system"):
        fallas.append("el primer mensaje no es system")

    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            fallas.append(f"[{i}] no es dict")
            continue
        rol = m.get("role")
        if rol not in _CLAVES:
            fallas.append(f"[{i}] rol desconocido: {rol!r}")
            continue
        if "reasoning_content" in m:
            fallas.append(f"[{i}] arrastra reasoning_content")
        extra = set(m) - _CLAVES[rol]
        if extra:
            fallas.append(f"[{i}] claves no canónicas: {sorted(extra)}")
        if rol == "assistant" and m.get("tool_calls"):
            ids = {tc.get("id") for tc in m["tool_calls"] if isinstance(tc, dict)}
            vistos = set()
            j = i + 1
            while j < len(messages):
                sig = messages[j]
                if isinstance(sig, dict) and sig.get("role") == "tool":
                    vistos.add(sig.get("tool_call_id"))
                    j += 1
                    continue
                break
            if vistos != ids:
                fallas.append(
                    f"[{i}] assistant con tool_calls {sorted(ids)} sin sus "
                    f"tools inmediatas (vistas: {sorted(vistos)})")
    return fallas


# ---------------------------------------------------------------------------
# Unidad indivisible assistant+tools y bloques
# ---------------------------------------------------------------------------

def _es_unidad(messages, i):
    """True si messages[i] es un assistant con tool_calls: es la CABEZA de
    una unidad indivisible (él + sus tools inmediatas después)."""
    m = messages[i]
    return (isinstance(m, dict) and m.get("role") == "assistant"
            and bool(m.get("tool_calls")))


def _unidades(messages):
    """El historial cortado en unidades atómicas: cada assistant con tools
    arrastra sus tools inmediatas (nunca se separan); el resto es unidad de
    un solo mensaje. Devuelve [(inicio, fin_exclusivo), ...]."""
    cortes = []
    i = 0
    n = len(messages)
    while i < n:
        if _es_unidad(messages, i):
            j = i + 1
            while j < n and isinstance(messages[j], dict) and messages[j].get("role") == "tool":
                j += 1
            cortes.append((i, j))
            i = j
        else:
            cortes.append((i, i + 1))
            i += 1
    return cortes


def _resumen(cantidad):
    """El resumen sintético de la zona fría: user con prefijo fijo, el
    conteo de vueltas omitidas y un placeholder instructivo. Determinista."""
    return {
        "role": "user",
        "content": (
            f"{PREFIJO_COMPACCION} {cantidad} mensajes anteriores (zona fría) "
            "fueron compactados para no reenviar todo el historial. El "
            "detalle de esas vueltas ya no está en este contexto; los hechos "
            "durables están en memoria/ si hicieran falta (usá memory_search "
            "para recuperarlos). Continuá desde la ventana caliente de abajo."
        ),
    }


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def compactar(messages, max_chars, ventana=VENTANA_DEFAULT):
    """Devuelve el historial compactado. PURA y DETERMINISTA.

    (a) SIEMPRE conserva intactos el system (índice 0) y los ÚLTIMOS
        `ventana` mensajes (la ventana caliente), contando assistant con
        tool_calls + sus tools como unidad indivisible.
    (b) La zona fría (el medio) se REEMPLAZA por UN mensaje de user con
        prefijo `[compacción]`, conteo de mensajes omitidos y placeholder.
    (c) Nunca deja un assistant con tool_calls sin sus tools (invariante).
    (d) No-op documentado: si el historial ya entra en `max_chars` o tiene
        menos de `ventana + 2` mensajes, se devuelve INTACTO (copia nueva).

    `max_chars` se mide sobre la serialización canónica (ver `serializar`).
    """
    original = list(messages)
    if _tamano(original) <= max_chars or len(original) < ventana + 2:
        return original

    unidades = _unidades(original)

    # La ventana caliente son las últimas unidades atómicas. Si la unidad
    # de corte arranca en el índice 1 (o menos), no hay zona fría: no-op.
    if len(unidades) <= ventana + 1:
        return original
    cola = unidades[-ventana:]
    corte = cola[0][0]  # índice del primer mensaje de la ventana caliente

    # El system (índice 0) siempre intacto. La zona fría arranca en 1.
    if corte <= 1:
        return original

    frios = corte - 1
    return [original[0], _resumen(frios)] + original[corte:]
