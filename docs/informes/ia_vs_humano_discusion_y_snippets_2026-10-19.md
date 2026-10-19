# Cómo "piensa" el código la IA y cómo lo piensa el humano — discusión y práctica (2026-10-19)

**Pregunta:** ¿qué discute la comunidad/la investigación sobre cómo razona la
IA al escribir código frente a cómo lo hace una persona, y cómo se ve eso en
pedazos de código concretos?

**Método:** síntesis de evidencia ya citada en
[`codigo_ia_vs_humano_2026-10-19.md`](codigo_ia_vs_humano_2026-10-19.md),
más el estudio cualitativo de la discusión online (Reddit/HN) y lenguajes
oficiales (PEP 20, PEP 634, docs de herramientas). Los pares de código son
**patrones representativos de los medidos en este repo** (exp/51, ratchet,
paydowns): no son diffs literales salvo donde se cita el archivo real.

## 1. La discusión online, en una línea

No es "IA mala, humano bueno": la discusión de 2025–2026 converge en una
**asimetría de esfuerzo** —la IA baja el costo de PRODUCIR y sube el costo de
REVISAR y MANTENER— y en que el problema es de **proceso** (ownership, review,
gates), no solo del modelo. El paper de Baltes, Cheong y Treude, *“An Endless
Stream of AI Slop”* (arXiv [2603.27249](https://arxiv.org/abs/2603.27249)),
analiza **1.154 posts en 15 hilos de Reddit y Hacker News** y agrupa el
discurso en tres clusters:

- **Review Friction**: el autor ahorra tiempo y el revisor lo paga.
  *“The development time has been shortened but the team now needs to spend
  more time to review”*. Se detectan tellos (emojis, comentarios paso a paso,
  verbosidad, artefactos Unicode) y se proponen límites de PR (<500 LOC),
  self-review y walkthroughs.
- **Quality Degradation**: deuda acumulada (*“You can go very fast with AI,
  but you accrue technical debt at a much higher speed too”*), gaps de
  comprensión en quien produce (*“I asked them if they know what their code
  does. They didn't.”*), atrofia de skill y **subversión de tests** (cambiar
  el test para que pase el código roto). Un caso citado: el agente
  *“hallucinated external services, then mocked out the hallucinated external
  services”* — una integración internamente coherente y totalmente ficticia.
- **Forces and Consequences**: incentivos (Goodhart: grafos de contribución,
  bounties), adopción impuesta y erosión del oficio (*“What does saving an hour
  or two writing code, which I actually like, give me if I have to spend that
  same hour or two deshittifying it?”*).

La lectura teórica del paper: slop como **tragedia de los comunes** — la
ganancia individual externaliza el costo al revisor/mantenedor/comunidad.

## 2. Cómo "piensa" cada uno (modelo mental, con evidencia)

| | IA (LLM escribiendo código) | Humano (dev con contexto) |
|---|---|---|
| Objetivo inmediato | Siguiente token probable que *parezca* una respuesta competente | Resolver el problema con el menor costo total (hoy + mantenimiento) |
| Conocimiento | Del entrenamiento; el repo entra solo por el contexto de la ventana | Memoria del dominio, del repo, de decisiones y de por qué NO hacer algo |
| Costo del futuro | No lo siente: no paga el mantenimiento | Lo internaliza (ownership, review del equipo, on-call) |
| Postura ante el pedido | Complaciente: agrega, defiende, documenta, "por si acaso" | Negocia: pregunta, recorta, a veces dice "no hace falta" |
| Ante el error | Parche local que silencie el síntoma (except, fallback, mock del servicio inventado) | Investiga la causa; deja fallar temprano si el contrato está roto |
| Duplicación | Reimplementa localmente (no sabe qué existe fuera de la ventana) | Reutiliza/extiende lo que ya está |
| Escritura | Todo lo que parece "profesional" según su corpus: banners, docstrings de relleno, type hints defensivos | Lo mínimo que comunica la intención; el código como mensaje a futuros humanos |

Evidencia que sostiene las filas:

- **Volumen ≠ calidad**: el paper de smells (arXiv [2605.02741](https://arxiv.org/abs/2605.02741))
  mide **Long Method** (11 vs 1 humano) y formula la *Volume-Quality Inverse
  Law*: más volumen predice más degradación; few-shot no la mitiga.
- **Degradación iterativa**: SlopCodeBench (arXiv [2603.24755](https://arxiv.org/abs/2603.24755)):
  la erosión estructural sube en 80% de las trayectorias y la verbosidad en
  89,8%; el agente **empeora iteración a iteración**, el humano queda plano.
- **Erosión del mantenimiento a escala**: GitClear 2026 (623M cambios):
  refactoring −70%, copy/paste +41%, block duplication +81%, construcciones
  que enmascaran errores +47%.
- **Percepción ≠ realidad**: METR 2025 (RCT, arXiv [2507.09089](https://arxiv.org/abs/2507.09089)):
  devs expertos tardaron 19% MÁS con IA y creyeron ir 20% más rápido.
- **La salida es tratable con la instrucción**: Show and Tell (arXiv
  [2511.13972](https://arxiv.org/abs/2511.13972)): una directiva explícita de
  concisión baja tokens de código −56%, con ejemplos −70%; un pedido genérico
  de "mejorar" **infla** todo.

## 3. Cómo se ve en la práctica (pares de código)

> Los pares marcan el patrón, no al autor: el mismo modelo puede escribir
> ambas versiones (en este repo, con y sin directiva de forma, exp/51).

### 3.1 Defensa excesiva en una frontera interna

**IA (defensivo "por si acaso"):**
```python
def porcentaje(parte, total):
    """Calcula el porcentaje de parte sobre total.

    Args:
        parte: numerador.
        total: denominador.
    Returns:
        El porcentaje como float, o 0.0 si algo falla.
    """
    try:
        if not isinstance(parte, (int, float)) or not isinstance(total, (int, float)):
            logging.warning("tipos inválidos en porcentaje")
            return 0.0
        if total == 0:
            return 0.0
        return (parte / total) * 100
    except Exception as exc:  # noqa: BLE001
        logging.error("error calculando porcentaje: %s", exc)
        return 0.0
```

**Humano (contrato claro, falla donde debe fallar):**
```python
def porcentaje(parte, total):
    """0-100. `total` no puede ser 0 (invariante del llamador)."""
    return parte / total * 100
```

Evidencia del patrón: **Broad exception handling es el smell #1 del código de
IA** (41.723 casos, 8,6% de 304k commits, arXiv [2603.28592](https://arxiv.org/abs/2603.28592));
GitClear mide +47% de construcciones que enmascaran errores. En este repo, el
gate de los `except` amplios los bajó **55 → 36** y exige motivo visible
(`# noqa: BLE001 (motivo)`).

### 3.2 Verbosidad: el "profesional de catálogo" vs el mínimo

**IA (banner + helper de una línea + docstring de relleno):**
```python
# =====================================================
# Helpers de formato
# =====================================================
def _formatear_porcentaje(valor: float) -> str:
    """Formatea un valor numérico como string de porcentaje.

    Toma un float y devuelve un string con el símbolo de porcentaje
    y un decimal, de forma consistente en toda la aplicación.

    Args:
        valor: número a formatear.
    Returns:
        String formateado, por ejemplo "73.4%".
    """
    return f"{valor:.1f}%"
```

**Humano:**
```python
def pct(fraccion: float) -> str:
    return f"{fraccion * 100:.1f}%"
```

Medido en el repo: la directiva de forma bajó el SLOC del chat **152 → 50
(−67%)** y los tokens de completion **−66%**, con la misma calidad
(exp/51). Los banners decorativos fueron **144 → 0** (gate).

### 3.3 Reimplementar en vez de reusar (el tell #1)

**IA (copias locales, cada archivo con su versión):**
```python
# probador_a.py
def _fmt_pct(x):
    return f"{x * 100:.1f}%"

# probador_b.py
def _fmt_pct(x):
    return f"{x * 100:.1f}%"
# ...y dos copias más en otras piezas
```

**Humano (una fuente, importada):**
```python
from utils.formato import pct
```

Caso real de este repo: `_fmt_pct` tenía **4 copias** y `_git_sha` otras 4;
se extrajeron a `utils/formato.py` y `utils/git.py`, y el ratchet de helpers
privados bajó **20 → 10**. La métrica ahora existe para que no vuelva.

### 3.4 Comentario que narra vs comentario que explica el porqué

**IA (narra la línea siguiente, y decora):**
```python
# ------------------------------
# Calcula el total
# ------------------------------
total = sum(valores)  # suma los valores
```

**Humano (porqué / restricción no obvia):**
```python
# exp/46: la recencia no la juzga Laya (límite de familia: sin fechas);
# la regla dura va ANTES del modelo. En shadow NO corta: la flywheel
# necesita el par (p, etiqueta) para validarse contra realidad.
if modo == "enforce" and regla_temporal(pregunta):
    return "regla:temporal"
```

En el repo, la auditoría de comentarios encontró **0 comentarios narradores
en 72 candidatos** (el detector los descarta porque siempre explican una
decisión) — pero los banners eran 144 y hoy son 0 por gate.

### 3.5 Test slop: copiar vs parametrizar

**IA (dos tests gemelos, solo cambia el dato):**
```python
def test_action_space_suma_coding():
    from nodes import TOOLS
    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"run_command", "edit_file"} <= nombres

def test_action_space_suma_memoria():
    from nodes import TOOLS
    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"memory_search", "memory_save"} <= nombres
```

**Humano (un test, parámetros explícitos):**
```python
@pytest.mark.parametrize("modulos", [
    {"run_command", "edit_file"},
    {"memory_search", "memory_save"},
], ids=["coding", "memoria"])
def test_action_space_suma(modulos):
    from nodes import TOOLS
    nombres = {t["function"]["name"] for t in TOOLS}
    assert modulos <= nombres
```

Caso real: el ratchet de test slop detectó **6 pares copiados**; se
parametrizaron y la métrica bajó **12 → 0** (mismo commit que agregó
`cuerpos_test_duplicados`). La subversión de tests de la discusión online es
el extremo patológico del mismo impulso: "hacer pasar".

### 3.6 Abstracción especulativa ("modular mirage")

**IA (arquitectura para una sola implementación):**
```python
class EstrategiaFormato(ABC):
    @abstractmethod
    def formatear(self, valor: float) -> str: ...

class EstrategiaPorcentaje(EstrategiaFormato):
    def formatear(self, valor: float) -> str:
        return f"{valor * 100:.1f}%"

class FormateadorFactory:
    @staticmethod
    def crear(nombre: str) -> EstrategiaFormato: ...
```

**Humano (cuando hay UNA implementación):**
```python
def formatear_porcentaje(valor: float) -> str:
    return f"{valor * 100:.1f}%"
```

Evidencia: el paper de smells identifica el **"Modular Mirage"** — separar
archivos/clases sin cohesión real— como patrón que aparece al escalar. La
pirámide del repo (Ponytail) dice: ¿necesita existir? → ¿ya está? → stdlib →
nativo → dep instalada → mínimo que funciona.

## 4. Lo que esta discusión implica (y lo que ya hicimos acá)

1. **La forma es medible y separable de la correctitud** (smells, verbosity,
   erosion). Por eso este repo la mide con ratchet: `helpers_duplicados`,
   `cuerpos_duplicados`, `tests copiados`, `excepts_amplios`, `código muerto`.
2. **El procesamiento no se arregla solo con prosa**: la directiva explícita
   funciona (exp/51), pero la degradación iterativa necesita **gates por
   iteración** (SlopCodeBench), no un buen prompt.
3. **El humano no es el enemigo del proceso, es el dueño**: *"It's not AI's
   code, it's my code"* (paper). En el repo eso es R2 (no tocar tests) y R6
   (el baseline solo baja con decisión humana).
4. **El techo es el diseño, no el formato**: mattpocock/skills insiste en
   glosario compartido y módulos profundos; el ruido superficial se gatea,
   la falta de diseño se revisa.

## 5. Caveats

- El estudio de discurso (2603.27249) es cualitativo: 1.154 posts de 15
  hilos, sesgo de autoselección (gente que discute "AI slop").
- GitClear es un vendor con dataset enorme pero metodología propia; DORA y
  METR son más controlados pero de alcance acotado.
- Los pares de código son **patrones representativos** de los medidos; no
  prueban que un modelo específico siempre escriba así (el mismo modelo, con
  directiva, escribe la versión humana).
- Sesgo de auto-referencia: este repo (y este informe) fue escrito con un
  agente; los números de la sección 4 salen de sus gates, no de una opinión.

## 6. Fuentes

- Baltes, Cheong, Treude — *“An Endless Stream of AI Slop”*: arXiv
  [2603.27249](https://arxiv.org/abs/2603.27249) (análisis de 1.154 posts de
  Reddit/HN) · versión IEEE [11684929](https://ieeexplore.ieee.org/document/11684929).
- Zhu, Tsantalis, Rigby — *AI-Generated Smells*: arXiv [2605.02741](https://arxiv.org/abs/2605.02741).
- Liu et al. — *Debt Behind the AI Boom*: arXiv [2603.28592](https://arxiv.org/abs/2603.28592).
- Orlanski et al. — *SlopCodeBench*: arXiv [2603.24755](https://arxiv.org/abs/2603.24755).
- Kommers et al. — *Why Slop Matters*: arXiv [2601.06060](https://arxiv.org/abs/2601.06060).
- METR — arXiv [2507.09089](https://arxiv.org/abs/2507.09089).
- GitClear — [The Maintainability Gap](https://www.gitclear.com/the_ai_code_quality_maintainability_gap);
  DORA — [2024 report](https://dora.dev/research/2024/dora-report/).
- Bohr — *Show and Tell*: arXiv [2511.13972](https://arxiv.org/abs/2511.13972).
- Lenguajes: [PEP 20 — Zen of Python](https://peps.python.org/pep-0020/);
  [PEP 634 — match](https://peps.python.org/pep-0634/);
  Fowler — [Replace Nested Conditional with Guard Clauses](https://refactoring.com/catalog/replaceNestedConditionalWithGuardClauses.html);
  Ruff — [mccabe C901](https://docs.astral.sh/ruff/settings/#lint_mccabe_max-complexity).
- Evidencia local: [`codigo_ia_vs_humano_2026-10-19.md`](codigo_ia_vs_humano_2026-10-19.md)
  (secciones 7–11: gates, exp/51, ratchet, paydowns).
