"""Juez: patrón evaluator-optimizer con Structured Output.

Draft responde; Judge evalúa en YAML (verdict: ok/retry) y si el borrador
cita archivos (ruta:línea), los LEE y verifica las citas contra el
contenido real — el antídoto contra desvíentes como citar "línea 20"
cuando la real es la 25. Un YAML roto o inválido lanza en exec() y el
retry del Node vuelve a preguntar. El tope de rondas es JUEZ_ROUNDS (default
2, configurable por corrida con `--rondas` o shared["max_rounds"]): al llegar
al tope se entrega lo último con una advertencia (ley L8 de bmo: el bucle se
autoacota).

Uso: python3 main.py juez "pregunta" [--rondas N]
"""
import argparse
import re

from pocketflow import Flow, Node

from utils.call_llm import call_llm
from utils.estructura import extraer_yaml
from utils.fs_tools import _resolve, read_file
from utils.terminal import colorear

JUEZ_ROUNDS = 2
CITA_RE = re.compile(r"(/[\w./-]+\.[\w]+):(\d+)")
ARCHIVO_RE = re.compile(r"[\w./-]+\.[\w]{2,4}")
MAX_CITAS = 5
MAX_CTX_ARCHIVOS = 3


def _archivos_de(texto):
    """Resuelve las rutas de archivo mencionadas en un texto (pregunta)."""
    rutas = []
    for m in ARCHIVO_RE.findall(texto):
        resolved, err = _resolve(m)
        if not err and resolved.is_file():
            rutas.append(resolved)
    return rutas[:MAX_CTX_ARCHIVOS]


class Draft(Node):
    def prep(self, shared):
        contexto = ""
        for ruta in _archivos_de(shared["question"]):
            frag = read_file(str(ruta), offset=1, limit=200)
            if not frag.startswith("ERROR"):
                contexto += f"\n--- {ruta} ---\n{frag}\n"
        return shared["question"], contexto, shared.get("feedback")

    def exec(self, inputs):
        question, contexto, feedback = inputs
        prompt = f"Responde en español, preciso y conciso:\n\n{question}"
        if contexto:
            prompt += (
                "\n\nContexto verificado de los archivos mencionados "
                f"(contenido real; NO inventes nada que no esté acá):{contexto}"
                "\nCita las fuentes en el formato ruta_absoluta:línea."
            )
        if feedback:
            prompt += (
                "\n\nUn juez encontró estos problemas en tu intento "
                f"anterior; corrígelos:\n{feedback}"
            )
        return call_llm(prompt)

    def post(self, shared, prep_res, exec_res):
        shared["draft"] = exec_res
        shared["rounds"] = shared.get("rounds", 0) + 1


def _recorte(texto, n=300):
    """Recorta un texto VERBATIM a ~n chars, marcando si se truncó."""
    texto = str(texto)
    return texto[:n] + ("…" if len(texto) > n else "")


# Marcador del prompt del Judge: distingue SUS llamadas de las del Draft.
# Lo importa el probe (banco/probes/verdict_juez.py), que antes lo copiaba:
# si cambia la redacción, cambia acá y no en dos sitios.
MARCA_JUDGE = "Evalúa el borrador"


def _canonico(verdict):
    """Canonicaliza el verdict: case/whitespace son ruido de codificación, no
    semántica. Definición ÚNICA: la comparten la validación, la normalización
    de _validar y el probe."""
    return verdict.strip().lower() if isinstance(verdict, str) else verdict


def _veredicto_valido(d):
    """Valida el veredicto contra AMBAS condiciones del contrato.

    Devuelve (bool, motivo). La canonicalización str/strip/lower NO es
    parche: case/whitespace son ruido de codificación, no semántica. El
    contrato no se afloja: cualquier otra palabra ('needs_changes',
    'OK!', 'entregar') queda inválida — y ahora es el feedback del
    reintento el que la endereza, no un alias clavado.
    """
    if not isinstance(d, dict):
        return False, "el YAML no es un diccionario de veredicto"
    crudo = d.get("verdict")
    canon = _canonico(crudo)
    if canon not in ("ok", "retry"):
        return False, f"verdict inválido: {crudo!r} (se esperaba ok o retry)"
    if "problems" in d and not isinstance(d["problems"], list):
        return False, f"problems no es lista: {type(d['problems']).__name__}"
    return True, ""


def _validar(crudo):
    """Parsea el crudo (extraer_yaml puede revantar) y valida.

    Devuelve (veredicto_canonicalizado, motivo) con veredicto None si
    inválido. extraer_yaml levantando es UN caso más de invalidez para el
    loop de reparación: nada escapa de exec por el verdict.
    """
    try:
        d = extraer_yaml(crudo)
    except Exception as e:
        return None, f"el YAML no parseó: {e}"
    ok, motivo = _veredicto_valido(d)
    if not ok:
        return None, motivo
    d["verdict"] = _canonico(d["verdict"])
    d.setdefault("problems", [])
    return d, ""


class Judge(Node):
    def prep(self, shared):
        """Hechos verificables en código: las líneas reales de cada cita."""
        citas = []
        for path, linea in CITA_RE.findall(shared["draft"] or "")[:MAX_CITAS]:
            frag = read_file(path, offset=int(linea), limit=2)
            if frag.startswith("ERROR"):
                citas.append(f"{path}:{linea} → {frag}")
            else:
                real = "\n".join(frag.splitlines()[1:3])[:300]
                citas.append(f"{path}:{linea} → contenido real:\n{real}")
        se_esperaban = bool(_archivos_de(shared["question"]))
        return shared["question"], shared["draft"], citas, se_esperaban

    def exec(self, inputs):
        question, draft, citas, se_esperaban = inputs
        citas_txt = "\n".join(citas) or "(el borrador no cita archivos)"
        aviso = ""
        if se_esperaban and not citas:
            aviso = (
                "\nATENCIÓN: la pregunta se refiere a archivos concretos y el "
                "borrador NO cita ninguno en formato ruta:línea. Eso es un "
                "problema grave de verificabilidad."
            )
        prompt = f"""Pregunta: {question}

Borrador a evaluar:
{draft}

Citas del borrador verificadas contra los archivos (contenido real):
{citas_txt}{aviso}

{MARCA_JUDGE}: precisión factual (las citas DEBEN coincidir con el
contenido real; una cita que no coincide es un problema grave),
completitud respecto de la pregunta y claridad.

Responde SOLO yaml:
```yaml
verdict: ok
problems:
  - <problema 1>
suggestions:
  - <sugerencia 1>
```

El campo verdict SOLO puede ser ok o retry, literal."""
        crudo = call_llm(prompt)
        veredicto, motivo = _validar(crudo)
        if veredicto is not None:
            return veredicto
        # Error-como-feedback (patrón del harness, exp/21 fase B2): un
        # verdict ilegible NO es un crash ni una entrega sin juzgar; es UN
        # reintento INFORMADO que cita al modelo su propia respuesta inválida
        # VERBATIM + el contrato. Un sinónimo nuevo lo atraviesa al parche de
        # alias; acá el modelo ve qué escribió y qué se esperaba.
        print(colorear(
            "  [juez] verdict ilegible → reintento con feedback", "aviso"
        ), flush=True)
        recorte = _recorte(crudo)
        feedback = (
            f"Tu respuesta anterior no cumplió el contrato:\n"
            f"--- respuesta recibida (verbatim) ---\n{recorte}\n"
            f"--- fin ---\n"
            f"Motivo: {motivo}\n"
            f"El campo verdict SOLO puede ser ok o retry, literal "
            f"(case/espacios se toleran); problems, si está, debe ser una "
            f"lista. Respondé de nuevo SOLO yaml."
        )
        crudo2 = call_llm(prompt + "\n\n" + feedback)
        veredicto, _ = _validar(crudo2)
        if veredicto is not None:
            return veredicto
        # Fallback semántico: ni con feedback validó. El lado SEGURO del
        # contrato binario — si no se puede confirmar ok, no está ok. El
        # borrador da una vuelta más con este problema como feedback, acotado
        # por max_rounds (L8); nunca se raise por verdict en exec.
        return {
            "verdict": "retry",
            "problems": [
                "el juez no pudo emitir un veredicto legible "
                f"(último crudo: {_recorte(crudo2)}); revisá precisión y "
                "citas del borrador"
            ],
        }

    def post(self, shared, prep_res, exec_res):
        rounds = shared.get("rounds", 1)
        # tope configurable por corrida (shared["max_rounds"]); default JUEZ_ROUNDS.
        max_rounds = shared.get("max_rounds", JUEZ_ROUNDS)
        if exec_res["verdict"] == "ok" or rounds >= max_rounds:
            if exec_res["verdict"] != "ok":
                shared["advertencia"] = (
                    f"El juez seguía insatisfecho al llegar al tope de "
                    f"{max_rounds} rondas; se entrega el último borrador."
                )
            return "entregar"
        # Contrato de shared["feedback"] (auditoría de consistencia 2026-10-05):
        # acá son BULLETS "- problema" (crítica del juez, se reinyecta al draft).
        # research.py reusa la MISMA clave con PROSA (huecos de cobertura).
        # Colisión semántica consciente: el vocabulario no se unifica (los
        # flujos son independientes y nunca comparten shared).
        shared["feedback"] = "\n".join(f"- {p}" for p in exec_res["problems"])
        return "retry"


class Entregar(Node):
    def post(self, shared, prep_res, exec_res):
        if shared.get("advertencia"):
            print(f"\n⚠️  {shared['advertencia']}")


def create_juez_flow():
    draft = Draft(max_retries=3, wait=5)
    judge = Judge(max_retries=3, wait=5)
    fin = Entregar()

    draft >> judge
    judge - "retry" >> draft
    judge - "entregar" >> fin

    return Flow(start=draft)


def responder_con_juez(pregunta, rondas=JUEZ_ROUNDS):
    shared = {"question": pregunta, "max_rounds": rondas}
    try:
        create_juez_flow().run(shared)
    except Exception:
        # Degradación terminal (mismo patrón que el tope de rondas, L8): si
        # el flujo revienta tras los retries (p. ej. el verdict sigue
        # ilegible), no se MATA: se entrega el último borrador con
        # advertencia explícita. Sin draft (el Draft también reventó),
        # se re-raise tal cual.
        if not shared.get("draft"):
            raise
        shared["advertencia"] = (
            "el juez no pudo emitir un veredicto legible; se entrega el "
            "borrador sin veredicto."
        )
    return shared["draft"], shared.get("advertencia")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="juez", description="Responder con borrador → juez → refinamiento"
    )
    parser.add_argument("pregunta", help="la pregunta")
    parser.add_argument("--rondas", type=int, default=JUEZ_ROUNDS,
                        help=f"tope de rondas de evaluación (default: {JUEZ_ROUNDS})")
    args = parser.parse_args(argv)

    if args.rondas < 1:
        raise SystemExit("ERROR: --rondas debe ser >= 1")
    respuesta, advertencia = responder_con_juez(args.pregunta, rondas=args.rondas)
    print(f"\nRespuesta (juzgada):\n{respuesta}")
    if advertencia:
        print(f"\n⚠️  {advertencia}")


if __name__ == "__main__":
    main()
