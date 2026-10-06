# Spec exp/8 — parte 2: la compuerta por datos + split del veto + docs

(3 cambios de código + docs. Todo el texto está DADO. Fundamento medido:
el veto CONFIRMA el falso-directo "mundial" (directo 0.78 met) — error
correlacionado medido; la compuerta 0.85 lo bloquea antes: 26/30 vs 25/30
en el ensamble, mismos 3 arbitrajes. La subida global sin split le costaría
al veto la mitad de su cobertura local (83%→53%): por eso el split.)

## 1. `utils/laya.py` — default de la compuerta del router

En `veredicto()`, la línea que lee `alto = _setting("LAYA_UNSURE_HIGH", "0.7")`
(campo alto con default "0.7"): cambiar el default a `"0.85"`, y actualizar
el comentario del docstring si menciona 0.7. Contexto para el comentario:
0.85 es la rodilla de la curva propia (exp/7/exp/8: el único falso-directo
que pasa 0.7, "mundial" a 0.831, queda bloqueado; ningún directo-correcto
entre 0.7 y 0.85 lo pierde — t20-historia 0.62 ya estaba bloqueado).

## 2. `nodes.py` — el veto con su PROPIO umbral

En `voto_confirmacion_router`, la línea `if resp in ("herramientas", "directo") and veredicto(conf) == "met":`
cambiar por:
```python
    if resp in ("herramientas", "directo") and veredicto(
        conf, alto=float(_setting("LAYA_UNSURE_HIGH_VOTO", "0.7"))
    ) == "met":
```
`_setting` ya está importado en esa función. Comentario de una línea arriba:
el umbral del voto es propio (0.7): la curva del veto da 96% de precisión
con 83% de cobertura a 0.7, y subirlo junto al router le cortaría la mitad
de las decisiones locales.

## 3. `.env.example` — documentar los dos umbrales

Donde ya se documentan los settings de Laya, agregar:

```
# Compuerta del router (veredicto "met" del lado directo). 0.85 = rodilla de
# la curva medida (exp/8): bloquea el falso-directo "mundial" (0.83) sin
# perder ningún directo-correcto en la banda 0.7-0.85.
# LAYA_UNSURE_HIGH=0.85
# Umbral propio del voto (segunda capa): su curva está bien a 0.7 (96%
# precisión, 83% cobertura local) — separado para no arrastrarlo al router.
# LAYA_UNSURE_HIGH_VOTO=0.7
```

## 4. `tests/test_smoke.py` — UN test nuevo del contrato del split

Al final del archivo (estilo del proyecto, docstring en español):

```python
def test_split_umbrales_router_y_voto():
    """exp/8: la compuerta del router (LAYA_UNSURE_HIGH, 0.85 por default)
    y la del voto (LAYA_UNSURE_HIGH_VOTO, 0.7) son settings SEPARADOS: el
    veto no hereda la subida del router — su curva propia está bien a 0.7
    (96% precisión / 83% cobertura) y arrastrarlo le cortaría la mitad de
    las decisiones locales (83%→53%)."""
    from utils.laya import veredicto

    # default del router tras exp/8: 0.85 (antes 0.7, ley de bmo heredada)
    assert veredicto(0.84) == "uncertain"
    assert veredicto(0.85) == "met"
    # el voto consulta con su propio alto explícito: 0.7 sigue siendo "met"
    assert veredicto(0.75, alto=0.7) == "met"
```

## 5. `docs/design.md` — sección exp/8, DESPUÉS de la sección exp/7

(Insertar después del bloque que termina con "Decisión: NO re-ajustar
temperaturas con 54 casos.", texto textual):

```
### exp/8 — la compuerta del router, decidida por datos (2026-10-06)

La curva con semántica de producción (solo el lado "directo" se computa;
herramientas dudoso cae al lado seguro sin compuerta) y la medición del
ensamble completo (router_flow-1k + router_voto sobre las mismas 30
preguntas, `sonda_laya.py voto_en_router`) dieron el veredicto:

- **El veto CONFIRMA el falso-directo "mundial"**: responde "directo" con
  conf 0.78 (met) — las dos capas fallan juntas, el caso de eco que la
  Mesa 3 advertía como riesgo, ahora medido en un caso real del test.
- **Compuerta del router 0.7 → 0.85**: bloquea mundial ANTES de consultar
  al voto. En la banda 0.7–0.85 no hay ningún directo-correcto que lo
  pierda (t20-historia, 0.62, ya estaba bloqueado en todos los umbrales)
  — el kill es gratis. El ensamble pasa de 25/30 a 26/30 con los mismos 3
  arbitrajes.
- **El voto conserva su umbral propio** (LAYA_UNSURE_HIGH_VOTO=0.7): su
  curva da 96% de precisión con 83% de cobertura local a 0.7; heredar la
  subida del router le cortaría la cobertura a 53% sin ganar nada.
- El supervisor no se toca: 0.9 ya es exactamente la rodilla de su curva
  (exp/7).
- Caveat honesto: n=30. La curva es consistente con todo lo medido antes
  (mundial 0.83 documentado desde la curaduría), pero la banda 0.7–0.85
  tiene pocos casos; el round dirigido de "hechos actuales" del roadmap
  sigue siendo el refuerzo natural si aparecen más falsos-directos.
```

## 6. `docs/roadmap.md` — sección de ciclo de experimentos (al FINAL del archivo)

(Append textual):

```
## Ciclo de experimentos exp/ (2026-10-06)

Workflow: branch exp/N → gate ./calidad.sh verde → medición en el mensaje
del commit → merge --no-ff solo del ganador. El banco (banco/banco.py)
mide: marcadores por turno en conversación real contra DeepSeek.

- **exp/1 ✅ mergeada** — política HITL: `cd` neutro + `sort` whitelist +
  partir por `;` (hueco medido: `ls ; rm -rf /tmp/x` clasificaba auto).
  Los 5 run_command reales de la sesión del test exhaustivo: 2 pasan a
  auto, 0 se relajan peligrosos.
- **exp/6 ✅ mergeada** — banco de conversación: escenarios YAML contra el
  chat real por PTY, conteo de marcadores por turno (laya, voto, hitl,
  compacción, auto...), no contamina memoria, exit 0 = todo OK. Primera
  corrida 7/7 y prueba en vivo de exp/1 (run-auto sin s/n).
- **exp/7 ✅ mergeada** — sonda_laya.py: evidencia de Laya con vara propia
  (ECE, curva de compuerta, latencia CPU ~0.2 s, RSS 2.86 GiB/proceso).
  La compuerta 0.9 del supervisor = rodilla precisión=100% de su curva.
  Sección "Laya: estado de la evidencia" en design.md.
- **exp/8 ✅ mergeada** — compuerta del router 0.7→0.85 por datos + split
  LAYA_UNSURE_HIGH_VOTO (el veto conserva 0.7). El veto confirmaba el
  falso-directo "mundial" (0.78 met): error correlacionado medido; la
  compuerta nueva lo bloquea antes. Ensamble 25/30 → 26/30. Sección en
  design.md.
- **exp/9 (pendiente)** — minar los 114 .runs: taxonomía de errores de
  tools y qué pasó después de cada uno; decide si el triaje con noul de
  Laya se justifica (evidencia antes que integración).
```

## Reglas

Texto textual donde está dado. No correr la sonda ni evals (los corre el
conductor). No tocar .env (el real).
