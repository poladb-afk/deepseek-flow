"""Juez: patrón evaluator-optimizer con Structured Output.

Draft responde; Judge evalúa en YAML (verdict: ok/retry) y si el borrador
cita archivos (ruta:línea), los LEE y verifica las citas contra el
contenido real — el antídoto contra desvíentes como citar "línea 20"
cuando la real es la 25. Un YAML roto o inválido lanza en exec() y el
retry del Node vuelve a preguntar. Máx JUEZ_ROUNDS rondas: al llegar al
tope se entrega lo último con una advertencia (ley L8 de bmo: el bucle se
autoacota).

Uso: python3 main.py juez "pregunta"
"""
import argparse
import re

from pocketflow import Flow, Node

from utils.call_llm import call_llm
from utils.estructura import extraer_yaml
from utils.fs_tools import _resolve, read_file

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

Evalúa el borrador: precisión factual (las citas DEBEN coincidir con el
contenido real; una cita que no coincide es un problema grave),
completitud respecto de la pregunta y claridad.

Responde SOLO yaml:
```yaml
verdict: ok
problems:
  - <problema 1>
suggestions:
  - <sugerencia 1>
```"""
        veredicto = extraer_yaml(call_llm(prompt))
        assert veredicto["verdict"] in ("ok", "retry"), "verdict inválido"
        assert isinstance(veredicto.get("problems", []), list), "problems no es lista"
        return veredicto

    def post(self, shared, prep_res, exec_res):
        rounds = shared.get("rounds", 1)
        if exec_res["verdict"] == "ok" or rounds >= JUEZ_ROUNDS:
            if exec_res["verdict"] != "ok":
                shared["advertencia"] = (
                    f"El juez seguía insatisfecho al llegar al tope de "
                    f"{JUEZ_ROUNDS} rondas; se entrega el último borrador."
                )
            return "entregar"
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


def responder_con_juez(pregunta):
    shared = {"question": pregunta}
    create_juez_flow().run(shared)
    return shared["draft"], shared.get("advertencia")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="juez", description="Responder con borrador → juez → refinamiento"
    )
    parser.add_argument("pregunta", help="la pregunta")
    parser.add_argument("--rondas", type=int, default=JUEZ_ROUNDS, help="(no usado aún)")
    args = parser.parse_args(argv)

    respuesta, advertencia = responder_con_juez(args.pregunta)
    print(f"\nRespuesta (juzgada):\n{respuesta}")
    if advertencia:
        print(f"\n⚠️  {advertencia}")


if __name__ == "__main__":
    main()
