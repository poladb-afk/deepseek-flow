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


def _contexto_extra(ruta, pregunta):
    """Ventanas alrededor de identificadores de la pregunta que caen MÁS ALLÁ
    de las primeras 200 líneas. El excerpt fijo de 200 era correcto cuando los
    archivos eran chicos; al crecer (fs_tools 514, nodes 807) dejó afuera
    `list_files`, `sanitizar`, `COMPACTION_CHARS` y friends → regresión del
    bench del juez (70,6% vs 94,1% baseline). Código puro, best-effort."""
    resolved, err = _resolve(str(ruta))
    if err or resolved is None or not resolved.is_file():
        return ""
    try:
        lineas = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if len(lineas) <= 200:
        return ""
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", str(pregunta)))
    ventanas, vistas = [], set()

    def _agregar(i, etiqueta):
        inicio, fin = max(1, i - 8), min(len(lineas), i + 8)
        cuerpo = "\n".join(f"{n}: {lineas[n - 1]}" for n in range(inicio, fin + 1))
        ventanas.append(f"(contexto de {etiqueta}: líneas {inicio}-{fin})\n{cuerpo}")
        vistas.add(i)

    for token in sorted(tokens):
        if token.isupper() or "_" in token:
            patron = re.compile(rf"\b{re.escape(token)}\b")
        else:
            patron = re.compile(
                rf"(?:\bdef\s+{re.escape(token)}\b|\bclass\s+{re.escape(token)}\b|"
                rf"\b{re.escape(token)}\b\s*=)")
        for i, linea in enumerate(lineas[200:], start=201):
            if patron.search(linea):
                _agregar(i, token)
                break
        if len(ventanas) >= 6:
            break
    # Si la pregunta no nombra símbolos (p. ej. "¿qué tools trae el CORE?"),
    # sumar las primeras definiciones después de la línea 200: son las
    # candidatas naturales de la respuesta.
    if len(ventanas) < 6:
        for i, linea in enumerate(lineas[200:], start=201):
            if i in vistas:
                continue
            if re.match(r"\s*(?:def|class)\s+[A-Za-z_]\w*", linea):
                _agregar(i, "definición")
            if len(ventanas) >= 6:
                break
    if not ventanas:
        return ""
    cabecera = (f"\n--- contexto adicional de {ruta} (símbolos después de la "
                "línea 200; ESTAS líneas también son citables) ---")
    return cabecera + "\n" + "\n".join(ventanas)


def _archivos_de(texto):
    """Resuelve las rutas de archivo mencionadas en un texto (pregunta)."""
    rutas = []
    for m in ARCHIVO_RE.findall(texto):
        resolved, err = _resolve(m)
        if not err and resolved.is_file():
            rutas.append(resolved)
    return rutas[:MAX_CTX_ARCHIVOS]


# exp/42 (hallazgo 2 de exp/20, residual de exp/21): el Draft alucinó la
# herramienta inexistente `delete_file` en 3/3 corridas y el Judge no podía
# notarlo porque nunca vio el inventario real. Mismo patrón de la casa que
# las citas: el hecho lo reúne el CÓDIGO (los nombres reales del action
# space), no el juicio del modelo.
#
# Un nombre "con pinta de herramienta": snake_case con al menos un guión bajo
# (delete_file, run_supervisor, read_file...). Los nombres cortos sin `_`
# del inventario (sql, debate) no se detectan como candidatos para no marcar
# cualquier palabra suelta; el costo es que un inventario futuro con nombres
# de una palabra no se contrastaría si el Draft los inventa — el sesgo va
# hacia NO dar falsos positivos.
TOOL_NAME_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
# Palabras que delatan que el candidato se menciona COMO herramienta (usar,
# describir, llamar) — no como variable o ruta cualquiera. Filtrar por esta
# ventana evita marcar snake_case genérico del borrador.
#
# exp/42 sesión 4 (lesión 1, medida con LLM real): 'función'/'funciones' quedó
# FUERA a propósito. La trampa es sobre HERRAMIENTAS, no sobre funciones del
# código: el borrador de thinking-tools dice "la función call_llm_agent hace
# X" y 'función' como contexto marcaba ['reasoning_content', 'tool_calls',
# 'call_llm_agent', 'call_llm'] — discutir una función interna no es afirmar
# una tool. Se exige contexto explícito de tool (herramienta/tool + verbos de
# uso).
TOOL_CONTEXTO_RE = re.compile(
    r"herramienta|tool|us[aá]r?|usand[oa]|ejecut[aá]r?|invoc[aá]r?|llam[aá]r?",
    re.IGNORECASE,
)
# exp/42 sesión 4 (lesión 2, medida con LLM real): un token que vive DENTRO de
# una ruta o de un nombre de archivo no es un claim de herramienta. El borrador
# de search-vacio cita '.../utils/fs_tools.py' en una línea con contexto de
# tool y el segmento 'fs_tools' se marcaba. Antes de buscar candidatos se
# borran de la línea (a) las citas ruta:línea (formato que pide el Draft) y
# (b) todo token con pinta de ruta/archivo, extinguiendo los sufijos .py/.md/
# .jsonl y compañía. Así 'utils/fs_tools.py' y 'juez.py:57' no dejan residuo.
CITA_RUTA_LINEA_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]{2,4}:\d+")
RUTA_O_ARCHIVO_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]{2,4}")


def _inventario_tools():
    """Nombres REALES de herramientas del action space, importados — no
    hardcodeados. `nodes` junta el CORE con los módulos vía discover() y ese
    discover() corre al importarse: por eso el import es PEREZOSO (mismo
    patrón documentado en modules/supervisor.py), para no armar un ciclo ni
    pagar el registro entero al cargar juez.py."""
    from nodes import MODULE_IMPLS, TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    nombres |= set(MODULE_IMPLS.keys())
    return nombres


def _tools_alucinadas(texto, inventario):
    """Nombres con pinta de herramienta que el borrador menciona COMO
    herramienta pero que NO existen en el inventario real. Función pura:
    el contraste contra el action space es un hecho del código, no una
    opinión del juez.

    Dos lecciones MEDIDAS con el bench de LLM real (exp/42 sesión 4) que
    esta función incorpora para no dar falsos positivos en borradores
    legítimos:
    (1) SEGMENTOS DE RUTA: 'utils/fs_tools.py' citado en una línea con
        contexto de tool NO es un claim de herramienta — un trozo de path no
        afirma que exista la tool `fs_tools`. Por eso se borran las citas
        ruta:línea y los tokens con pinta de ruta/archivo antes de buscar
        candidatos.
    (2) FUNCIONES INTERNAS: 'la función call_llm_agent hace X' discute código
        del propio proyecto, no afirma una tool — por eso 'función'/'funciones'
        no vive en TOOL_CONTEXTO_RE.
    La trampa sigue viva: 'usá la herramienta delete_file' marca delete_file.
    """
    inventario = set(inventario)
    alucinadas = []
    for linea in (texto or "").splitlines():
        if not TOOL_CONTEXTO_RE.search(linea):
            continue  # la línea no habla de herramientas: nada que contrastar
        # ni citas ruta:línea ni nombres de archivo/ruta cuentan como claims
        linea = CITA_RUTA_LINEA_RE.sub(" ", linea)
        linea = RUTA_O_ARCHIVO_RE.sub(" ", linea)
        for nombre in TOOL_NAME_RE.findall(linea):
            if nombre not in inventario and nombre not in alucinadas:
                alucinadas.append(nombre)
    return alucinadas


class Draft(Node):
    def prep(self, shared):
        contexto = ""
        for ruta in _archivos_de(shared["question"]):
            frag = read_file(str(ruta), offset=1, limit=200)
            if not frag.startswith("ERROR"):
                contexto += f"\n--- {ruta} ---\n{frag}\n"
                contexto += _contexto_extra(ruta, shared["question"])
        return shared["question"], contexto, shared.get("feedback"), shared.get("draft")

    def exec(self, inputs):
        question, contexto, feedback, anterior = inputs
        prompt = f"Responde en español, preciso y conciso:\n\n{question}"
        if contexto:
            prompt += (
                "\n\nContexto verificado de los archivos mencionados "
                f"(contenido real; NO inventes nada que no esté acá):{contexto}"
                "\nCita las fuentes en el formato ruta_absoluta:línea. "
                "Cuando cites una función, constante o setting, usá la línea "
                "EXACTA donde aparece definido (no el inicio del bloque ni un "
                "comentario cercano). Si el dato es un mensaje o valor literal, "
                "citá la línea EXACTA donde aparece el literal (no la definición "
                "de la función que lo devuelve)."
            )
        if feedback:
            prompt += (
                "\n\nUn juez encontró estos problemas en tu intento "
                f"anterior; corrígelos:\n{feedback}"
            )
            if anterior:
                # corregía a ciegas: el refinamiento recibe su borrador EXACTO
                prompt += (
                    "\n\n--- tu intento anterior (verbatim) ---\n"
                    f"{anterior[:2000]}\n--- fin ---"
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


def _cita_rota(frag, linea):
    """Una cita NO resuelve si read_file devolvió ERROR o si la línea citada
    está más allá del final del archivo (fuera de rango: el fragmento llega
    vacío y sin ERROR). Es un hecho del código, no una opinión del juez."""
    if frag.startswith("ERROR"):
        return True
    cabecera = frag.splitlines()[0] if frag else ""
    m = re.search(r"de (\d+)\]$", cabecera)
    return bool(m) and int(linea) > int(m.group(1))


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
            if _cita_rota(frag, linea):
                # el marcador viaja al prompt Y habilita la compuerta de exec
                citas.append(f"[ROTA] {path}:{linea} → {frag}")
            else:
                real = "\n".join(frag.splitlines()[1:3])[:300]
                citas.append(f"{path}:{linea} → contenido real:\n{real}")
        se_esperaban = bool(_archivos_de(shared["question"]))
        return shared["question"], shared["draft"], citas, se_esperaban

    def exec(self, inputs):
        question, draft, citas, se_esperaban = inputs
        # exp/42: las herramientas alucinadas se computan ACÁ (exec ya recibe
        # el borrador) y no en prep, para no cambiar la aridad prep→exec: el
        # contrato observable del Judge (sus veredictos) no cambió, solo DÓNDE
        # se computa un hecho interno. El inventario se importa perezosamente.
        alucinadas = _tools_alucinadas(draft or "", _inventario_tools())
        citas_txt = "\n".join(citas) or "(el borrador no cita archivos)"
        aviso = ""
        if se_esperaban and not citas:
            aviso = (
                "\nATENCIÓN: la pregunta se refiere a archivos concretos y el "
                "borrador NO cita ninguno en formato ruta:línea. Eso es un "
                "problema grave de verificabilidad."
            )
        if alucinadas:
            aviso += (
                "\nATENCIÓN: el borrador menciona como herramienta algo que "
                f"NO existe en el action space: {', '.join(alucinadas)}. "
                "Una herramienta inventada es un problema grave (alucinación)."
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
        rotas = sum(1 for c in citas if c.startswith("[ROTA]"))

        def _compuerta(v):
            """Hechos del código por encima del juicio del modelo (C07): con
            verdict ok el flujo ENTREGABA un borrador citando una ruta
            inexistente (medido). Si alguna cita no resuelve, hay retry. Y
            con una herramienta inventada (exp/42) tampoco se entrega: el
            inventario real lo aporta el código, no el modelo."""
            if v.get("verdict") != "ok":
                return v
            problemas = list(v.get("problems", []))
            if rotas:
                print(colorear(
                    "  [juez] cita rota con verdict ok → retry (hecho del código)",
                    "aviso"), flush=True)
                problemas.insert(0,
                    f"{rotas} cita(s) del borrador no resuelven contra los "
                    "archivos reales (ruta inexistente o línea fuera de rango)")
            if alucinadas:
                print(colorear(
                    "  [juez] herramienta inexistente con verdict ok → retry "
                    "(hecho del código)", "aviso"), flush=True)
                problemas.append(
                    "el borrador menciona como herramienta algo que no existe "
                    f"en el action space: {', '.join(alucinadas)}")
            if problemas != list(v.get("problems", [])):
                return {"verdict": "retry", "problems": problemas}
            return v

        crudo = call_llm(prompt)
        veredicto, motivo = _validar(crudo)
        if veredicto is not None:
            return _compuerta(veredicto)
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
            return _compuerta(veredicto)
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
