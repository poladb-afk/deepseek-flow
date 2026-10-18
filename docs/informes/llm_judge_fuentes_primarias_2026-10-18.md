# LLM-as-a-judge: fuentes primarias verificadas (2026-10-18)

**Método:** el harness (`python3 main.py research`) produjo un borrador de 7,8 KB
sobre sesgos y confiabilidad de LLM-as-a-judge (`salidas/auditoria_2026-10/live21/research.md`).
Después verifiqué cada fuente primaria con `web_fetch` (HTTP 200 + título) y separé
lo confirmado de lo que solo aparece en blogs/agregadores.

## Fuentes primarias verificadas

| arXiv | Título verificado | Qué aporta (según abstract) |
|---|---|---|
| [2306.05685](https://arxiv.org/abs/2306.05685) | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | Jueces LLM como alternativa a evaluación humana; introduce MT-Bench/Arena y discute límites (posición, verbosidad, auto-mejora). |
| [2406.07791](https://arxiv.org/abs/2406.07791) | Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge | Sesgo de posición como amenaza a la fiabilidad; métricas y estudio sistemático/mitigación. |
| [2410.21819](https://arxiv.org/abs/2410.21819) | Self-Preference Bias in LLM-as-a-Judge | Cuantifica la autopreferencia de los evaluadores LLM. |
| [2410.12784](https://arxiv.org/abs/2410.12784) | JudgeBench: A Benchmark for Evaluating LLM-based Judges | Benchmark para evaluar a los propios jueces; la fiabilidad del juez rara vez se audita. |
| [2604.23178](https://arxiv.org/abs/2604.23178) | Judging the Judges: A Systematic Evaluation of Bias Mitigation Strategies in LLM-as-a-Judge Pipelines | Compara estrategias de mitigación de sesgos en pipelines de jueces. |
| [2411.15594](https://arxiv.org/abs/2411.15594) | A Survey on LLM-as-a-Judge | Survey del área: métodos, retos y confiabilidad. |
| [2403.13787](https://arxiv.org/abs/2403.13787) | RewardBench: Evaluating Reward Models for Language Modeling | Benchmark de reward models (evaluación automática de preferencias). |
| [2405.01535](https://arxiv.org/abs/2405.01535) | Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models | Juez open-source especializado en evaluar otros modelos. |

## Confirmado vs no verificado

**Confirmado (verificación directa):** los 8 títulos existen y coinciden con la
atribución del informe; los temas centrales (sesgo de posición, autopreferencia,
benchmarks de jueces, mitigación, survey, reward models, Prometheus 2) están
respaldados por abstracts primarios.

**No verificado (secundario o numérico):** el "κ ≈ 0,48 para 85% de acuerdo", los
"3.000 votos de expertos / 30.000 conversaciones" de MT-Bench, la afirmación de
que FastChat "no mantiene leaderboard" y las cifras de blogs/agregadores. Son
plausibles, pero no los tomo como evidencia sin leer el paper completo o la
tabla oficial.

## Lectura práctica para el harness

- **Sesgo de posición:** cualquier juez binario/A-B debe correr con posiciones
  intercambiadas y comparar consistencia; no confiar en una sola pasada.
- **Autopreferencia:** no usar el mismo modelo como generador y juez sin control
  (o medir el sesgo explícitamente).
- **JudgeBench/Juices:** la confiabilidad del juez es un objeto medible; conviene
  meta-evaluar antes de usar el juez como gate.
- **RewardBench/Prometheus:** alternativas open-source si se necesita juez local.

## Conclusión de la tarea

El harness **sirve para producir el borrador con estructura y fuentes**, pero la
calidad final depende de que el operador (yo) fuerce fuentes primarias y verifique
URLs: el mismo informe mezclaba papers con blogs. Para investigación seria:
pedir explícitamente "solo arxiv/ACL/NeurIPS/repos oficiales", y verificar cada
fuente antes de citarla.
