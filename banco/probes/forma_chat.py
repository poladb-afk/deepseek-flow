"""exp/51 (chat real) — la directiva de forma en el CHAT con tools + HITL.

La sonda `forma_codigo.py` mide llamadas one-shot. Acá se mide lo que el
harness HACE de verdad: una sesión de chat por PTY (banco), pidiendo escribir
un módulo con `write_file` y editarlo con `edit_file` (HITL aprobado por
scope). Los dos brazos son los escenarios `exp51-chat-on/off.yaml`, que solo
difieren en `PROMPT_FORMA=1|0`.

Uso: python3 banco/probes/forma_chat.py [--runs 2]
Gasta API (dos sesiones de chat por brazo) y deja los archivos generados en
salidas/probes/ (ignorado). Exit 0 siempre que haya al menos una sesión OK
por brazo.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forma_codigo import analizar_codigo  # noqa: E402  (mismas métricas)

ESCENARIOS = {"on": "banco/escenarios/exp51-chat-on.yaml",
              "off": "banco/escenarios/exp51-chat-off.yaml"}
ARCHIVO = RAIZ / "salidas" / "exp51" / "chat" / "modulo.py"
_METRICAS = ("sloc", "funciones", "docstrings_densidad", "try", "none_checks",
             "comentarios", "docstrings_relleno", "banners")


def correr_sesion(brazo, timeout):
    """Una sesión de banco; devuelve (ok, segundos, motivo)."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.unlink(missing_ok=True)
    inicio = time.perf_counter()
    proceso = subprocess.run(
        [sys.executable, "banco/banco.py", ESCENARIOS[brazo]],
        cwd=RAIZ, capture_output=True, text=True, timeout=timeout,
    )
    segundos = time.perf_counter() - inicio
    if proceso.returncode != 0:
        cola = (proceso.stderr or proceso.stdout or "").strip().splitlines()
        return False, segundos, f"banco exit {proceso.returncode}: {cola[-4:] if cola else 'sin salida'}"
    if not ARCHIVO.is_file():
        return False, segundos, "no se escribió salidas/exp51/chat/modulo.py"
    return True, segundos, ""


def mediana(filas, metrica):
    valores = [f["metricas"][metrica] for f in filas if f["metricas"]]
    return statistics.median(valores) if valores else None


def main_probe(argv=None):
    parser = argparse.ArgumentParser(description="A/B de la directiva de forma en el chat real (exp/51)")
    parser.add_argument("--runs", type=int, default=2, help="sesiones por brazo (default 2)")
    parser.add_argument("--timeout", type=int, default=420, help="timeout por sesión en segundos")
    args = parser.parse_args(argv)

    destino = RAIZ / "salidas" / "probes"
    destino.mkdir(parents=True, exist_ok=True)
    filas = []
    for turno in range(args.runs):
        for brazo in ("off", "on"):
            print(f"  · chat/{brazo}/r{turno + 1}…", flush=True)
            fila = {"brazo": brazo, "run": turno + 1, "error": None,
                    "segundos": None, "metricas": None, "archivo": None}
            try:
                ok, segundos, motivo = correr_sesion(brazo, args.timeout)
            except subprocess.TimeoutExpired:
                ok, segundos, motivo = False, args.timeout, "timeout de sesión"
            fila["segundos"] = round(segundos, 1)
            if not ok:
                fila["error"] = motivo
            else:
                codigo = ARCHIVO.read_text(encoding="utf-8")
                copia = destino / f"chat_{brazo}_r{turno + 1}.py"
                copia.write_text(codigo, encoding="utf-8")
                fila["archivo"] = str(copia.relative_to(RAIZ))
                try:
                    fila["metricas"] = analizar_codigo(codigo)
                except SyntaxError as exc:
                    fila["error"] = f"syntax: {exc}"
            filas.append(fila)

    print(f"\n== exp/51 chat real — directiva de forma (n={args.runs} por brazo) ==")
    print(f"{'métrica':22} {'sin_forma':>10} {'con_forma':>10} {'delta':>9}")
    for metrica in _METRICAS:
        off = mediana([f for f in filas if f["brazo"] == "off"], metrica)
        on = mediana([f for f in filas if f["brazo"] == "on"], metrica)
        if off is None or on is None:
            continue
        delta = f"{(on - off) / off * 100:+.0f}%" if off else "n/a"
        print(f"{metrica:22} {off:>10} {on:>10} {delta:>9}")
    print("\nsegundos por sesión: " + ", ".join(
        f"{f['brazo']}/r{f['run']}={f['segundos']}" for f in filas))
    errores = [f for f in filas if f["error"]]
    if errores:
        print("errores: " + "; ".join(f"{f['brazo']}/r{f['run']}: {f['error']}" for f in errores))
    print(f"artefacto: salidas/probes/ · corridas OK: {len(filas) - len(errores)}/{len(filas)}")
    salida = destino / f"forma_chat_{datetime.now():%Y%m%d_%H%M%S}.json"
    salida.write_text(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"),
                                  "runs": args.runs, "filas": filas}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    return 0 if len(errores) < len(filas) else 1


if __name__ == "__main__":
    sys.exit(main_probe())
