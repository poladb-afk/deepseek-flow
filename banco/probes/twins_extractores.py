"""TWINS del patrón de extracción dependiente del fraseo (exp/84 → exp/85).

El patrón: un sitio LLM que clasifica HECHOS VERIFICABLES de prosa EXTERNA
sin que el código junte los hechos o marque candidatas delante del modelo.
exp/84 lo cerró en fable_judge (candidatas_verificacion); esta sonda busca
gemelos en el resto del harness y queda como CANDADO: todo sitio LLM del
producto está clasificado por archivo, y uno nuevo sin clasificar la hace
fallar (mismo espíritu que tests/test_docs_sin_deriva.py para los docs).

Categorías (definición congelada en banco/specs/exp85_twins.md):
  a) generación · b) contrato de salida · c) entrada estructurada/propia
  d) hechos del código delante · e) ejecutor con tools
Un GEMELO es un sitio que no entra en ninguna (prosa externa + hechos
verificables + código ausente).

El escaneo es por AST (los comentarios y docstrings no engañan) y cuenta
las llamadas `call_llm`/`call_llm_agent` MÁS las directas a la API (un
Constant con "chat/completions" — vision.py no usa el cliente compartido).

Uso: python3 banco/probes/twins_extractores.py
"""
import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent

# Registro congelado de exp/85 (la lectura sitio por sitio está en la
# bitácora). Cada archivo: (n_sitios, categorías, por qué no es gemelo).
# Un sitio NUEVO se detecta por conteo; un archivo nuevo, por el archivo.
REGISTRO = {
    "auditoria.py": (2, "c",
                     "síntesis de análisis generados por el propio flujo"),
    "debate.py": (3, "a/b",
                  "argumentos generados (a) y veredicto con assert+retry (b); "
                  "no hay hechos verificables en juego"),
    "fable_judge.py": (4, "d",
                       "diff + fuentes + candidatas_verificacion (exp/84): el "
                       "código junta todos los hechos"),
    "explorador.py": (1, "e",
                      "ejecutor con tools de sólo lectura (exp/97): el "
                      "system+código fijan la whitelist; devuelve resumen"),
    "informe.py": (1, "c", "síntesis map-reduce sobre resultados estructurados"),
    "juez.py": (3, "d",
                "el Judge recibe citas LEÍDAS del disco + inventario real de "
                "tools (exp/42); el CITA_RE es del código"),
    "main.py": (1, "a", "resumen de sesión: bookkeeping, prosa de prosa"),
    "nodes.py": (3, "e/d",
                 "chat ejecutor con tools (e); corrección de citas con las "
                 "citas verificadas por utils/citas contra el disco (d); "
                 "árbitro del voto tras las reglas deterministas de exp/54 (d)"),
    "research.py": (4, "b/d/a",
                    "plan y decisión yaml (b); los hechos se extraen del "
                    "material que el código fetch-eó, URLs ya delante (d); "
                    "informe final (a)"),
    "sonda_supervisor.py": (1, "b", "plan yaml con args: contrato de salida"),
    "supervisor.py": (2, "e/c",
                      "UnPaso es ejecutor con tools (e); la síntesis va sobre "
                      "pasos registrados del propio bucle (c)"),
    "modules/vision.py": (2, "a",
                          "API directa (chat/completions): el código carga la "
                          "imagen/PDF y sus límites delante; el modelo describe"),
}

_EXCLUIDOS = {"tests", "banco", "salidas", ".venv", "__pycache__", "docs"}


def _es_llamada_llm(nodo):
    if isinstance(nodo.func, ast.Name) and nodo.func.id in ("call_llm", "call_llm_agent"):
        return True
    # llamada directa a la API: un constant con la ruta del endpoint
    return any(isinstance(a, ast.Constant) and "chat/completions" in str(a.value)
               for a in ast.walk(nodo))


def sitios_llm(raiz=None):
    """Inventario determinista por AST: {archivo: n_sitios_llm}."""
    raiz = Path(raiz) if raiz else RAIZ
    inventario = {}
    for ruta in sorted(raiz.rglob("*.py")):
        partes = set(ruta.relative_to(raiz).parts)
        if partes & _EXCLUIDOS or ruta.name in ("call_llm.py",):
            continue
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        n = sum(1 for nodo in ast.walk(arbol)
                if isinstance(nodo, ast.Call) and _es_llamada_llm(nodo))
        if n:
            inventario[ruta.relative_to(raiz).as_posix()] = n
    return inventario


def gemelos(inventario, registro=None):
    """Los archivos con sitios LLM que el registro no cubre (con su motivo)."""
    registro = registro if registro is not None else REGISTRO
    faltantes = []
    for archivo, n in sorted(inventario.items()):
        if archivo not in registro:
            faltantes.append(f"{archivo}: {n} sitio(s) LLM SIN CLASIFICAR")
        elif registro[archivo][0] != n:
            faltantes.append(
                f"{archivo}: el registro congela {registro[archivo][0]} sitio(s) "
                f"y hay {n} — clasificá el nuevo (o actualizá el conteo a propósito)")
    return faltantes


def main():
    inventario = sitios_llm()
    print("Sitios LLM del producto (categorías: a generación · b contrato de "
          "salida · c entrada estructurada · d hechos del código · e tools):")
    for archivo, n in sorted(inventario.items()):
        entrada = REGISTRO.get(archivo)
        if entrada:
            print(f"  {archivo} ({n}): {entrada[1]} — {entrada[2]}")
        else:
            print(f"  {archivo} ({n}): SIN CLASIFICAR")
    problemas = gemelos(inventario)
    if problemas:
        print("\nGEMELOS/SIN CLASIFICAR:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("\nTWINS: busqué el patrón de exp/84 — encontré 0 gemelos: todo "
          "sitio con prosa externa tiene los hechos del código delante.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
