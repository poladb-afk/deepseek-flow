"""Conjuntos conformales para los juicios de Laya (exp/30).

Qué agrega sobre un umbral a mano: en vez de "0.85 porque ahí estaba la
rodilla", se elige un riesgo alpha y el umbral SALE de los datos de
calibración, con la corrección de muestra finita. La regla de decisión es la
de una cascada: se acepta el juicio local solo si el conjunto de etiquetas
plausibles COLAPSA a una; si no, se deriva al árbitro (DeepSeek).

Por qué: Conformal Cascade (arXiv:2607.25018) documenta que "los umbrales de
confianza en producción están miscalibrados, hay que tunearlos por par de
modelos y por dominio, y ningún setting da una cota formal de accuracy"; el
tamaño del conjunto conformal sí da una cobertura marginal >= 1-alpha bajo
intercambiabilidad. Es la versión auditable de las compuertas 0.85/0.7/0.9.

Binario a propósito: los contratos de Laya acá son de 2 opciones (router,
voto) o de ranking (prefiltro). El despacho de 18 opciones del supervisor NO
entra: la propia Laya documenta caída con espacios grandes de etiquetas.

Código puro: sin LLM, sin red, sin estado. Determinista.
"""
import json
import math
from pathlib import Path


def cuantil_conformal(puntajes, alpha):
    """El cuantil q de los puntajes de calibración para un riesgo alpha.

    Índice ceil((n+1)*(1-alpha)) sobre los puntajes ordenados: es la
    corrección de muestra finita. Con n=30 y alpha=0.05 el índice es 30 (el
    máximo de los puntajes, o sea el umbral más permisivo posible): ESO es
    información — con 30 casos no se puede prometer más que eso. Si el índice
    supera n (p. ej. n=30, alpha=0.02) no hay cota posible y se devuelve inf,
    que en la regla significa derivar SIEMPRE.
    """
    if not puntajes:
        raise ValueError("sin puntajes de calibración")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha fuera de (0, 1): {alpha}")
    ordenados = sorted(puntajes)
    n = len(ordenados)
    indice = math.ceil((n + 1) * (1.0 - alpha))
    if indice > n:
        return math.inf
    return ordenados[indice - 1]


def puntaje(conf, correcto):
    """El puntaje conformal de un caso binario: 1 - p(etiqueta verdadera).

    Laya devuelve answer_confidence = p(opción elegida). Si acertó, la
    verdadera es la elegida; si no, es la otra."""
    return (1.0 - conf) if correcto else conf


def conjunto(conf, q):
    """El conjunto de etiquetas plausibles de un binario dado q.

    ("elegida",) = colapsa, se decide local; ("elegida", "otra") = ambiguo,
    se deriva. La regla es la de la cascada: aceptar solo si es un singleton.
    """
    if q == math.inf:
        return ("elegida", "otra")
    umbral = 1.0 - q
    plausibles = tuple(
        nombre for nombre, p in (("elegida", conf), ("otra", 1.0 - conf)) if p >= umbral
    )
    return plausibles or ("elegida", "otra")


def leer_calibracion(ruta):
    """Los casos de calibración desde un JSONL (o un JSON con clave "casos").

    Formato: una línea por caso, {"conf": 0.93, "correcto": true}. Es el
    artefacto que produce banco/probes/etiquetar_router.py (etiquetado ciego,
    en distribución). El test del fine-tune NO sirve para calibrar: la cota
    dejaría de valer."""
    path = Path(ruta)
    if not path.is_file():
        raise FileNotFoundError(f"sin calibración: {path}")
    if path.suffix == ".json":
        datos = json.loads(path.read_text(encoding="utf-8"))
        crudos = datos.get("casos", datos) if isinstance(datos, dict) else datos
    else:
        crudos = [
            json.loads(linea)
            for linea in path.read_text(encoding="utf-8").splitlines()
            if linea.strip()
        ]
    casos = [
        {"conf": float(c["conf"]), "correcto": bool(c["correcto"])}
        for c in crudos
        if "conf" in c and "correcto" in c
    ]
    if not casos:
        raise ValueError(f"calibración vacía o sin forma: {path}")
    return casos


def q_de_calibracion(casos, alpha):
    """El q conformal de esos casos, o None si con ese n no hay cota posible."""
    q = cuantil_conformal([puntaje(c["conf"], c["correcto"]) for c in casos], alpha)
    return None if q == math.inf else q


def evaluar(casos, q):
    """(n, cobertura, aceptadas, precision) con un q YA calibrado en OTRO set.

    Es la evaluación honesta de la cascada: calibrar en A y medir en B.
    Cobertura = la etiqueta verdadera entró al conjunto; aceptadas = fracción
    de decisiones tomables localmente (conjunto singleton); precision =
    cuántas de esas eran correctas."""
    n = len(casos)
    if n == 0:
        raise ValueError("sin casos para evaluar")
    dentro = aceptadas = aciertos = 0
    for caso in casos:
        if puntaje(caso["conf"], caso["correcto"]) <= q:
            dentro += 1
        if len(conjunto(caso["conf"], q)) == 1:
            aceptadas += 1
            if caso["correcto"]:
                aciertos += 1
    return {
        "n": n,
        "cobertura": dentro / n,
        "aceptadas": aceptadas / n,
        "precision": (aciertos / aceptadas) if aceptadas else None,
    }


def cobertura_loo(casos, alpha):
    """(cobertura, aceptadas, precision) por leave-one-out.

    Evaluar sobre el MISMO conjunto con el que se calibró es optimista; el
    LOO recalibra sin el caso evaluado y es la estimación honesta con n
    chico. `casos`: [{"conf": float, "correcto": bool}, ...].
    """
    n = len(casos)
    if n < 3:
        raise ValueError("hacen falta al menos 3 casos de calibración")
    dentro = aceptadas = aciertos = 0
    for i, caso in enumerate(casos):
        otros = [puntaje(c["conf"], c["correcto"]) for j, c in enumerate(casos) if j != i]
        q = cuantil_conformal(otros, alpha)
        if puntaje(caso["conf"], caso["correcto"]) <= q:
            dentro += 1
        if len(conjunto(caso["conf"], q)) == 1:
            aceptadas += 1
            if caso["correcto"]:
                aciertos += 1
    return {
        "cobertura": dentro / n,
        "aceptadas": aceptadas / n,
        "precision": (aciertos / aceptadas) if aceptadas else None,
    }
