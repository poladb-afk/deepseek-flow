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
5. Ningún `tool` huérfano: responde al tool_call del assistant
   INMEDIATAMENTE anterior (la implementación solo verifica eso: un tool que
   responda a un assistant más viejo también se marca huérfano).

`validar_historial` verifica los cinco. Se corre en los tests ANTES y
DESPUÉS de compactar: compactar jamás puede romper un historial válido.
"""

import hashlib
import json

# Prefijo fijo e inconfundible del resumen sintético. Un solo lugar para
# cambiarlo; los tests y la integración lo leen de acá.
PREFIJO_COMPACCION = "[compacción]"

# Ventana caliente por default: últimos N mensajes que NUNCA se tocan.
VENTANA_DEFAULT = 6

# Tope del respaldo literal de la zona fría antes de compactar (A17): la
# transcripción completa va a memoria/ y no conviene que crezca sin límite.
MAX_RESPALDO_CHARS = 200_000

# Recorte de tool results viejos DENTRO de la ventana caliente (exp/91): cuando
# la ventana sola supera el tope, la compacción no puede bajarlo y el contexto
# se clava. Recortar el CONTENIDO (no la estructura) lo desbloquea; el prefijo
# hace la operación idempotente y delata el marcador en el historial.
PREFIJO_RECORTE = "[recorte]"
UMBRAL_RECORTE = 500   # por debajo no vale la pena: un resultado corto no pesa
CABEZA_RECORTE = 300   # ancla de contexto conservada al principio
COLA_RECORTE = 300     # ancla de contexto conservada al final
MANTENER_TOOLS = 3     # los últimos N tool results quedan INTACTOS

# Claves canónicas permitidas por rol (contrato de la API DeepSeek).
_CLAVES = {
    "system": {"role", "content"},
    "user": {"role", "content"},
    "assistant": {"role", "content", "tool_calls"},
    "tool": {"role", "tool_call_id", "content"},
}


# Serialización y tamaño

def serializar(messages):
    """Representación determinista del historial para medir y hashear."""
    return json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)


def _tamano(messages):
    return len(serializar(messages))


def huella(messages):
    """sha1 del historial serializado: dos historiales idénticos dan la
    misma huella. La integración la usa para no re-compactar la misma ronda."""
    return hashlib.sha1(serializar(messages).encode("utf-8")).hexdigest()


# Validación de invariantes

def _chequeos_de_rol(i, m):
    """(fallas, rol_conocido) de un mensaje: rol, reasoning y claves."""
    rol = m.get("role")
    if rol not in _CLAVES:
        return [f"[{i}] rol desconocido: {rol!r}"], False
    fallas = []
    if "reasoning_content" in m:
        fallas.append(f"[{i}] arrastra reasoning_content")
    extra = set(m) - _CLAVES[rol]
    if extra:
        fallas.append(f"[{i}] claves no canónicas: {sorted(extra)}")
    return fallas, True


def _chequeos_tool_calls(i, m, messages):
    """assistant con tool_calls debe tener sus tools inmediatas (contrato API)."""
    if m.get("role") != "assistant" or not m.get("tool_calls"):
        return []
    ids = {tc.get("id") for tc in m["tool_calls"] if isinstance(tc, dict)}
    vistos = set()
    for sig in messages[i + 1:]:
        if not (isinstance(sig, dict) and sig.get("role") == "tool"):
            break
        vistos.add(sig.get("tool_call_id"))
    if vistos == ids:
        return []
    return [
        f"[{i}] assistant con tool_calls {sorted(ids, key=str)} sin sus "
        f"tools inmediatas (vistas: {sorted(vistos, key=str)})"
    ]


def _actualizar_abiertos(i, m, abiertos, fallas):
    """Tool huérfano + estado de ids abiertos tras el mensaje `m`."""
    rol = m.get("role")
    if rol == "tool":
        if m.get("tool_call_id") not in abiertos:
            fallas.append(f"[{i}] tool huérfano: {m.get('tool_call_id')!r} sin assistant que lo pida")
        abiertos.discard(m.get("tool_call_id"))
        return abiertos
    if rol == "assistant" and m.get("tool_calls"):
        return {tc.get("id") for tc in m["tool_calls"] if isinstance(tc, dict)}
    return set()


def validar_historial(messages):
    """Devuelve la lista de violaciones (vacía = historial válido).

    NUNCA levanta: es un instrumento, no un candado de flujo. Clava los
    invariantes que el modo thinking pegajoso exige.
    """
    if not isinstance(messages, list) or not messages:
        return ["el historial está vacío o no es una lista"]
    fallas = []
    primero = messages[0]
    if not (isinstance(primero, dict) and primero.get("role") == "system"):
        fallas.append("el primer mensaje no es system")
    abiertos = set()  # ids del último assistant con tool_calls aún sin respuesta
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            fallas.append(f"[{i}] no es dict")
            continue
        abiertos = _actualizar_abiertos(i, m, abiertos, fallas)
        violaciones, rol_conocido = _chequeos_de_rol(i, m)
        fallas.extend(violaciones)
        if rol_conocido:
            fallas.extend(_chequeos_tool_calls(i, m, messages))
    return fallas


# Unidad indivisible assistant+tools y bloques

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


def zona_fria(messages, ventana=VENTANA_DEFAULT):
    """Los mensajes que compactar() descartaría, con la MISMA partición.

    Lista vacía si no hay zona fría (historial corto o ventana completa). El
    llamador la usa para RESPALDARLA antes de compactar (A17): el marcador no
    debe prometer que el detalle está en memoria/ si nadie lo guardó."""
    original = list(messages)
    if len(original) < ventana + 2:
        return []
    unidades = _unidades(original)
    if len(unidades) <= ventana + 1:
        return []
    corte = unidades[-ventana:][0][0]
    if corte <= 1:
        return []
    return original[1:corte]


def _resumen(cantidad, respaldo=None, objetivo=None):
    """El resumen sintético de la zona fría: user con prefijo fijo, el
    conteo de vueltas omitidas y —si el llamador respaldó la zona fría— la
    ruta donde quedó. Determinista.

    El texto viejo afirmaba que "los hechos durables están en memoria/" sin
    que nadie los hubiera guardado: era falso en cuanto hubiera algo durable
    en la zona fría. Ahora solo lo dice si hay respaldo y dice CUÁL es.

    `objetivo` conserva la TAREA VIGENTE: sin esto, la zona fría se lleva la
    pregunta original y el modelo queda con resultados de tools sin saber qué
    le pidieron (medido en vivo: auditoría de 16 rondas, "I need to know what
    the actual task is")."""
    donde = (f" El detalle completo quedó en {respaldo} (recuperable con "
             "memory_search).") if respaldo else ""
    tarea = f" Tarea vigente: {str(objetivo).strip()[:600]}." if objetivo else ""
    return {
        "role": "user",
        "content": (
            f"{PREFIJO_COMPACCION} {cantidad} mensajes anteriores (zona fría) "
            "fueron compactados para no reenviar todo el historial." + donde +
            tarea + " Continuá desde la ventana caliente de abajo."
        ),
    }


# Función principal

def compactar(messages, max_chars, ventana=VENTANA_DEFAULT, respaldo=None,
              objetivo=None):
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
    `respaldo` es la ruta donde el LLAMADOR ya guardó la zona fría: va en el
    texto del marcador. Esta función no escribe nada (sigue siendo pura).
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
    nuevo = [original[0], _resumen(frios, respaldo, objetivo)] + original[corte:]
    # Si la ventana caliente sola ya pesa más que el tope, la compacción NO
    # achica (medido: 9 mensajes/60.403 chars → 8/60.644) y el llamador
    # re-compactaría en cada ronda sin bajar nunca. Si no achica, no se toca.
    return nuevo if _tamano(nuevo) < _tamano(original) else original


# Recorte del contenido de tool results viejos (exp/91)

def _marcador_recorte(contenido):
    """El marcador que reemplaza un resultado viejo: prefijo que lo delata
    como recortado, cabeza y cola como anclas y el conteo de lo comido."""
    cabeza = contenido[:CABEZA_RECORTE]
    cola = contenido[-COLA_RECORTE:]
    comidos = len(contenido) - len(cabeza) - len(cola)
    return f"{PREFIJO_RECORTE} {cabeza} [… {comidos} chars recortados …] {cola}"


def recortar_tools_viejos(messages, mantener=MANTENER_TOOLS):
    """Recorta el CONTENIDO de los tool results viejos. PURA: no muta el input.

    Cuando la ventana caliente sola supera `max_chars`, `compactar` es no-op y
    el historial se clava: cada ronda reenvía los resultados enteros de
    lecturas que ya nadie mira (medido, sesión exp/88: 60–75k por ronda).
    Se recorta el contenido de TODOS los tool messages salvo los últimos
    `mantener` (los que el modelo está usando ahora), respetando la
    ESTRUCTURA (roles, `tool_call_id`, unidades assistant+tools): los
    invariantes del modo thinking y el candado `validar_historial` quedan
    intactos.

    Idempotente por `PREFIJO_RECORTE`: un recortado no se vuelve a recortar.
    Los resultados cortos (< `UMBRAL_RECORTE`) ni se tocan.
    """
    if not isinstance(messages, list):
        return list(messages or [])
    indices = [i for i, m in enumerate(messages)
               if isinstance(m, dict) and m.get("role") == "tool"]
    viejos = set(indices[:-mantener] if mantener > 0 else indices)
    nuevo = []
    for i, m in enumerate(messages):
        contenido = m.get("content") if i in viejos and isinstance(m, dict) else None
        if (isinstance(contenido, str) and len(contenido) > UMBRAL_RECORTE
                and not contenido.startswith(PREFIJO_RECORTE)):
            marcador = _marcador_recorte(contenido)
            # si no achica, no se toca (mismo principio que compactar): un
            # contenido apenas sobre el umbral puede ser más corto que el
            # marcador (cabeza+cola+prefijo ~640) y recortarlo lo INFLARÍA
            # (hallazgo del juez de fable sobre exp/91)
            if len(marcador) < len(contenido):
                m = {**m, "content": marcador}
        nuevo.append(m)
    return nuevo
