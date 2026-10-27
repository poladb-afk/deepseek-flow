"""F — sacar del prompt lo que la estructura reemplazó (pre-registro: banco/specs/f_prompt.md)

Tres brazos sobre las auditorías de fable: el prompt de producción, sin la
directiva de citas (s15–s20) y sin la de alcance (s17–s20). Cada directiva se
compara con base solo donde su estructura decide, y el criterio exige probar
que la estructura corrió (X82: medí la pieza donde decide).

Uso:
    python3 banco/probes/f_prompt.py                         # 48 corridas (~4 h)
    python3 banco/probes/f_prompt.py --brazos base,sin_citas --seeds 1
    python3 banco/probes/f_prompt.py --resumen
"""
import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_fable as bf  # noqa: E402
from h3b_swarm import tokens_del_log  # noqa: E402

EXP = "f-prompt"
CITAS = ("s15-python-bug-hunt", "s16-hard-bug-hunt", "s17-scale-audit",
         "s18-real-audit", "s19-real-audit-2", "s20-real-audit-3")
AMPLIOS = CITAS[2:]
BASE = {"PROMPT_FABLE": "0", "SKILLS": "0"}
BRAZOS = {
    "base": (BASE, CITAS),
    "sin_citas": ({**BASE, "PROMPT_CITAS": "0"}, CITAS),
    "sin_alcance": ({**BASE, "PROMPT_ALCANCE": "0"}, AMPLIOS),
}
DIRECTIVAS = {"sin_citas": "citas", "sin_alcance": "alcance"}
COSTO_MAX = 1.10
SEEDS_MIN = 2
RE_CITAS = re.compile(r"\[citas\] \d+/[1-9]\d* verificadas")
RE_AMPLIO = re.compile(r"⚙ ronda \d+/16\b")
RE_CORREGIDAS = re.compile(r"DeepSeek \(citas corregidas\)")


def evidencia(log):
    """Lo que prueba que la estructura decidió en ESTA corrida."""
    return {"citas_vistas": bool(RE_CITAS.search(log or "")),
            "tope_amplio": bool(RE_AMPLIO.search(log or "")),
            "correcciones": len(RE_CORREGIDAS.findall(log or ""))}


def correr(brazo, escenario, seed):
    env, _ = BRAZOS[brazo]
    r = bf.correr_uno(EXP, escenario, brazo, seed, forzar=True, salir=True, env=env)
    log = r.pop("log")
    uso = tokens_del_log(log)
    return {"brazo": brazo, "escenario": escenario, "seed": seed,
            "calidad": r["correct_action"], "citas_invalidas": r["checks"].get("citas_invalidas"),
            "tokens": uso[1] if uso else None, "rondas": r["rondas"], **evidencia(log),
            "seg": r["seg"], "error": r["error"] or (None if uso else "sin línea [tokens]")}


def _media(valores):
    valores = [v for v in valores if v is not None]
    return sum(valores) / len(valores) if valores else None


def _medidas(filas):
    return {"n": len(filas), "calidad": _media(f["calidad"] for f in filas),
            "citas_invalidas": sum(f["citas_invalidas"] or 0 for f in filas),
            "tokens": _media(f["tokens"] for f in filas)}


def veredicto(filas):
    """El criterio de banco/specs/f_prompt.md, sin retoques. PURA."""
    salida = {}
    for brazo, directiva in DIRECTIVAS.items():
        escenarios = BRAZOS[brazo][1]
        prueba = [f for f in filas if f["brazo"] == brazo and f["escenario"] in escenarios]
        base = [f for f in filas if f["brazo"] == "base" and f["escenario"] in escenarios]
        clave = "citas_vistas" if directiva == "citas" else "tope_amplio"
        cobertura = {e: sum(1 for f in prueba if f["escenario"] == e and f[clave]) for e in escenarios}
        mp, mb = _medidas(prueba), _medidas(base)
        completo = bool(prueba and base) and None not in (mp["calidad"], mb["calidad"], mp["tokens"], mb["tokens"])
        condiciones = {
            "cobertura": all(n >= SEEDS_MIN for n in cobertura.values()),
            "calidad": completo and mp["calidad"] >= mb["calidad"],
            "citas": completo and mp["citas_invalidas"] <= mb["citas_invalidas"],
            "costo": completo and mp["tokens"] <= COSTO_MAX * mb["tokens"],
        }
        gana = completo and all(condiciones.values())
        salida[directiva] = {
            "brazo": brazo, "medidas": {"prueba": mp, "base": mb}, "cobertura": cobertura,
            "correcciones": sum(f["correcciones"] for f in prueba),
            "condiciones": condiciones, "completo": completo, "gana": gana,
            "decision": (f"se borra la directiva de {directiva} (y PROMPT_{directiva.upper()})" if gana else
                         f"la directiva de {directiva} se queda (se borra solo PROMPT_{directiva.upper()})")
            if completo else "faltan datos: no hay veredicto",
        }
    return salida


def _fmt(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def resumen(filas):
    v = veredicto(filas)
    L = ["# F — sacar del prompt lo que la estructura reemplazó", "",
         "Criterio pre-registrado: banco/specs/f_prompt.md.", ""]
    for directiva, d in v.items():
        mp, mb = d["medidas"]["prueba"], d["medidas"]["base"]
        L += [f"## {directiva} ({d['brazo']} vs base)", "",
              "| brazo | n | calidad media | citas inválidas | tokens medios |", "|---|---|---|---|---|",
              f"| base | {mb['n']} | {_fmt(mb['calidad'])} | {mb['citas_invalidas']} | {_fmt(mb['tokens'], 0)} |",
              f"| {d['brazo']} | {mp['n']} | {_fmt(mp['calidad'])} | {mp['citas_invalidas']} | {_fmt(mp['tokens'], 0)} |",
              "", "Cobertura (seeds donde la estructura decidió): "
              + ", ".join(f"{e}={n}" for e, n in d["cobertura"].items())
              + f" · correcciones de VerificarCitas: {d['correcciones']}", ""]
        L += [f"- {c}: {'✅' if ok else '❌'}" for c, ok in d["condiciones"].items()]
        L += ["", f"**Veredicto:** {'GANA' if d['gana'] else 'NO GANA'} → {d['decision']}", ""]
    return "\n".join(L)


def _ruta():
    return bf.SALIDAS / "resultados" / f"{EXP}.jsonl"


def cargar():
    ruta = _ruta()
    return [json.loads(ln) for ln in ruta.read_text(encoding="utf-8").splitlines() if ln.strip()] if ruta.is_file() else []


def guardar(fila):
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    clave = (fila["brazo"], fila["escenario"], fila["seed"])
    filas = [r for r in cargar() if (r["brazo"], r["escenario"], r["seed"]) != clave] + [fila]
    ruta.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="f_prompt", description="F: directivas del prompt vs su estructura")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--brazos", default=",".join(BRAZOS))
    parser.add_argument("--resumen", action="store_true", help="solo escribe el resumen de lo ya corrido")
    args = parser.parse_args(argv)
    if not args.resumen:
        for seed in (int(s) for s in args.seeds.split(",") if s.strip()):
            for brazo in (b.strip() for b in args.brazos.split(",") if b.strip()):
                for escenario in BRAZOS[brazo][1]:
                    fila = correr(brazo, escenario, seed)
                    guardar(fila)
                    print(f"[f] {brazo} s{seed} {escenario}: calidad={fila['calidad']} tokens={fila['tokens']} "
                          f"citas={fila['citas_vistas']} tope16={fila['tope_amplio']} err={fila['error'] or '-'}",
                          flush=True)
    texto = resumen(cargar())
    destino = bf.SALIDAS / "resultados" / f"{EXP}-resumen.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"[f] resumen → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
