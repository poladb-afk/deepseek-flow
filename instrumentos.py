"""Instrumentos compartidos del laboratorio (X165): lo que usan evals,
replay, tablero, triaje, la minería de errores, los benches y la sonda del
supervisor, y el producto no.

Vivían en `utils/` (`git`, `formato`, `rutas`, `trazas`, `votacion`) y
`lineas_del_producto` los contaba como producto. `utils/` queda para lo que
usa el producto (`test_cada_pieza_de_utils_la_usa_el_producto`).

- `DIR_RUNS`, `DIR_SALIDA`: carpetas de trabajo de los CLI (relativas al CWD).
- `pct`: una fracción como porcentaje para los informes markdown.
- `sha_corto`, `sha_o_motivo`: la identidad git que anclan informes y
  baselines (best-effort: git no es dependencia).
- `leer_eventos`: lectura tolerante de trazas `.jsonl`.
- `mayoria`: la votación N-de-M de la sonda del supervisor.
"""
import json
import subprocess
from collections import Counter
from pathlib import Path

DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")


def pct(fraccion):
    """Una fracción (0.734) como porcentaje legible ("73.4%"); None → "—"."""
    return f"{fraccion * 100:.1f}%" if fraccion is not None else "—"


def _correr(argumentos: list[str], timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argumentos, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def sha_corto(timeout: int = 5) -> str:
    """sha corto del HEAD; "" si git no está o el repo no está inicializado."""
    resultado = _correr(["git", "rev-parse", "--short", "HEAD"], timeout)
    return resultado.stdout.strip() if resultado is not None and resultado.returncode == 0 else ""


def sha_o_motivo(timeout: int = 5) -> str:
    """sha LARGO del HEAD; si git falla, el motivo como texto (para el informe).

    Un fallo de git se muestra en el markdown, no se silencia (el baseline
    del bench ancla contra el sha completo).
    """
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=timeout
        )
        return resultado.stdout.strip() if resultado.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as exc:
        return f"(git no disponible: {type(exc).__name__})"


def leer_eventos(archivo) -> list[dict]:
    """Eventos de un .jsonl; [] si el archivo es ilegible o una línea no es JSON.

    Tolera el archivo ausente; una línea corrupta descarta el archivo entero
    (la semántica histórica de evals — el contrato es "todo o nada", no
    parcial). La usan evals, replay y triaje_trazas.
    """
    eventos = []
    try:
        for linea in Path(archivo).read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea:
                eventos.append(json.loads(linea))
    except (json.JSONDecodeError, OSError):
        return []
    return eventos


def mayoria(votos, desempate=None, minimo=2):
    """La opción con `minimo` votos coincidentes; sin ella, el desempate.

    >>> mayoria(["sql", "sql", "finish"])
    'sql'
    >>> mayoria(["sql", "db_schema", "finish"], desempate="sql")
    'sql'
    """
    conteo = Counter(votos)
    if not conteo:
        return desempate
    (opcion, n), *resto = conteo.most_common()
    empate = bool(resto) and resto[0][1] == n
    if n >= minimo and not empate:
        return opcion
    return desempate if desempate is not None else opcion
