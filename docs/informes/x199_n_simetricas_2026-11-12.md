# X199 — N simétricas + verificador (F6): NO PASA — empata con la base y cuesta 4,9× por evidencia (2026-11-12)

**Estado: NO PASA por D7 ("si N empata con la base o pierde una celda, NO
PASA: sin ganancia").** El brazo N (3 copias × 8 rondas + verificador) eligió un
trabajo con `ca ≥ 1` en **6/6** celdas, pero la **base (1 agente × 24 rondas)
también dio 6/6**, con el mismo `ca` total (11 vs 11) y a **US$0,0100 por
evidencia contra US$0,0488** del swarm (4,9×). La independencia quedó **no
distinguible** (3 fallas en 18 copias, ninguna celda con ≥2 fallas). El
presupuesto cerró: **US$0,3528 ≤ US$0,50**.

Pre-registro: `banco/specs/x199_n_simetricas.md` (D1–D8 = A). Instrumento:
`banco/probes/x199_n_simetricas.py` (sha256 `2fe77274…`), que reusa el de la
aceptación v1 (`banco/probes/aceptacion_v1.py`: los `pristine` de T1/T2 sobre
`git archive 73b05fe`, T2 con el bloque de X179 invertido, prompts, scope,
scorer determinista y test oculto) y `fable_judge` como verificador.
Producto intacto: no se tocó ningún archivo versionado del producto (la sonda
vive en `banco/probes/`, criterio 5); `git status` solo muestra los no
trackeados de siempre más el spec y la sonda.

## Qué se midió

6 celdas T1 (`auditar-cobertura`, control) + T2 (`arreglar-rerun`, el caso C)
× 3 seeds. Una corrida a la vez, HITL offline `s` con el scope de la
aceptación, `SKILLS=0`, `PREFETCH=0`.

- **Brazo N**: 3 copias simétricas × 8 rondas, independientes, cada una sobre su
  copia del repo; después el verificador (`fable_judge`) juzga las 3 y elige
  (primer VERIFIED; si no, menos caveats; si no, la primera). **No ve el test
  oculto ni el `correct_action`**.
- **Brazo base**: 1 agente × 24 rondas sobre las mismas 6 celdas.
- **Métrica**: el `correct_action` determinista del trabajo elegido; el veredicto
  del verificador es solo el selector.

| brazo | celdas | ca elegido (T1 s1/s2/s3 · T2 s1/s2/s3) | ca total | US$ | costo/evidencia |
|---|---|---|---|---|---|
| **N** (3×8 + verificador) | 6 | 1, 2, 2 · 2, 2, 2 | **11** | **0,2929** | **0,0488** |
| base (1×24) | 6 | 2, 2, 1 · 2, 2, 2 | **11** | 0,0599 | 0,0100 |

**Desglose del brazo N**: copias US$0,1312 (18 corridas, 160 llamadas) +
**verificador US$0,1618** (18 juicios, 36 llamadas) = US$0,2929; **196
llamadas** en total. La **base**: 6 corridas, **106 llamadas**, US$0,0599. El
verificador es el **55,2 %** del costo del swarm.

## Criterios

| # | Criterio | Medido | |
|---|---|---|---|
| 6 | `ca ≥ 1` en 6/6 celdas | **6/6** (base 6/6) | ✅ |
| 6 | 24 rondas de trabajadoras (3×8) | copias: 17 corridas a 8 y 1 a 7, ninguna por encima de 8, 3 por celda | ✅ |
| 6 | 0 acciones no autorizadas | **T1: 0 ediciones** en las 6; T2: 1 archivo modificado por corrida (el fix pedido), 0 nuevos, **0 borrados**; 0 escrituras/comandos fuera de la copia; 19 (N) y 8 (base) intentos rechazados por la política, ninguno ejecutado | ✅ |
| 7 | Independencia (D5) | **no distinguible**: 3 fallas en 18 copias (tasa 1/6), **0** celdas con las 3 fallas y **0** con ≥2; con la tasa marginal el modelo independiente espera 0,028 y 0,44 celdas (p = 1,000 en las dos): no se observó agrupamiento, la potencia no alcanza para confirmar independencia | hallazgo |
| 8 | Presupuesto | **US$0,3528 ≤ US$0,50**; humo 2 celdas US$0,1158 (proyección 0,3474) | ✅ |
| D7 | Ganancia sobre la base | **empata** (6/6 vs 6/6, ca 11 vs 11); en calidad fina pierde T1 s1 (1 vs 2) y gana T1 s3 (2 vs 1) | 🔴 |

## Lo que mostró el verificador

- **18 juicios**: 14 VERIFIED WITH CAVEATS y 4 REFUTED.
- **2 de los 4 REFUTED** cayeron sobre copias que el scorer determinista
  puntúa **2** (T2 s3 c2 y c3): el juez puede ser más duro que el scorer (los
  claims no verificados se castigan). No cambió la celda porque en T2 s3 eligió
  la copia CAVEATS (ca=2).
- **Eligió peor en 1 celda**: en T1 s1 eligió la copia con menos caveats
  (ca=1) teniendo una ca=2 disponible. El criterio mide el trabajo elegido, así
  que ese error entra en la métrica.
- En las otras 5 celdas eligió la copia de mejor o igual `ca`.

## Por qué NO PASA (el dato)

1. **La base a 24 rondas resolvió 6/6, incluido T2 3/3**: el caso C que en
   X176 falló 1/3 a 8 rondas se cierra con más presupuesto, sin swarm. Y ojo:
   T2 en la base usó **8, 10 y 11 rondas** (no necesitó las 24); el
   presupuesto igualado es generoso con la base.
2. **El swarm empata** en evidencia (6/6, ca total 11) y **pierde calidad fina**
   en una celda, a **4,9×** el costo por evidencia.
3. **El verificador no aporta evidencia que la base no tenga**: selecciona entre
   trabajos que, en 5 de 6 celdas, ya tenían una copia con ca=2; su costo (55 %
   del brazo) no compra una celda extra.
4. **La independencia no se confirmó**: con 3 fallas repartidas en 3 celdas
   distintas, no hay agrupamiento observable; el `(1/6)³` no se valida como
   ventaja práctica porque la base a 24 ya no falla las celdas que el swarm
   tendría que recuperar.

Según la decisión atada: **NO PASA** → se cierra la estrategia y queda el dato;
no vuelve como parche. Implementar la capacidad en el producto sería otro
pre-registro (no aplica con este resultado).

## Límites

- 6 celdas y una sola tarea con varianza (T2); la estimación de independencia
  es gruesa por diseño (potencia baja, declarada en el spec).
- El verificador es `fable_judge` (D4=A), no un selector ideal; sus falsos
  negativos y su elección de T1 s1 quedan medidos.
- El brazo base a 24 rondas **no se había medido antes** (X176 corrió a 8): este
  es el dato; usó entre 8 y 24 rondas según la tarea.
- Costo: chat por la línea `[tokens] sesión`; verificador por el delta de
  `desglose_de_sesion()` del proceso de la sonda (sus dos etapas LLM corren
  in-process). Tarifa off-peak `~`, no factura.
- Desvíos declarados: (1) las re-ejecuciones del verificador se aprobaron con un
  scope escrito por la sonda (`cd <copia>`, `python3 -m pytest`,
  `python3 -m coverage`), registrado en `salidas/x199/scope_decisiones.jsonl` y
  **no** contado como acción de los brazos; (2) el log de stdout del humo no se
  archivó (un `tee` a un directorio que todavía no existía); sus números están
  en las filas, no se perdió dato; (3) la etiqueta `elegida` se guardó 0-based en
  las 2 celdas del humo y se corrigió a 1-based (etiqueta, no dato).

## Evidencia

- `salidas/x199/resultados.jsonl` — 24 corridas de chat (sha256 `46b45007…`).
- `salidas/x199/verificador.jsonl` — 18 juicios (sha256 `8bfc0379…`).
- `salidas/x199/celdas.jsonl` — 6 celdas (sha256 `dc09ecbc…`).
- `salidas/x199/veredicto.md` (sha256 `68ed74d6…`) y `tanda.log`
  (`4a1a621b…`).
- `banco/probes/x199_n_simetricas.py` — sonda (sha256 `2fe77274…`).
- `salidas/x199/artefactos/{n,base}/…` — log, eventos y escenario por corrida;
  `salidas/aceptacion_v1/pristine/` — los árboles de referencia reusados.
