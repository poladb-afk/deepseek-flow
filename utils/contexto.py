"""Pre-filtro de contexto por Laya (Mesa 6, 12-factor #5).

El patrón de la wild: no mandar todo el contexto al prompt — dejar que un
juicio barato y LOCAL (Laya, ms) elija qué fragmentos/notas entran ANTES
de pagar tokens (reportado ~80% de costo/tiempo en recuperación).

Regla de hierro: **un retriever no debe perder recall por un modelo
ausente**. Si no hay checkpoint disponible, o el puntaje falla por
cualquier motivo, entran TODOS los chunks (o los primeros `max_unidades`).
Laya es un acelerador opcional, no una dependencia: su ausencia deja el
comportamiento idéntico al de hoy.

Hay dos consumidores del filtro (rag_search, memory_search); ambos usan
los mismos helpers de acá para no derivar. El contrato del prompt se
declara (como los del router: congelado) y el checkpoint se lee de un
setting (`LAYA_MODEL_PREFILTRO`). Sin checkpoint entrenado todavía, el
filtro es no-op — cercado por tests."""

# Contrato del pre-filtro: una sola opción binaria ("¿este bloque ayuda a
# responder la consulta?"). El estado es {"consulta", "bloque"}; el fine-tune
# (cuando exista) lee esto byte a byte.
PREGUNTA_PREFILTRO = {
    "aporta_contexto": {
        "type": "choice",
        "instructions": (
            "Does this block of text help answer the query directly "
            "(mentions the topic, a required fact, a definition, or a "
            "concrete instruction needed to answer)? Answer 'si' if it does, "
            "'no' if it is tangential, boilerplate, or unrelated."
        ),
        "criteria": {
            "si": "the block mentions the query's subject or a fact needed to answer",
            "no": "the block is tangential, boilerplate, log noise, or unrelated",
        },
    }
}

DEFAULT_MODEL_SETTING = "LAYA_MODEL_PREFILTRO"


def unidades_bloques(texto):
    """Corta un texto (markdown/plano) en bloques atómicos sin partir
    ninguno: una línea en blanco o un encabezado markdown (`# `) abre bloque
    nuevo. La unidad mínima indivisible es el párrafo; devuelve la lista de
    strings no vacíos, en orden original."""
    if not texto:
        return []
    bloques, actual = [], []
    for linea in texto.splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            if actual:
                bloques.append("\n".join(actual).strip())
                actual = []
            if linea.strip():  # el encabezado abre bloque (no se descarta)
                actual = [linea]
            continue
        actual.append(linea)
    if actual:
        bloques.append("\n".join(actual).strip())
    return [b for b in bloques if b]


def elegir_por_laya(consulta, unidades, max_unidades, setting_modelo=DEFAULT_MODEL_SETTING):
    """Reordena/recorta `unidades` por relevancia a `consulta` según Laya.

    Devuelve las mejores `max_unidades` **en orden original** (la relevancia
    decide QUÉ entra, no el orden de presentación). Con `max_unidades <= 0`,
    con una sola unidad, o sin Laya disponible, devuelve `unidades` intactas:
    el default seguro es no perder recall."""
    unidades = list(unidades)
    if not unidades or max_unidades <= 0 or len(unidades) <= max_unidades:
        return unidades
    puntajes = _puntuar(consulta, unidades, setting_modelo)
    if puntajes is None:
        return unidades[:max_unidades]  # sin juicio: no se pierde nada de más
    # empate estable: el orden original desempata (determinismo)
    orden = sorted(range(len(unidades)), key=lambda i: (-puntajes[i], i))
    elegidos = sorted(orden[:max_unidades])  # vuelven en orden original
    return [unidades[i] for i in elegidos]


def _puntuar(consulta, unidades, setting_modelo):
    """{índice: probabilidad} de que cada unidad aporte. None si Laya no
    está o algo falla (el llamador cae al default seguro)."""
    try:
        from utils.laya import disponible, preguntar

        if not disponible(setting_modelo):
            return None
        puntajes = {}
        for i, unidad in enumerate(unidades):
            estado = {"consulta": str(consulta)[:1000], "bloque": str(unidad)[:2000]}
            # clave estable por índice: preguntar() devuelve {id: (resp, conf)}
            contrato = {"aporta_contexto": PREGUNTA_PREFILTRO["aporta_contexto"]}
            resp = preguntar(estado, contrato, setting=setting_modelo)["aporta_contexto"]
            respuesta, confianza = resp
            puntajes[i] = confianza if respuesta == "si" else 1.0 - confianza
        return puntajes
    except Exception:  # cualquier fallo: sin juicio (default seguro)
        return None