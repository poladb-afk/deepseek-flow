# Patch S0-CITAS-EJECUCION

**Patch de código sobre el ZIP autorizado: citas limitadas a fuentes autorizadas
y pytest sin permiso automático.** No implementa el harness completo ni fusiona
las Entregas 01/02 o una variante posterior del auditor.

INTENT: el fallback de citas busca sin delimitar previamente el alcance y pytest recibe permiso automático; el patch exige búsqueda autorizada y aprobación antes de ejecutar tests; el fundamento v1.1 §5.2, §5.3 y §7 requiere controlar capacidades efectivas y no confundir planificación con ejecución.

## Cambios de raíz

- `utils/citas.py`: autoriza cada base fuente antes de recorrerla y cada candidato
  antes de aceptarlo. Los archivos externos no participan en la unicidad ni cambian
  la respuesta abreviada según existan o no. Conserva el retorno de tres valores y
  evita la tupla expandida de la Entrega 01.
- `utils/politica_comandos.json`: retira `nivel: auto` de pytest y python3 -m pytest.
  Reutiliza el default preguntar. Revoca A45 explícitamente y no depende de recordar
  HITL_AUTO=0. Los scopes deben cubrir el comando y conservan sus restricciones.

No se agrega helper de producción, dependencia, setting, prompt o framework.
`utils/policy.py` solo actualiza documentación: su AST ejecutable no cambia.
No se migra ni reorganiza el proyecto. Las notas en diseño/estado/bitácora y el
spec registran la revocación sin borrar su historia ni instalar otro rector.

## Observado antes/después

| Prueba focal | Original | Candidato |
|---|---|---|
| Cita abreviada externa y alias | Lee contenido sintético externo | No lee |
| Archivo externo presente/ausente | Cambia la respuesta | Misma respuesta |
| Recorrido de bases fuera del alcance | Se intenta | No se recorre |
| Lectura/fallback autorizados | Funcionan | Conservados |
| Ambigüedad entre candidatos | No elige | Conservada |
| Pytest con aprobador que rechaza | No consulta; ejecuta y escribe la marca | Un pedido; ninguna ejecución ni marca |
| Pytest con aprobador que acepta | Ejecución permitida | Un pedido; ejecución y marca observadas |

Se usaron funciones originales y archivos sintéticos reales. Los casos de
fallback/ambigüedad tienen candidatos controlados; la aprobación y telemetría
son controladas. El subprocess solo ejecuta un test del instrumento, sin
conftest/plugins del proyecto ni credenciales. No es el recorrido completo del chat.

Además:

- **167 casos puros** de funciones de tests ejecutados directamente: sin fallos.
- **927 filas** de dos corpus históricos completos: **118 cambios de nivel**, todos
  auto→preguntar. También se registra cada cambio de explicación (incluso donde ya
  se pedía permiso). Ningún nivel se relaja ni se omiten filas.
- Dos funciones de tests de fotos ejecutadas contra sus fixtures controlados y
  seis casos del control real de scopes: satisfactorios.
- **267 archivos Python** compilan en memoria; no certifica tipos/imports.
- Patch reaplicado exactamente a la base en memoria; ZIP, CRC y metadatos contrastados.

## Tests y evidencia histórica

Se conservan todas las funciones, comandos y grupos parametrizados anteriores.
Se cambian las expectativas que exigían auto para pytest, por el contrato nuevo.
La única modificación dentro de un decorator cambia auto→preguntar en un caso;
sus IDs explícitos y comandos se mantienen. No se quitan aserciones para ocultar
la nueva fricción ni se ajustan comprobaciones no relacionadas.

Las fotos JSONL históricas no se tocan. Un fixture de delta exacto por hash de
comando conserva antes/después. El test compara todas las filas, comprueba el
estado anterior y ausencia de deltas huérfanos; acepta solamente auto→preguntar o
actualización de explicación con nivel preguntar ya existente. No ignora pytest
por keywords ni usa tolerancias amplias.

Se añaden **8 funciones de regresión** con casos de scopes, rechazo/aprobación,
enlaces, subcarpetas, existencia y ambigüedad. Las que necesitan fixtures completos
de pytest/checkout siguen pendientes; haberlas escrito no cuenta como ejecutarlas.

## Alcance

Modificados (12):
- README.md
- docs/bitacora.md
- docs/design.md
- docs/estado.md
- tests/test_auditoria_2026_10_26.py
- tests/test_citas.py
- tests/test_policy.py
- tests/test_policy_bypass.py
- tests/test_policy_datos.py
- utils/citas.py
- utils/policy.py
- utils/politica_comandos.json

Agregados (3):
- banco/specs/s0_citas_ejecucion.md
- tests/fixtures/policy_pytest_autorizacion.json
- tests/test_autorizacion_pytest.py

Sin eliminaciones; 620 originales idénticos. Baselines,
dependencias, workflows, calidad.sh e inventario de tests permanecen intactos.

TWINS: searched llamadas a _por_nombre_suelto en todo el Python del ZIP y concesiones auto de pytest - found 0 other fallback sites; 0 concesiones auto de pytest restantes.

La búsqueda no certifica todos los lectores o ejecutores del harness.

## Lo que este patch no resuelve

No implementa plan versionado, skills sin regex, aislamiento SO, módulos hostiles,
automodificación ni cancelación. Autorizar pytest permite ejecutar código; no
confina sus efectos internos. Otros comandos auto aún requieren investigación y
Ruff puede escribir cachés. No se afirma que todo auto sea lectura estricta.

Las búsquedas abreviadas solo recorren bases fuente completamente autorizadas;
para scopes más profundos se puede necesitar una ruta explícita. No hay atomicidad
contra carreras entre validar y abrir (TOCTOU), protección de hardlinks ni promesa
universal de ausencia de canales laterales. Se verifica el caso visible reportado.

No se ejecutó calidad.sh, la suite completa, Pyright, Ruff ni cobertura. No se
instalaron paquetes. El entorno no permite extraer el checkout y carece de parte
del toolchain. El código necesario de S0 puede aumentar el ratchet de líneas:
no se compensó borrando código ajeno ni se modificó el baseline para pasar.

## Aplicar y validar

Solo contra el ZIP original de SHA256 `ab163eaf03f80c7a0298e5a4b270c536789b98061da2af2b20dc8eefbe6791ce`.
**No aplicar encima de las Entregas 01/02.** En una copia revisable del proyecto:

```sh
git apply --check deepseek-flow_s0.patch
git apply deepseek-flow_s0.patch
python3 -m pytest tests/test_citas.py tests/test_autorizacion_pytest.py tests/test_policy.py tests/test_policy_bypass.py tests/test_policy_datos.py tests/test_auditoria_2026_10_26.py -q
bash calidad.sh
```

Estos comandos son la validación siguiente en el entorno real, no corridas
atribuidas a esta entrega. Revisar los efectos del gate sobre artefactos y
baselines. Un fallo se investiga; no se debilitan tests ni se usa la clave del
operador para aparentar aceptación.

El instrumento verificar_patch_s0.py reproduce las sondas con los dos ZIP; usa
pytest instalado únicamente para su prueba sintética. No instala ni extrae
proyectos. El JSON distingue lo observado de las comprobaciones pendientes.

Durante la generación se corrigieron tres chequeos del instrumento: selector de
decorators, separación entre explicación y nivel, y una comparación excesiva de
expectativas antiguas/nuevas. No se cuentan esos intentos como pruebas aprobadas
ni se cambiaron requisitos para ocultarlos.

ZIP candidato SHA256: `8010bba9f12f5ca47aac10628b2bc1b451ba187d1941a1b5f117a37db9dccbe8`.
Entradas intactas; sin commits, pushes o cambios de GitHub; sondas eliminadas.
