# Spec de ejecución — exp/85: TWINS del patrón de extracción dependiente del fraseo

**Estado:** ejecutada el 2026-10-22; C1-C4 OK, **0 gemelos** - resultado en bitacora exp/85.
**Instrumento:** sonda determinista + lectura del código (`PENDING` declarado por el agente en exp/84).

## Contexto

El fix de exp/84 cerró el patrón en `fable_judge` (clasificación LLM de hechos verificables donde
el código podía marcar candidatas). El método exige el paso final: buscar el MISMO patrón en el
resto del harness antes de declarar el trabajo completo.

## El patrón (definición operativa, congelada)

Un sitio LLM es **gemelo** si cumple las TRES:
1. consume prosa EXTERNA (un reporte/claim de otro, no material autogenerado ni estructurado), Y
2. clasifica/extrae HECHOS VERIFICABLES (cosas que el disco o una ejecución pueden confirmar), Y
3. el código NO junta esos hechos ni marca candidatas delante del modelo.

Categorías NO-gemelo (mutuamente excluyentes con la definición):
- **a) generación**: el modelo produce prosa/argumentos/descripciones (nadie verifica un estilo);
- **b) contrato de salida**: la salida es structured output validado con reparación (el modo de
  falla es output inválido con retry, no clasificación silenciosa);
- **c) entrada estructurada o propia**: consume resultados registrados por el propio flujo;
- **d) hechos del código delante**: el código ya junta/marca los hechos (citas leídas, inventario
  de tools, resultados fetched, reglas deterministas previas, diff/fuentes/candidatas);
- **e) ejecutor con tools**: el loop de agente (tiene action space, no clasifica prosa).

## Diseño (pre-registrado)

1. Sonda `banco/probes/twins_extractores.py`: escanea los sitios LLM del producto (líneas con
   `call_llm(`, `call_llm_agent(` o `extraer_yaml(` en .py del harness, sin tests/banco/salidas)
   y los cruza contra un registro de clasificación por archivo. **Falla si aparece un sitio sin
   clasificar** — el candado queda: un extractor nuevo se clasifica a consciencia o la sonda
   avisa (mismo espíritu que test_docs_sin_deriva para los docs).
2. Corrida + lectura del código de cada sitio dudoso.
3. Test del candado (sin red, sin LLM).

## Criterios (congelados)

- **C1:** la sonda corre y todo sitio del producto está clasificado (el registro se congela con
  lo que haya; lo que importa es el candado hacia adelante).
- **C2:** para cada sitio clasificado d/e, la lectura del código confirma la categoría (hechos
  del código o reglas deterministas delante del modelo) — si alguno NO la confirma, es GEMELO y
  se abre exp de fix.
- **C3 (el TWINS):** hallazgo = "encontré N sitios: <lista>". Si N=0 → el patrón queda declarado
  específico del juicio de reportes de trabajo externos, resultado negativo documentado (como
  X36); si N>0 → fix en exp aparte.
- **C4:** gate verde.

## Fuera de alcance

Cambios de código de producto (salvo que C2 encuentre un gemelo), F2, medir conducta del chat.


## Resultado (2026-10-22)

24 sitios LLM en 11 archivos, todos clasificados (a/b/c/d/e): **0 gemelos**.
El patron era especifico del juicio de reportes de trabajo externos. La
sonda queda como candado (un sitio sin clasificar rompe el gate); el escaneo
es por AST y tambien ve las llamadas directas a la API (vision.py). El
ratchet cazo test slop en los tests nuevos de la sonda y se corrigio
parametrizando (X20).
