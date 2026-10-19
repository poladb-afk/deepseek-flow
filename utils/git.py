"""Identidad git del árbol para anclar informes y baselines (best-effort).

Los informes y baselines anotan el commit que produjo la medición. git no es
una dependencia del producto: si el árbol no está inicializado o git no está,
el informe sale igual (sin sha o con el motivo como texto). El nombre público
evita `sha` a secas para no chocar con la variable local `sha` que usan las
piezas que llaman a estas funciones.
"""
import subprocess


def _correr(argumentos: list[str], timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argumentos, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def sha_corto(timeout: int = 5) -> str:
    """sha corto del HEAD; "" si git no está o el repo no está inicializado."""
    resultado = _correr(["git", "rev-parse", "--short", "HEAD"], timeout)
    return resultado.stdout.strip() if resultado is not None and resultado.returncode == 0 else ""


def sha_largo(timeout: int = 5) -> str:
    """sha completo del HEAD; "" si git no está (para anclar baselines)."""
    resultado = _correr(["git", "rev-parse", "HEAD"], timeout)
    return resultado.stdout.strip() if resultado is not None and resultado.returncode == 0 else ""


def sha_o_motivo(timeout: int = 5) -> str:
    """sha LARGO del HEAD; si git falla, el motivo como texto (para el informe).

    Separado de `sha_largo` porque un fallo de git se muestra en el markdown,
    no se silencia (el baseline del bench ancla contra el sha completo).
    """
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=timeout
        )
        return resultado.stdout.strip() if resultado.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as exc:
        return f"(git no disponible: {type(exc).__name__})"
