# Estrategias por principio

> **Estado: borrador para revisión del operador (X192, 2026-11-07).** La
> arquitectura que estas estrategias sirven está en `docs/arquitectura.md`.

## La regla

Los principios son **la lógica de la que sale la estrategia de diseño**, no un
filtro que se cumple con lo mínimo. En consecuencia:

- **Un resultado negativo cierra una estrategia, no un principio.** Si pocas
  muestras dan mal, se buscan estrategias con otro mecanismo y se vuelve a
  probar.
- **Cerrar un principio constitutivo** exige las tres cosas: (1) al menos
  **tres estrategias con mecanismos distintos** (repetir la misma con otro
  modelo no cuenta); (2) probadas **en el régimen donde el principio predice
  ganar**; (3) la **decisión explícita del operador**.
- Sin ese criterio el principio se vuelve dogma ("faltó la estrategia
  correcta"); con él, se puede cerrar con honestidad.

## Constitutivos y regulativos

| Tipo | Qué son | Cómo se cambian | Cuáles |
|---|---|---|---|
| **Constitutivos** | definen **qué es** el harness: sin ellos es otro proyecto | solo por decisión del operador, nunca por una métrica | P2, P3, P4 (el grafo es su forma, no un principio aparte) |
| **Regulativos** | definen **cómo hacerlo bien** | se ajustan con evidencia | P1 |

Los números son los de `docs/principios.md` (X201, opción A). S0 y N1–N4 no
entran en esta clasificación: su columna "Cede ante" dice **Nada**, así que no
se ajustan con evidencia (antes N3 y N4 figuraban como regulativos, en contra
de esa precedencia).

**Cómo se perdió un principio sin que nadie lo decidiera** (para no repetirlo):
se midió la replicación y no ganó; el roadmap post-X150 dijo "no retoma
ninguna replicación"; se achicó dentro de la forma existente. Cada paso
cumplía las reglas y la suma dejó al fractal escrito y sin ningún paso que lo
sirviera. Es deriva por decisiones locales. Se evita revisando, principio por
principio, dónde está vivo en el código.

## P2 · Fractal

### Lo probado: un punto del espacio

| Experimento | Estrategia | Quién decidía replicar | Resultado |
|---|---|---|---|
| exp/103 (X127) | tool `dividir` ofrecida al chat, copias iguales | **el modelo** | NO PASA por adopción |
| exp/105 (X131) | la misma, con `deepseek-v4-pro` | **el modelo** | 0/72 llamadas a `dividir` |
| exp/110 (X150) | tres hijos especializados ofrecidos como tools | **el modelo** | 6 delegaciones en 24 corridas; NO PASA |

La variable que **no se movió** es quién decide replicar, y el banco eran
tareas que un agente solo ya resuelve: el régimen donde la literatura citada en
`docs/principios.md` (Kim et al.) predice que replicar no gana. **Lo refutado**:
"el modelo elige dividirse por su cuenta cuando se le ofrece, en tareas
cortas". **El fractal sigue abierto.**

### El espacio del swarm

El swarm puede no ser mejor para A o B y ser ideal para C. Su ventaja tiene
dos modos:

- **N estrategias simétricas con pequeñas diferencias**: sirven cuando la tarea
  tiene **varianza** (cada copia es un intento; un verificador elige). Mejora la
  probabilidad de que alguna acierte, no el intento promedio.
- **Estrategias con alto grado de diferenciación**: sirven cuando la tarea tiene
  **ancho** (muchas facetas, miradas opuestas). Un council es esto.

Lo medido hasta hoy: N chico, decidido por el modelo, diferenciación nula o
solo por tools, tareas cortas, métrica calidad por costo.

**El caso C ya está en los datos**: en la aceptación v1 (X176) la tarea T2 salió
**5 de 6** y la que falló gastó las 8 rondas leyendo sin editar. Es varianza, no
capacidad. Si las fallas fueran independientes, tres copias fallarían juntas
con probabilidad (1/6)³ ≈ 0,5 % contra 17 % de una sola. **Es una hipótesis**: la
independencia es justamente lo que hay que medir. El verificador ya existe:
`fable_judge`.

### Estrategias abiertas

| # | Estrategia | Variable que mueve |
|---|---|---|
| F1 | **Replicación estructural**: el grafo decide (research abre una copia por subpregunta; auditoría, una por carpeta) | quién decide: el harness, no el modelo |
| F2 | **Fractal como forma**: las capacidades como instancias de `kernel.loop` | la definición, no la ejecución (y es minimalismo) |
| F3 | **El régimen**: tareas que no entran en un contexto | el banco |
| F4 | **Otra métrica**: aislamiento de contexto, paralelismo, robustez | qué cuenta como ganancia |
| F5 | **Cómo se ofrece**: el esquema de la tool y cuándo se ofrece (sin prompt, N3) | la interfaz |
| F6 | **N simétricas + verificador** sobre tareas de varianza conocida (el caso C) | el modo del swarm |

**Regla de método para todas**: comparar **con el presupuesto igualado** (por
ejemplo, 3 copias de 8 rondas contra un agente de 24). Sin eso, la ventaja es
solo haber gastado más.

### El graduador (a futuro)

Elige N, diferenciación y profundidad según la necesidad, en escalones:
(1) **declarado** por quien arma el grafo; (2) **adaptativo por señales
medidas** (empezar con N = 1 y escalar si el verificador rechaza: la señal es
un hecho, no una lista de palabras); (3) **aprendido** (un juicio de Laya), cuando
haya datos de los dos primeros. **Hoy solo el escalón 1.**

## P4 · Emergente

**Ninguna estrategia se probó**: no se abandonó por evidencia, se abandonó por
inercia. Hoy las capacidades grandes son pipelines cableados, no composiciones.

| # | Estrategia | Estado |
|---|---|---|
| E1 | **Composición por conector**, declarada por el usuario: research + council (un consejo debate cómo encarar el research) | abierta: primera prueba de la arquitectura |
| E2 | **Copias + verificador** como capacidad nueva hecha de piezas existentes (F6) | abierta |

## P1, P3 y el grafo como forma

| Principio | Vivo hoy | Gate | Estrategia abierta |
|---|---|---|---|
| Grafo (la forma de P2; EL2) | el loop del kernel; el chat son 20 líneas que lo arman | `nodos_largos`, el diagrama del README es el grafo, sin calles muertas | las composiciones como aristas, no como código |
| P3 · Modular | `discover()`, `TOOLS`/`IMPLS`/`HOOKS` | `core_importa_modulos` 0, `producto_conoce_lab` 0 | el template con interconectores |
| P1 · Minimalismo | un solo loop (X126); `lineas_del_producto` solo baja | 5 métricas del ratchet | uno por capacidad; el catálogo para bajar `bytes_primer_request` |

## Lo que ya se probó afuera (X192b, por resumen)

El fractal no es una rareza: en 2026 hay una línea activa. Leído por resumen y
abstract (los números son de sus autores); la revisión de sus diseños es el
informe de X193b (`docs/informes/x193b_disenos_externos.md`), antes de escribir
el template.

| Fuente | Qué confirma de lo nuestro | Qué tomar | Dónde |
|---|---|---|---|
| Lár | el saldo compartido (`Ledger`) y la validación heredada (`hijas`, X147) | **una** puerta humana **antes del reduce**, con las filas por rama (no una puerta por rama) | S0 en la composición (X197) |
| FRACTAL | el swarm diferenciado dentro de un nodo | **dos fases** (propuesta ciega → refutación), una **señal medible** de saturación y copias aisladas | concilio (X196); graduador y F6 (X199) |
| FRACTAL-MAS | el agente como herramienta | la **uniformidad de la arista**: tool o hijo por el mismo despacho (MCP y A2A ya existen) | template (X194) |
| FractFlow | unidades agente–herramienta anidables | **una sola descripción** por módulo, la lee el de arriba | catálogo (X198) |

**Lo que nos diferencia**: el minimalismo. FRACTAL pone cinco componentes en
cada nodo; acá el nodo es el loop mínimo y todo lo demás es un módulo
opcional que se conecta.

**Antecedentes clásicos** de la misma idea, antes de los LLM: el patrón
Composite (un compuesto se usa igual que una pieza simple), los holones de
Koestler (cada parte es un todo y parte de algo mayor) y el Viable System
Model de Stafford Beer (cada nivel con la misma estructura). PocketFlow lo
resume en una línea: un Flow es un Node.

**Ya estaba en el repo**: *Understanding Agent Scaling … via Diversity* (2026,
en `docs/principios.md`) dice que dos agentes diversos igualan o superan a 16
iguales, y que por eso el 0/144 simétrico **no refuta** el fractal. La fuente
estaba; el roadmap post-X150 no la usó.

