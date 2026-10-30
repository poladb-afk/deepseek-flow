"""Fase 5b: qué skill se cargó en cada turno del banco (read-only, sin LLM).

Lee los eventos `turno-fin` que deja `banco/banco.py` (cada uno trae el
conteo de marcadores del turno; `skill` cuenta las líneas `[skill] <id>
activo`) y el transcript, para saber CUÁL se cargó. Agrega las corridas de un
brazo y aplica el criterio de disparo pre-registrado en
`banco/specs/fase5b.md`. El costo y las rondas salen de `.runs` con
`banco/probes/tokens_runs.py`; las auditorías, de `bench_fable.py`.

Uso:
    python3 banco/probes/fase5b.py salidas/banco/fase5b-disparo_*.jsonl
"""
import json
import re
import sys
from pathlib import Path

# Lo que cada turno de fase5b-disparo tiene que cargar (None = ninguno).
ESPERADO = {
    "pos-revision-es": "revision",
    "pos-revision-en": "revision",
    "pos-revision-parafrasis": "revision",
    "pos-auditoria": "auditoria-seguridad",
    "neg-haiku": None,
    "neg-concepto": None,
    "neg-lectura": None,
}
_MARCA = re.compile(r"\[skill\] ([\w-]+) activo")


def skills_por_turno(eventos, transcript):
    """{turno: [ids cargados]} de UNA corrida. PURA.

    El transcript se parte por los `turno-inicio`/`turno-fin` en el orden en
    que aparecen las marcas: el banco no ecoa la pregunta, así que el conteo
    de `turno-fin` dice cuántas marcas le tocan a cada turno."""
    marcas = _MARCA.findall(transcript or "")
    por_turno, i = {}, 0
    for evento in eventos:
        if evento.get("tipo") != "turno-fin":
            continue
        detalle = evento.get("detalle") or {}
        n = int((detalle.get("marcadores") or {}).get("skill", 0))
        por_turno[detalle.get("id")] = marcas[i:i + n]
        i += n
    return por_turno


def veredicto_disparo(corridas, esperado=ESPERADO):
    """Criterio 1 de la 5b sobre las corridas de un brazo. PURA.

    Positivos: en CADA corrida, al menos 3 de 4 cargan el skill esperado.
    Negativos: 0 cargas en total. Un skill equivocado en un positivo cuenta
    como fallo de ese positivo."""
    positivos = [t for t, s in esperado.items() if s]
    negativos = [t for t, s in esperado.items() if not s]
    aciertos = [sum(1 for t in positivos if esperado[t] in corrida.get(t, [])) for corrida in corridas]
    cargas_negativas = sum(len(corrida.get(t, [])) for corrida in corridas for t in negativos)
    cumple = bool(corridas) and all(a >= 3 for a in aciertos) and cargas_negativas == 0
    return {"aciertos_por_corrida": aciertos, "de": len(positivos),
            "cargas_en_negativos": cargas_negativas, "cumple": cumple}


def _leer(ruta):
    eventos = []
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        try:
            eventos.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    log = Path(ruta).with_suffix(".log")
    return eventos, (log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")


def main(argv=None):
    rutas = [Path(r) for r in (argv if argv is not None else sys.argv[1:]) if not r.endswith("_hitl.jsonl")]
    if not rutas:
        print("pasá los eventos .jsonl de las corridas de un brazo")
        return 1
    corridas = [skills_por_turno(*_leer(r)) for r in rutas]
    for ruta, corrida in zip(rutas, corridas, strict=True):
        print(f"{ruta.name}: " + ", ".join(f"{t}={'+'.join(s) or '—'}" for t, s in corrida.items()))
    print(json.dumps(veredicto_disparo(corridas), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
