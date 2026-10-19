"""A/B de exp/52-B en el chat real: ¿el corte por novedad ahorra rondas?

Corre el escenario `exp52b-redundante-off/on` (mismo prompt; el único cambio
es `CORTE_NOVEDAD=0` vs `2`) por el banco y mide, desde la TRAZA de cada
sesión: rondas por pregunta, si el corte por novedad se disparó, y si la
sesión terminó OK. Criterio pre-registrado (exp/52-A/52-B): la regla sirve si
baja rondas en el turno redundante SIN bajar los turnos OK. Si no, se
documenta el negativo y el default queda en 0.

Uso: python3 banco/probes/ab_novedad.py [--runs 2]
Gasta API (dos sesiones de banco por run y brazo). Artefactos en salidas/.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rondas  # noqa: E402

ESCENARIOS = {
    "off": "banco/escenarios/exp52b-redundante-off.yaml",
    "on": "banco/escenarios/exp52b-redundante-on.yaml",
}


def trazas_antes():
    return {ruta.name for ruta in (RAIZ / ".runs").glob("*.jsonl")}


def traza_nueva(antes):
    """La traza de chat que apareció después de la corrida (la más nueva)."""
    nuevas = [r for r in (RAIZ / ".runs").glob("*.jsonl") if r.name not in antes]
    chats = []
    for ruta in nuevas:
        eventos = rondas.leer_sesion(ruta)
        if rondas.es_sesion_chat(eventos):
            chats.append((ruta.stat().st_mtime, ruta, eventos))
    if not chats:
        return None, []
    _, ruta, eventos = max(chats, key=lambda x: x[0])
    return ruta, eventos


def contar_cortes(eventos):
    return sum(1 for e in eventos
               if e.get("nodo") == "corte_sin_novedad" and e.get("accion") == "politica")


def correr_sesion(brazo):
    antes = trazas_antes()
    inicio = time.perf_counter()
    proceso = subprocess.run([sys.executable, "banco/banco.py", ESCENARIOS[brazo]],
                             cwd=RAIZ, capture_output=True, text=True, timeout=900)
    segundos = round(time.perf_counter() - inicio, 1)
    ruta, eventos = traza_nueva(antes)
    if ruta is None:
        return {"brazo": brazo, "ok": False, "segundos": segundos,
                "motivo": "sin traza de chat", "ciclos": [], "cortes": 0}
    ciclos = rondas.ciclos(eventos)
    return {
        "brazo": brazo,
        "ok": proceso.returncode == 0,
        "segundos": segundos,
        "traza": ruta.name,
        "ciclos": [{"rondas": c["rondas"], "respondio": c["respondio"]} for c in ciclos],
        "rondas": [c["rondas"] for c in ciclos],
        "cortes": contar_cortes(eventos),
    }


def mediana(valores):
    return statistics.median(valores) if valores else None


def main_probe(argv=None):
    parser = argparse.ArgumentParser(description="A/B de corte por novedad (exp/52-B)")
    parser.add_argument("--runs", type=int, default=2, help="corridas por brazo (default 2)")
    args = parser.parse_args(argv)

    filas = []
    for turno in range(args.runs):
        for brazo in ("off", "on"):
            print(f"  · {brazo}/r{turno + 1}…", flush=True)
            fila = correr_sesion(brazo)
            fila["run"] = turno + 1
            filas.append(fila)
            print(f"    ok={fila['ok']} rondas={fila.get('rondas')} cortes={fila.get('cortes')} "
                  f"seg={fila['segundos']}", flush=True)

    print(f"\n== exp/52-B A/B chat real (n={args.runs} por brazo) ==")
    for brazo in ("off", "on"):
        sel = [f for f in filas if f["brazo"] == brazo and f["ok"]]
        rondas_totales = [sum(f["rondas"]) for f in sel]
        print(f"{brazo:3}: sesiones OK {len(sel)}/{args.runs} · rondas totales "
              f"{rondas_totales} (mediana {mediana(rondas_totales)}) · "
              f"cortes {sum(f['cortes'] for f in sel)} · "
              f"tiempo mediano {mediana([f['segundos'] for f in sel])} s")
        for f in sel:
            print(f"      r{f['run']}: ciclos={f['rondas']} cortes={f['cortes']} traza={f['traza']}")

    destino = RAIZ / "salidas" / "probes"
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / f"ab_novedad_{datetime.now():%Y%m%d_%H%M%S}.json"
    salida.write_text(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"),
                                  "runs": args.runs, "filas": filas}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"artefacto: {salida.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main_probe())
