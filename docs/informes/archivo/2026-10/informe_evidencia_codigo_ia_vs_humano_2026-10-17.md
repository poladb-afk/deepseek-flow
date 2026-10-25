# Evidencia: código que funciona vs código bien escrito, y programación IA vs humana

**Fecha:** 2026-10-17 · **Consulta de fuentes:** 2026-10-17 · **Alcance:** evidencia disponible a octubre de 2026.

**Método.** Búsqueda dirigida, apertura de cada fuente citada, contraste de metadatos contra OpenAlex y Crossref, y lectura de los PDF cuando estaban disponibles. No es una revisión sistemática: es una selección curada con tamaño muestral, tipo de estudio y límites declarados. Los resultados sobre herramientas de IA caducan en meses; los resultados sobre mecanismos (confianza, integración, contexto) caducan más lento.

**Regla de jerarquía aplicada.** RCT y peer-reviewed por encima de preprints; preprints con método claro por encima de observacionales grandes; observacionales por encima de informes de industria; encuestas al final. Los blogs de opinión no se usan como evidencia. Cuando una fuente no se pudo abrir, se dice y no se reproduce su cifra.

---

## 1. Resumen ejecutivo

1. **«Funciona» y «bien escrito» son dos ejes distintos, medidos con instrumentos distintos.** La corrección se testea; la calidad estructural se infiere de proxies (legibilidad, nombres, smells, cambios, defectos, deuda). Confundirlos es el error de método más común de esta literatura. *Confianza: alta (definicional); media-baja para cualquier claim causal.*
2. **Entender el código es la actividad dominante del trabajo profesional.** Estudio de campo con 78 desarrolladores, 7 proyectos y 3.148 horas: ~58% del tiempo se va en comprensión, y los seniors gastan proporcionalmente menos que los juniors (Xia et al., TSE 2017). *Confianza: alta para la medición; 7 proyectos y una instrumentación concreta limitan la generalización.*
3. **La dirección «escribir bien paga» es consistente; la magnitud no está medida.** Legibilidad, nombres y estructura correlacionan con menos cambios y menos defectos en tres muestras independientes (Buse & Weimer 2010; Butler et al. 2009/2010; Khomh et al. 2009). Todos son observacionales. *Confianza: alta en la dirección, baja en el tamaño del efecto.*
4. **No existe un RCT que compare «solo que funcione» contra «bien escrito» midiendo costo total.** El eslabón causal de la pregunta 1 no está experimentalmente establecido. *Confianza: alta en la ausencia.*
5. **Las métricas de calidad no capturan de forma fiable la mejora que el desarrollador percibe.** En commits donde el autor declara mejorar cohesión, acoplamiento, legibilidad o complejidad, las métricas del estado del arte fallan «más a menudo que no» (Pantiuchina et al., ICSME 2018). Y al controlar por tamaño, las métricas de complejidad pierden señal (Improta et al. 2026, preprint). *Confianza: media-alta.*
6. **En productividad con IA el signo depende del contexto, y el autorreporte es optimista por diseño.** +55,8% en una tarea verde de un archivo (Peng et al. 2023, autores de Microsoft/GitHub); ~21% en una tarea empresarial (Paradis et al. 2024, Google); **19% más lento** en issues reales de repos maduros, con participantes que tras sufrirlo creían haber sido 20% más rápidos (METR 2025). *Confianza: alta en que percepción ≠ medición; media en el signo agregado.*
7. **El código de IA es más simple, más repetitivo y con más hallazgos de seguridad, pero en repos reales la brecha se achica y la legibilidad puede ser comparable.** 500k+ muestras: más construcciones sin uso, más debugging hardcodeado y más vulnerabilidades de alto riesgo (ISSRE 2025). 787.562 pares: ~mitad de tamaño y ramas (Improta et al. 2026, preprint). Medición en repos reales: diferencias «más bien pequeñas» (Mao et al. 2026, preprint). Caso industrial Atlassian: legibilidad comparable a la humana (ICSME 2025). *Confianza: media, con evidencia que se contradice en magnitud.*
8. **La IA sube el throughput y también la inestabilidad, y la confianza del usuario no acompaña.** −1,5% de throughput y −7,2% de estabilidad por cada +25% de adopción (DORA 2024); en 2025 el throughput ya mejora y la inestabilidad persiste, con 30% de poca o ninguna confianza en el código generado (DORA 2025). En laboratorio, el asistente produjo código menos seguro y más confianza (Perry et al., CCS 2023). *Confianza: media; encuestas autorreportadas con patrocinio de Google.*

---

## 2. Pregunta 1: «código que funciona» vs «código bien escrito»

### 2.1 Definiciones operativas

| Término | Definición operativa | Cómo se mide en la literatura | Problema del instrumento |
|---|---|---|---|
| Corrección funcional | Satisface la especificación en las entradas probadas | Tests, pass@k, benchmarks | Mide lo probado, no el comportamiento en producción |
| Comprensión | Costo cognitivo de entender un cambio | Tiempo en tareas, datos HCI de campo, eye-tracking | Caro de medir; muestras chicas o instrumentación invasiva |
| Legibilidad | Facilidad de lectura de un fragmento | Juicios humanos agregados sobre snippets; métricas de features | Valida contra percepción, no contra mantenimiento |
| Calidad estructural | Acoplamiento, cohesión, complejidad, duplicación, tamaño | Métricas estáticas, detectores de smells | Confundida con tamaño (Improta et al. 2026) |
| Deuda técnica | Costo futuro de una solución subóptima | Metáfora (Cunningham 1992); proxies de smells y churn | No hay unidad de medida; se estima con herramientas |
| Defectos | Fallos observados | Bugs reportados, hallazgos estáticos, incidencias | Los estáticos sobrerrepresentan lo detectable |
| Costo | Costo de propiedad | Agregados nacionales (CISQ); economía de defectos | Agregaciones heterogéneas, no causales |

Dos advertencias de definición. Primera: «bien escrito» no es una propiedad única; los estudios miden fragmentos distintos (formato local, nombres, estructura de clases, tamaño de funciones) y generalizan entre sí sin justificación. Segunda: la corrección se mide casi siempre en tareas sintéticas donde el código se escribe una vez y nadie lo mantiene.

### 2.2 Tabla de hallazgos

| Hallazgo | Fuente | Tipo | Qué muestra | Límite |
|---|---|---|---|---|
| La comprensión domina el tiempo de trabajo | Xia et al., TSE 2017 | Estudio de campo: 78 desarrolladores, 7 proyectos, 3.148 h, datos HCI multi-aplicación | ~58% del tiempo en actividades de comprensión; seniors gastan menos proporción que juniors | Siete proyectos; el tiempo no es el costo; instrumentación propia |
| La legibilidad medida predice el juicio humano y correlaciona con calidad | Buse & Weimer, TSE 2010 | Observacional: 120 anotadores, 2,2 M LOC | Modelo de features locales con ~80% de efectividad contra juicios humanos; correlación fuerte con cambios, reportes de defectos y mensajes de log | Correlación, no causalidad; snippets chicos; confusión con tamaño y actividad del archivo |
| El modelo de legibilidad puede ser mucho más simple | Posnett et al., MSR 2011 | Reanálisis de los datos de Buse & Weimer | Tamaño + entropía (Halstead) explican los juicios con un modelo más simple y significativo | Mismo constructo subjetivo; no evalúa outcomes |
| Los nombres defectuosos se asocian a peor código, también a nivel de método | Butler et al., WCRE 2009 y CSMR 2010 | Observacional: 8 librerías Java, 12 guías; extensión a métodos con técnicas de test diagnóstico | Asociación significativa entre identificadores que violan guías y hallazgos de análisis estático; se mantiene al nivel de método | Análisis estático como criterio de calidad; confusión con estilo y madurez del proyecto |
| Las clases con code smells son más propensas al cambio | Khomh et al., WCRE 2009 | Observacional: 29 smells; 9 releases de Azureus y 13 de Eclipse | En casi todos los releases las clases con smells cambian más; algunos smells correlacionan mucho más que otros | Change-proneness no es costo ni defecto; dos sistemas; confusión con tamaño |
| Las métricas de calidad no capturan la mejora que el autor declara | Pantiuchina et al., ICSME 2018 | Minería de commits con intención declarada (cohesión, acoplamiento, legibilidad, complejidad) | «Más a menudo que no» las métricas del estado del arte no detectan la mejora declarada | La intención declarada no prueba mejora real; muestra autoetiquetada |
| La refactorización responde a métricas de proceso y producto | Pantiuchina et al., TOSEM 2020 | 287.813 refactorizaciones en 150 sistemas; 551 pull requests analizados a mano | Relación cuantitativa entre refactorizaciones y métricas; taxonomía de motivaciones | No mide retorno; sesgo a proyectos open source activos |
| Al controlar por tamaño, la complejidad pierde señal | Improta et al. 2026 (preprint) | 787.562 pares función-docstring en Python, Java y C | La naturalidad estadística separa autoría; las métricas de complejidad aportan poco una vez controlado el tamaño | Preprint; «naturalidad» es un constructo nuevo, no validado contra mantenimiento |
| El costo agregado de la mala calidad es enorme y la deuda es su mayor componente | CISQ 2022 (Krasner) | Informe de industria, EE.UU. | 2,41 billones USD de costo de mala calidad; ~1,52 billones de deuda técnica acumulada | Agrega ciberdelito y cadena de suministro; metodología no revisada; consorcio que certifica |
| La deuda y el envejecimiento son fenómenos de decisión | Cunningham 1992; Parnas 1994 | Reportes conceptuales | «Shipping first time code is like going into debt»; el deterioro viene de cambios que no mantienen la estructura | Sin datos; valen como marco |
| Prevenir defectos es más barato que corregirlos tarde | Boehm & Basili, Computer 2001 | Síntesis de datos cuantitativos previos | Relaciones y modelos que muestran costos desproporcionados de la detección tardía | Síntesis de estudios de los 70-90; no separa estilo de diseño |

### 2.3 Síntesis de la pregunta 1

**Lo que sostiene la evidencia.** Hay una asociación repetida y en la misma dirección: peor legibilidad y peor estructura acompañan más cambios, más hallazgos estáticos y más propensión a modificarse. Tres estudios con muestras independientes (2,2 M LOC; 8 proyectos Java; 2 sistemas con 22 releases) llegan a la misma conclusión. Además, la comprensión —lo que la legibilidad pretende abaratar— es la actividad que domina el tiempo profesional medido en campo (58%). Ese es el mejor argumento disponible: si la mayor parte del tiempo se va en entender, cualquier cosa que reduzca el costo de entender ataca el componente más grande.

**Lo que no sostiene.** No existe un experimento que asigne equipos a escribir «bien» o «solo que funcione» y compare costo total, defectos escapados y tiempo de mantenimiento. La literatura mide fragmentos, no proyectos, y usa defectos y cambios como proxy de costo sin separar el efecto del tamaño y la actividad del archivo.

**El hallazgo incómodo.** Pantiuchina et al. (2018) muestran que las métricas de calidad fallan sistemáticamente en capturar la mejora que el propio desarrollador declara, y Improta et al. (2026) muestran que, controlado el tamaño, las métricas de complejidad casi no distinguen autoría ni, por implicación, calidad. Eso no prueba que la calidad no importe: prueba que **la capa de medición con la que se decide «esto está bien escrito» es débil**. Toda política de calidad basada en umbrales de métricas hereda ese error.

**Detalle contraintuitivo y relevante para la sección 3.** Buse & Weimer reportan que, para los juicios locales de legibilidad, los comentarios importan menos que las líneas en blanco. El marcador «cantidad de comentarios», que suele usarse como señal de calidad y que el código generado por IA infla, no es un buen indicador de legibilidad percibida.

**Veredicto.** Escribir bien paga, con confianza alta en la dirección y baja en la magnitud. El respaldo es más fuerte para propiedades estructurales (tamaño, duplicación, acoplamiento) que para estilo cosmético, y más fuerte para «esto se va a cambiar mucho» que para «esto va a costar X».

---

## 3. Pregunta 2: forma de programar de la IA vs programación humana

### 3.1 Qué se mide (y con qué se confunde)

| Dimensión | Instrumento típico | Qué mide de verdad | Confusión frecuente |
|---|---|---|---|
| Productividad | Tiempo hasta completar tarea; tareas cerradas por unidad de tiempo | Velocidad en una tarea acotada | Se extrapola a throughput organizacional, que depende de revisión, integración y operación |
| Productividad percibida | Encuesta al desarrollador | Expectativa y satisfacción | Se reporta como medición; METR muestra que puede invertir el signo |
| Corrección | pass@k sobre HumanEval y MBPP | Corrección en problemas algorítmicos de un archivo | Se extrapola a repos con dependencias cruzadas |
| Seguridad | Escaneo de programas generados; juicio experto | Tasa de vulnerabilidades en escenarios inducidos | Se extrapola a código integrado y revisado |
| Mantenibilidad | Churn, duplicación, smells, deuda estimada | Proxies de esfuerzo futuro | Churn no distingue reescritura sana de retrabajo |
| Estilo e idiomas | Naturalidad estadística, similitud con convenciones del repo | Consistencia y «tipicidad» | Se interpreta como calidad cuando es solo diferencia |
| Contexto del repo | Benchmarks multi-archivo; medición en repos reales | Uso de contexto cruzado | Los benchmarks estándar son de un solo archivo |

### 3.2 Productividad: la evidencia está dividida

| Estudio | Diseño y muestra | Resultado | Límite |
|---|---|---|---|
| Peng et al. 2023 (arXiv 2302.06590) | RCT; desarrolladores reclutados; servidor HTTP en JavaScript | +55,8% de velocidad | Tarea verde, de un archivo, con especificación; autores de Microsoft Research, GitHub y MIT Sloan |
| Paradis et al. 2024 (arXiv 2410.12944) | RCT; 96 ingenieros de Google; tarea empresarial compleja | ~21% menos tiempo, con intervalo amplio; más beneficio en quien pasa más horas en código | Una tarea, tooling interno; los autores advierten contra extrapolar |
| METR 2025 | RCT; 16 desarrolladores expertos; 246 issues de repos grandes; ~2 h por tarea | 19% más tiempo con IA; esperaban 24% menos; tras el experimento creían haber sido 20% más rápidos | N chico; tiempo autoinformado; herramientas de principios de 2025 |
| METR 2026 (actualización) | Nuevo experimento desde agosto de 2025; 10 devs del original + 47 nuevos | Autores declaran datos no fiables por selección; subconjunto original −18% (IC −38% a +9%); nuevos −4% (IC −15% a +9%) | 30-50% de los devs no presentaban tareas que no quisieran hacer sin IA: el grupo de control se degrada |
| Cui et al. 2026 (Management Science) | Tres RCT de campo en Microsoft, Accenture y una Fortune 100 | 4.867 desarrolladores: +26,08% de tareas completadas (SE 10,3%); los menos experimentados ganan más | Texto completo inaccesible (403); cifras del abstract verificado vía OpenAlex |

**Lectura.** Los tres RCT no se contradicen: miden cosas distintas. Peng mide una tarea greenfield con el costo de integración en cero; Paradis, una tarea empresarial con tooling; METR, a la persona que conoce el repositorio mejor que el modelo, en issues que requieren contexto disperso. La variable que ordena los resultados no es el modelo sino **cuánto del trabajo consiste en integrar con código y conocimiento que ya existe**.

**El aporte más sólido de METR no es el 19%.** Es la brecha entre 24% esperado a favor, 19% medido en contra y 20% percibido a favor después de haberlo sufrido. Eso invalida las encuestas de productividad como medición, y la actualización de 2026 lo confirma por otra vía: la adopción misma destruye el grupo de control.

### 3.3 Calidad, seguridad y estilo

| Hallazgo | Fuente | Tipo | Qué muestra | Límite |
|---|---|---|---|---|
| ~40% del código generado es vulnerable en escenarios de riesgo | Pearce et al., IEEE S&P 2022 | 89 escenarios, 1.689 programas | Aproximadamente 40% vulnerables en escenarios derivados del Top 25 de CWE | Modelo de 2021; prompts sintéticos; sin revisor humano |
| El asistente vuelve al usuario menos seguro y más confiado | Perry et al., CCS 2023 | Estudio de usuario: 47 participantes, 6 tareas de seguridad | Código significativamente menos seguro y mayor creencia de haber escrito código seguro; más interacción con el prompt se asocia a menos vulnerabilidades | Laboratorio; modelo codex-davinci-002; tareas orientadas a seguridad |
| Los bugs del código de LLM tienen patrones identificables | Tambon et al., EMSE 2025 | 333 bugs de 3 LLM; taxonomía validada con 34 practicantes | 10 patrones: interpretación errónea del pedido, caso borde faltante, error tonto, objeto alucinado, generación incompleta, entre otros | Muestra de benchmarks y generadores concretos; no da frecuencias en repos reales |
| La corrección en benchmarks sube, pero es corrección de benchmark | Yetiştiren et al. 2023 (arXiv 2304.10778) | HumanEval; Copilot, CodeWhisperer, ChatGPT | Correcto 65,2%, 46,3% y 31,1%; deuda estimada 8,9, 9,1 y 5,6 minutos | Tareas algorítmicas de un archivo; «deuda» es estimación de herramienta |
| El código IA es más simple y repetitivo, con más construcción muerta y más vulnerabilidades de alto riesgo | ISSRE 2025 | 500k+ muestras, Python y Java; ChatGPT, DeepSeek-Coder, Qwen-Coder; ODC y CWE | IA: más construcciones sin uso, debugging hardcodeado, más vulnerabilidades de alto riesgo; humano: más complejidad estructural y más problemas de mantenibilidad | Clasificación estática; modelos de 2024-2025; dos lenguajes |
| El código IA es estructuralmente comprimido y estilísticamente «plantilla» | Improta et al. 2026 (preprint) | 787.562 pares función-docstring; Python, Java, C | ~mitad de tamaño y ramas que el humano; se agrupa aparte en estilo; seguridad depende del lenguaje; en C, menos fallos graves de memoria que el humano | Preprint; emparejamiento por docstring, no por tarea de mantenimiento |
| En repos reales las diferencias de métricas son pequeñas | Mao et al. 2026 (preprint) | Medición a gran escala en repositorios reales; métricas de código y de commit | Contradice la magnitud de laboratorio: las diferencias código-level son «más bien pequeñas»; aporta duplicación, tamaño de commit y estabilidad | Preprint; atribución de autoría por heurísticas |
| La legibilidad del código IA puede ser comparable a la humana | Atlassian, ICSME 2025 | Encuesta a practicantes + comparación del framework HULA contra código humano en escenarios reales | La legibilidad sigue siendo crítica; la del código generado resultó comparable | Un solo caso industrial; herramienta propia |
| Los generadores comerciales clonan código | Wu et al., PACMSE 2025 | Estudio empírico de 3 generadores; todos los tipos de clon | Clones Tipo-1 y Tipo-2 de hasta 7,50%; riesgo de propagar bugs y vulnerabilidades e infringir copyright | Especificaciones sintéticas; no mide clones integrados |
| En repos reales sube el clonado y baja la refactorización | GitClear 2024 y 2025 | ~153 M líneas modificadas (2020-2023); 211 M (2020-2024) | Clones de 8,3% a 12,3%; líneas refactorizadas de 25% a menos de 10%; 4× más clonado; copy/paste supera a código movido | Proveedor de la métrica que reporta; base de clientes sesgada; sin pares |
| La IA sube el throughput y también la inestabilidad | DORA 2024 y 2025 | Encuestas anuales; decenas de miles de respondedores | 2024: −1,5% de throughput y −7,2% de estabilidad por cada +25% de adopción. 2025: 90% usa IA, más de 80% cree que mejoró su productividad, el throughput ya mejora y la inestabilidad persiste; 30% con poca o ninguna confianza en el código generado | Autorreporte, corte transversal; programa de Google Cloud con GitHub y GitLab como partners |
| Los benchmarks estándar no representan el trabajo en repos | CrossCodeEval, NeurIPS 2023 | Benchmark multilingüe sobre repos reales | HumanEval y MBPP son de un archivo; el completado real exige contexto de otros archivos | Mide completado, no mantenibilidad |
| En repos reales, la proporción detectable de código IA baja y se concentra en tests | Ji et al., JSS 2026 | Minería 2021-2025 de repos de empresa y comunidad | Código detectado como generado por LLM decrece en el tiempo y se concentra en tests; grandes empresas reportan 20-30% de su código generado por LLM | La detección es heurística, no verdad de terreno |
| La deuda inducida por GenAI queda escrita en los comentarios | arXiv 2601.07786 (2026, preprint) | 6.540 comentarios que referencian LLM en repos Python y JS (nov-2022 a jul-2025) | 81 comentarios que además auto-admiten deuda: testeo postergado, adaptación incompleta, comprensión limitada | Preprint; muestra chica; solo deuda declarada |
| El uso es masivo; la confianza no | Stack Overflow Survey 2025 | Encuesta; ~49.000 respuestas | 84% usa o planea usar IA (76% el año previo); 51% de los profesionales la usa a diario | Muestra autoseleccionada; contexto, no prueba de efecto |

### 3.4 Síntesis de la pregunta 2

**Productividad.** Tres RCT de buena calidad, tres respuestas, y la que ordena es el contexto de integración, no el modelo. El resultado más accionable es el de METR: la brecha percepción-medición es de casi 40 puntos porcentuales en el mismo experimento.

**Seguridad.** Dos mecanismos distintos. Pearce mide la propensión del modelo a producir código inseguro cuando se lo induce. Perry mide lo que pasa cuando hay un humano decidiendo: menos seguridad efectiva y más confianza subjetiva. El segundo resultado es el que importa para ingeniería, porque sobrevive a la mejora del modelo: el problema no es solo la tasa de vulnerabilidades, es la caída del escrutinio.

**Estilo: hay firma, pero no la caricatura.** Convergen tres observaciones: el código IA es más chico, más repetitivo y menos «natural» estadísticamente; tiene un perfil de defectos distinto (más construcción muerta y boilerplate, menos problemas de mantenibilidad de codebase madura); y en seguridad depende del lenguaje. Pero dos mediciones recientes matizan la magnitud: en repos reales las diferencias son pequeñas (Mao et al. 2026) y la legibilidad puede ser comparable a la humana en un caso industrial (Atlassian 2025). La afirmación «el código IA es ilegible» no está sostenida; la afirmación «el código IA tiene una firma estilística propia y más repetición» sí.

**Mantenibilidad.** Clones, churn y caída de refactorización convergen, y una parte es peer-reviewed (Wu et al. 2025). Pero el agregado ecológico más citado es de un proveedor que vende la métrica que reporta. La convergencia es sugestiva; la cadena causal no está establecida.

**Consistencia con el repo e idiomas.** Sigue siendo el hueco más grande. CrossCodeEval documenta que el completado real exige contexto cruzado que los benchmarks no evalúan; no encontré un instrumento validado que mida adopción de convenciones del repositorio ni idiomatismo por lenguaje. Las afirmaciones fuertes sobre «no respeta el estilo del repo» son, hoy, impresión profesional con respaldo indirecto.

---

## 4. Cruces: ¿el código IA funciona pero se lee y se mantiene peor?

### 4.1 Evidencia a favor

- **Clonado y churn suben mientras la refactorización baja** (GitClear 2024/2025): el patrón esperable si el código se agrega más rápido de lo que se integra. Límite: proveedor, métrica propietaria.
- **Clones medidos en generadores comerciales** (Wu et al. 2025, peer-reviewed): hasta 7,5% de clones Tipo-1/2, con propagación de bugs y vulnerabilidades.
- **Perfil de defectos distinto** (ISSRE 2025): más construcciones sin uso y más debugging hardcodeado, que es deuda de integración más que de algoritmo.
- **Caída de estabilidad de entrega con más adopción** (DORA 2024): consistente con cambios peor integrados, no solo con más cambios. DORA 2025 mantiene la inestabilidad aunque el throughput mejore.
- **Más confianza con menos seguridad** (Perry et al. 2023): el mecanismo humano que compensa la mala calidad —revisar con escepticismo— se debilita justo cuando más falta hace.
- **Freno en repos maduros** (METR 2025): si el costo estuviera solo en la escritura, la IA no podría frenar a un experto en su propio repositorio. El tiempo se va en entender, verificar e integrar, que es la definición operativa de mala mantenibilidad.

### 4.2 Evidencia en contra o que matiza

- **La legibilidad medida puede ser comparable a la humana** (Atlassian, ICSME 2025): el cruce «se lee peor» no se sostiene como afirmación general; en ese caso industrial no se verificó.
- **En repos reales las diferencias de métricas son pequeñas** (Mao et al. 2026): la brecha de laboratorio no se replica con la misma magnitud en código de producción.
- **La corrección en benchmarks mejora y la deuda estimada es de minutos** (Yetiştiren et al. 2023): si el código fuera estructuralmente inservible, esos números no se sostendrían.
- **Los bugs típicos son superficiales** (Tambon et al. 2025): interpretación errónea del pedido, casos borde, errores tontos. Son fallos de especificación y verificación, no de arquitectura; se detectan con tests y revisión.
- **Complejidad y tamaño explican buena parte de la diferencia** (Improta et al. 2026): al controlar por tamaño, las métricas de complejidad pierden señal. Mucha de la «peor calidad» medida es «código más chico medido con la misma vara».

### 4.3 Lectura de los cruces

El cruce más defendible no es «el código IA es ilegible». Es: **el código IA se produce a un ritmo que el sistema de revisión, integración y refactorización no acompaña**. Los indicadores que lo sostienen no son de legibilidad sino de flujo: churn, clones, inestabilidad, tiempo de un experto en su propio repo. La legibilidad del código generado, medida con instrumentos válidos, dio comparable en el único caso industrial verificado; la firma estilística y la repetición sí están documentadas.

---

## 5. Lo que la evidencia NO muestra

- **No hay RCTs sobre calidad de código ni sobre mantenibilidad.** Los RCT existen para productividad en tareas y para seguridad en laboratorio. Para «¿paga escribir bien?» y para «¿el código IA se mantiene peor?» no hay asignación aleatoria. Es la limitación estructural del campo, no un descuido de esta revisión.
- **Tareas sintéticas contra repos reales.** HumanEval y MBPP son problemas de un archivo sin dependencias, sin revisión y sin vida útil. CrossCodeEval documenta que el trabajo real exige contexto de otros archivos. Mao et al. (2026) muestran que las diferencias medidas en laboratorio no se replican con la misma magnitud en repos reales: la validez externa de los benchmarks es baja y ya está cuantificada.
- **Autorreporte contra medición.** METR cuantifica la brecha: 24% esperado a favor, 19% medido en contra, 20% percibido a favor después. Las encuestas de productividad miden percepción.
- **Conflictos de interés declarados.** Peng et al.: autores de Microsoft Research, GitHub y MIT Sloan evaluando un producto de GitHub. GitClear: vende analítica de calidad. CISQ: consorcio que certifica. DORA: programa de Google Cloud con GitHub y GitLab como research partners. Atlassian: evalúa su propia herramienta. Ninguno invalida los datos; todos exigen leer el resultado con el diseño en mente.
- **Preprints sin revisión.** METR (blog), Paradis et al., Yetiştiren et al., Improta et al., Mao et al., el estudio de deuda auto-admitida. Algunos son de 2026 y todavía están en revisión; sus cifras deben tratarse como provisionales.
- **Los instrumentos de calidad tienen validez cuestionada.** La legibilidad se valida contra juicios sobre snippets; las métricas de calidad estructural fallan en capturar la mejora percibida (Pantiuchina et al. 2018) y pierden señal al controlar tamaño (Improta et al. 2026). Medir «bien escrito» con umbrales es, en el mejor caso, un proxy ruidoso.
- **La atribución de autoría es heurística.** Los estudios en repos reales infieren qué escribió una IA por commits, comentarios o detectores. Ji et al. (2026) muestran que esa proporción detectable cae con el tiempo y se concentra en tests; el ruido de atribución contamina cualquier comparación a gran escala.
- **Casi todo es de 2021-2026 y los modelos cambian más rápido que los estudios.** Pearce evaluó un modelo de 2021; Perry, codex-davinci-002; METR declaró su propio resultado desactualizado un año después. Las conclusiones sobre mecanismos envejecen más lento que las conclusiones sobre productos.
- **Sesgo de escenario.** Los estudios de seguridad usan tareas inducidas hacia el fallo; los de productividad, tareas donde el éxito es observable. Ambos extremos están representados, pero la mezcla no es una muestra del trabajo real.

---

## 6. Implicancias prácticas

- **Medir en el repositorio propio, no en benchmarks.** Los indicadores con mejor relación señal/ruido son churn a dos semanas, duplicación, tiempo hasta revisión, defectos escapados y estabilidad de entrega. pass@k no informa sobre el costo de mantener lo generado.
- **Tratar la revisión como el cuello de botella que es.** Si el código se produce más rápido de lo que se puede revisar, el sistema no gana velocidad: gana inventario. Presupuestar revisión y pruebas como parte del costo de la herramienta, no como externalidad.
- **Hacer ejecutables las convenciones.** Dado que las métricas de calidad no capturan la mejora percibida y que el estilo del código generado no está medido con instrumentos validados, conviene que las reglas vivan en linters, formateadores, tipos y tests que fallan, no en instrucciones de prompt ni en revisiones humanas cansadas. Lo que no falla, no se cumple.
- **No aceptar «funciona» como criterio de merge para código generado.** Los patrones documentados —caso borde faltante, interpretación errónea del pedido, menos escrutinio— se detectan con tests de casos borde y revisión dirigida, exactamente lo que se saltea cuando hay confianza.
- **Instrumentar seguridad en el ciclo, no después.** La combinación de ~40% de vulnerabilidad inducida, más hallazgos de alto riesgo en Python y Java, y más confianza del usuario hace que la revisión humana sola no alcance: SAST, threat model y pruebas de seguridad en el pipeline son la compensación razonable.
- **Desconfiar del retorno declarado, de la IA y del refactor.** Los dos autorreportes están sesgados en la misma dirección: se sobreestima la velocidad que la IA da y la mejora que una refactorización produce. Decidir con medición local en ambos casos.

---

## 7. Referencias

Consultadas el 2026-10-17. Se indica tipo de estudio y N cuando la fuente lo declara. Cuando no se pudo acceder al texto completo, se dice.

**Fundamentos de calidad y costo**

1. [The WyCash Portfolio Management System](http://c2.com/doc/oopsla92.html) — Ward Cunningham, 1992, OOPSLA '92 Experience Report. Origen de la metáfora de deuda técnica. Reporte de experiencia, sin N.
2. [Software Aging](https://doi.org/10.5555/257734.257788) — David Lorge Parnas, 1994, ICSE. Conceptual. Metadatos verificados vía OpenAlex; texto no abierto.
3. [Software Defect Reduction Top 10 List](https://doi.org/10.1109/2.962984) — Barry Boehm y Victor Basili, 2001, Computer 34(1). Síntesis de datos cuantitativos previos.
4. [CISQ Publishes the Cost of Poor Software Quality in the US: A 2022 Report](https://www.it-cisq.org/press-releases/12-06-22/) — Herb Krasner / CISQ, 2022. Informe de industria: 2,41 billones USD de costo total y ~1,52 billones de deuda técnica. Sin revisión por pares.

**Comprensión, legibilidad y estructura**

5. [Measuring Program Comprehension: A Large-Scale Field Study with Professionals](https://doi.org/10.1109/TSE.2017.2734091) — Xin Xia, Lingfeng Bao, David Lo, Zhenchang Xing, Ahmed E. Hassan y Shanping Li, 2017, IEEE TSE. Estudio de campo: 78 desarrolladores, 7 proyectos, 3.148 horas; ~58% del tiempo en comprensión.
6. [Learning a Metric for Code Readability](https://doi.org/10.1109/TSE.2009.70) — Raymond Buse y Westley Weimer, 2010, IEEE TSE 36(4). Observacional: 120 anotadores, 2,2 M LOC.
7. [A Simpler Model of Software Readability](https://doi.org/10.1145/1985441.1985454) — Daryl Posnett, Abram Hindle y Prem Devanbu, 2011, MSR. Reanálisis de los datos de Buse & Weimer.
8. [Relating Identifier Naming Flaws and Code Quality: An Empirical Study](https://doi.org/10.1109/WCRE.2009.50) — Simon Butler, Michel Wermelinger, Yijun Yu y Helen Sharp, 2009, WCRE. Observacional: 8 librerías Java, 12 guías.
9. [Exploring the Influence of Identifier Names on Code Quality: An Empirical Study](https://doi.org/10.1109/CSMR.2010.27) — los mismos autores, 2010, CSMR. Extiende el resultado a nivel de método con técnicas de test diagnóstico.
10. [An Exploratory Study of the Impact of Code Smells on Software Change-proneness](https://doi.org/10.1109/WCRE.2009.28) — Foutse Khomh, Massimiliano Di Penta y Yann-Gaël Guéhéneuc, 2009, WCRE. Observacional: 29 smells, 9 releases de Azureus y 13 de Eclipse.

**Refactorización y percepción de calidad**

11. [Improving Code: The (Mis)Perception of Quality Metrics](https://doi.org/10.1109/ICSME.2018.00017) — Jevgenija Pantiuchina y coautores, 2018, ICSME. Minería de commits con intención declarada de mejora.
12. [Why Developers Refactor Source Code](https://doi.org/10.1145/3408302) — Jevgenija Pantiuchina y coautores, 2020, ACM TOSEM. 287.813 refactorizaciones en 150 sistemas; 551 pull requests analizados.

**Productividad con asistentes de IA**

13. [The Impact of AI on Developer Productivity: Evidence from GitHub Copilot](https://arxiv.org/abs/2302.06590) — Sida Peng, Eirini Kalliamvakou, Peter Cihon y Mert Demirer, 2023, arXiv (Microsoft Research, GitHub, MIT Sloan). RCT: +55,8%.
14. [Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) — Joel Becker, Nate Rush, Beth Barnes y David Rein, METR, 2025. RCT: 16 desarrolladores, 246 issues, 19% más lento. Sin revisión por pares.
15. [We are Changing our Developer Productivity Experiment Design](https://metr.org/blog/2026-02-24-uplift-update/) — METR, 2026. Actualización: −18% y −4% con sesgo de selección declarado; los autores consideran el dato poco fiable.
16. [How much does AI impact development speed? An enterprise-based randomized controlled trial](https://arxiv.org/abs/2410.12944) — Elise Paradis y coautores, 2024, arXiv (Google). RCT: 96 ingenieros, ~21% menos tiempo.
17. [The Effects of Generative AI on High-Skilled Work: Evidence from Three Field Experiments with Software Developers](https://doi.org/10.1287/mnsc.2025.00535) — Zheyuan Cui, Mert Demirer, Sonia Jaffe, Leon Musolff, Sida Peng y Tobias Salz, 2026, Management Science (online 2025). Tres RCT de campo; 4.867 desarrolladores; +26,08% de tareas completadas (SE 10,3%). Texto completo inaccesible (403); abstract verificado vía OpenAlex.

**Seguridad**

18. [Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions](https://arxiv.org/abs/2108.09293) — Hammond Pearce, Baleegh Ahmad, Benjamin Tan, Brendan Dolan-Gavitt y Ramesh Karri, 2022, IEEE S&P. 89 escenarios, 1.689 programas, ~40% vulnerables.
19. [Do Users Write More Insecure Code with AI Assistants?](https://arxiv.org/abs/2211.03622) — Neil Perry, Megha Srivastava, Deepak Kumar y Dan Boneh, 2023, ACM CCS. Estudio de usuario: 47 participantes, 6 tareas de seguridad.

**Calidad, bugs, duplicación y estilo del código generado**

20. [Evaluating the Code Quality of AI-Assisted Code Generation Tools](https://arxiv.org/abs/2304.10778) — Burak Yetiştiren, Işık Özsoy, Miray Ayerdem y Eray Tüzün, 2023, arXiv v2. HumanEval; corrección 65,2%, 46,3% y 31,1%; deuda estimada 8,9, 9,1 y 5,6 minutos.
21. [Bugs in Large Language Models Generated Code: An Empirical Study](https://arxiv.org/abs/2403.08937) — Florian Tambon y coautores, 2025, EMSE. 333 bugs de 3 LLM; 10 patrones validados con 34 practicantes.
22. [Human-Written vs. AI-Generated Code: A Large-Scale Study of Defects, Vulnerabilities, and Complexity](https://doi.org/10.1109/ISSRE66568.2025.00035) — 2025, ISSRE. 500k+ muestras, Python y Java, 3 LLM; ODC y CWE.
23. [What is the Difference Between Me and You? Benchmarking the Quality Gap Between Human-Written and AI-Generated Code](https://arxiv.org/abs/2609.12708) — Improta et al., 2026, arXiv. 787.562 pares en Python, Java y C. Preprint.
24. [A Large-Scale Comprehensive Measurement of AI-Generated Code in Real-World Repositories](https://arxiv.org/abs/2603.27130) — Mao et al., 2026, arXiv. Medición en repos reales. Preprint.
25. [An Empirical Study of Code Clones from Commercial AI Code Generators](https://doi.org/10.1145/3729397) — Weibin Wu y coautores, 2025, PACMSE. Clones Tipo-1/2 de hasta 7,50%.
26. [An exploratory study on LLM-generated code and comments in code repositories](https://doi.org/10.1016/j.jss.2026.113026) — Yongyi Ji y coautores, 2026, JSS. Minería 2021-2025.
27. [«TODO: Fix the Mess Gemini Created»: Towards Understanding GenAI-Induced Self-Admitted Technical Debt](https://arxiv.org/abs/2601.07786) — 2026, arXiv. 6.540 comentarios, 81 con deuda auto-admitida. Preprint.

**Legibilidad del código generado en la industria**

28. [Code Readability in the Age of Large Language Models: An Industrial Case Study from Atlassian](https://doi.org/10.1109/ICSME64153.2025.00073) — 2025, ICSME. Encuesta + comparación de HULA contra código humano; legibilidad comparable.

**Benchmarks y contexto de repositorio**

29. [CrossCodeEval: A Diverse and Multilingual Benchmark for Cross-File Code Completion](https://arxiv.org/abs/2310.11248) — Yangruibo Ding y coautores, 2023, NeurIPS. Cuatro lenguajes, repos reales; documenta la brecha de contexto cruzado.

**Industria y encuestas (contexto, no prueba)**

30. [Coding on Copilot: 2023 Data Suggests Downward Pressure on Code Quality](https://www.gitclear.com/coding_on_copilot_data_shows_ais_downward_pressure_on_code_quality) y [AI Copilot Code Quality: 2025 Look Back](https://www.gitclear.com/ai_assistant_code_quality_2025_research) — GitClear, 2024 y 2025. ~153 M y 211 M líneas; clones de 8,3% a 12,3%, refactorización de 25% a menos de 10%. Proveedor de la métrica que reporta.
31. [2024 DORA Report](https://dora.dev/research/2024/dora-report/) y [PDF](https://services.google.com/fh/files/misc/2024_final_dora_report.pdf) — Google Cloud / DORA, 2024. −1,5% de throughput y −7,2% de estabilidad por cada +25% de adopción. La página pública no lista las cifras; se citan del informe y de la cobertura de prensa.
32. [2025 State of AI-assisted Software Development](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf) — Google Cloud / DORA, 2025. 90% de uso; 30% con poca o ninguna confianza; la IA como amplificador.
33. [2025 Stack Overflow Developer Survey — AI](https://survey.stackoverflow.co/2025/ai) — Stack Overflow, 2025. ~49.000 respuestas; 84% usa o planea usar IA; 51% de los profesionales a diario.

---

### Nota sobre fuentes no verificadas

La fuente de arranque «Pantiuchina et al., Clean Code, ICSE/EMSE 2020» no se pudo verificar con ese título ni en OpenAlex ni en Crossref para esa autora. Lo que sí existe y se cita aquí es su trabajo sobre percepción de métricas de calidad (ICSME 2018) y su estudio a gran escala sobre motivaciones de refactorización (TOSEM 2020). No se incluyó ninguna afirmación atribuida a un paper «Clean Code» de 2020 porque no se pudo confirmar su existencia.

Del mismo modo, la cifra de «~50% del tiempo en comprensión» que circula en la literatura quedó reemplazada por la medición de campo de Xia et al. (2017), que es primaria, reciente y da ~58%.
