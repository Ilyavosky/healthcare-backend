# healthcare-backend

API y motor de búsqueda del proyecto **Healthcare: Priorización de Urgencias Médicas** (Fundamentos de IA, UPChiapas, 7C).

## Modelo

- **M médicos** atienden en paralelo a **N pacientes** de una sala de urgencias. No hay tope para M ni para N; si M es mayor que los pendientes, en el estado solo se guardan tantos médicos como pacientes pendientes, porque los demás nunca se usan.
- Cada paciente tiene nivel de triage (1 Crítico a 5 No urgente), minutos que ya esperaba al iniciar el turno (`wait`) y duración estimada de consulta (`duration`).
- Penalización de atender a `p` en el minuto `t`: `peso(nivel) · max(0, wait + t − límite(nivel))`.
- **Estado:** `(attended, free_at)` = pacientes ya atendidos y minuto en que se libera cada médico, ordenado.
- **Acción:** atender a un pendiente con el médico que se libera primero.
- **Inicio modificable:** pacientes ya atendidos, minuto actual `t0` y minuto en que se libera cada médico.
- **Meta modificable:** todos, críticos (N1–N2), K pacientes, horizonte H o subconjunto. Al cumplirse, los pendientes se cobran con el cierre por protocolo de triage.
- **Regla de seguridad (`critical_first`):** si hay un Nivel 1 pendiente que cabe, solo se puede atender a un Nivel 1.
- **Algoritmos:** `ucs` (h = 0), `astar_simple` (penalización de los pendientes si empezaran en `l1`) y `astar` (la anterior más la espera mínima extra: el k-ésimo en empezar lo hace como pronto en `min(L[k], l1 + d_min)` si k < M, o tras las ⌊k/M⌋ consultas más cortas si k ≥ M). Las dos heurísticas son admisibles; `astar` puede ser inconsistente con varios médicos, por eso el motor reabre nodos cerrados cuando encuentra un g mejor (`SearchResult.reopened`) y conserva la optimalidad.
- **A\* ponderado:** `search(..., weight=ε)` usa f = g + ε·h; termina mucho antes en salas grandes y garantiza costo ≤ ε · óptimo.
- **Escenarios:** `generate_patients(n, seed)` (reproducible, probabilidades y rangos por nivel) y `patients_to_csv` / `patients_from_csv` con columnas `patient_id,level,wait,duration`.
- **Línea base:** `level_order` atiende por nivel, desempata por mayor espera y luego por orden de captura, con el médico que se libera primero y el mismo cierre. `order_cost` evalúa cualquier orden.
- **Agenda:** `build_schedule(problem, order)` da, por paciente, médico (numerados en el orden en que se capturaron sus minutos de liberación), inicio, fin, retraso, penalización y si quedó fuera de la meta. Siempre suma lo mismo que el costo de la búsqueda.
- **Alertas:** `ALREADY_LATE`, `EXCEEDS_LIMIT`, `NEAR_LIMIT` (margen de 10 min), `LEFT_OUT` y `LEFT_OUT_CRITICAL`. Solo se devuelve el código y los minutos; los textos los pone el frontend.
- **Servicio `solve`:** corre los algoritmos pedidos (por defecto `ucs` y `astar`) y la línea base, y calcula `same_cost`, la reducción de nodos contra UCS y la brecha de la base contra el óptimo. Con `time_limit_ms` y `fallback_weights`, si A\* no termina reintenta con A\* ponderado e informa el ε usado. Si ningún algoritmo termina, devuelve la agenda de la línea base.
- **Desempates de la frontera:** a igual f sale primero el de menor h, luego el más profundo, y META gana cualquier empate. Así, cuando todas las agendas cuestan lo mismo (por ejemplo, tantos médicos como pacientes), A\* va directo a la meta en N + 2 expansiones.
- **Poda exacta por orden irrelevante:** si hay al menos tantos médicos libres como pacientes pendientes y todos se liberan en el mismo minuto, cualquier orden cuesta lo mismo, así que se genera un solo sucesor. Así, 500 pacientes con 500 médicos se resuelven en 55 ms.
- **Presupuesto de tiempo:** `timeLimitMs` es el total por algoritmo. El intento óptimo usa la mitad y cada reintento ponderado la mitad de lo que queda. El límite también se revisa dentro de cada expansión.
- **Límite de búsqueda:** `search` acepta `max_expanded` y `time_limit_ms` (por defecto sin límite). No restringen la entrada; detienen una corrida que crece demasiado con `SearchLimitError`, que reporta los nodos expandidos.

## Supuestos

Médicos idénticos; el nivel de triage es un dato de entrada; duraciones fijas y sin interrupción; un médico libre siempre atiende; el entorno es una foto de la sala en `t0` y se replanifica cuando cambia.

## API

`uv run fastapi dev app/main.py` y abrir `http://localhost:8000/docs`. Todo el JSON va en camelCase.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/health` | `{ "status": "ok" }` |
| GET | `/api/config` | Niveles (nombre, peso, límite), tipos de meta, algoritmos, códigos de alerta, columnas del CSV y valores por defecto |
| POST | `/api/scenarios/generate` | `{ n, seed? }` → `{ seed, patients }` reproducible |
| POST | `/api/scenarios/csv` | Archivo CSV (`multipart/form-data`, campo `file`) → `{ patients }` |
| POST | `/api/scenarios/csv/export` | `{ patients }` → descarga `escenario.csv` |
| POST | `/api/solve` | Resuelve un escenario en memoria |

**`POST /api/solve`:**
- **Entrada:**
  - `patients[]` con `{ id, level, wait, duration }`;
  - `start` con `{ attended, t0, doctorsFreeAt? }`;
  - `doctors`, `goal` con `{ type, value }`, `algorithms`, `criticalFirst`, `includeTrace`, `traceLimit?`, `timeLimitMs?` y `allowApproximate`.
- **Salida:**
  - `results.<alg>` con `status` (`optimal`, `approximate` o `limit_reached`), `weight`, `cost`, `closingCost`, `expanded`, `maxFrontier`, `ms`, `reopened`, `steps[]`, `leftOut[]`, `trace[]` y `limitAttempts[]`. Cada fila de `trace` es un nodo expandido con `id`, `parent`, `patient`, `attended`, `freeAt`, `isGoal`, `g`, `h`, `f` y `children[] { id, patient, g, h, f, replaces }`, los sucesores que generó; `replaces` es el id de la entrada de la frontera que ese hijo deja obsoleta por llegar al mismo estado con menor g. Con `parent` y `children` se reconstruye el árbol de búsqueda, y quitando los `replaces` se obtiene la frontera real;
  - además `baseline`, `reference`, `cost`, `sameCost`, `reductionPct`, `baselineGapPct` y `alerts[]`.
  - `referenceKind` dice qué agenda se muestra: `optimal`, `approximate` (A\* ponderado), `anytime` o `baseline` (orden por gravedad).
- **Si un algoritmo no termina** (`limit_reached`): devuelve la traza parcial del intento con ε = 1 y `anytime { nodeId, searchSteps, cost, lowerBound, steps[], leftOut[] }`. Es la agenda que sale de completar por triage el mejor nodo de la frontera; `searchSteps` son los pasos que eligió la búsqueda, `nodeId` es el nodo de la traza del que parte (−1 si salió de un intento ponderado) y `lowerBound` es la menor g + h de la frontera, una cota inferior del óptimo. Si esa agenda cuesta menos que el orden por gravedad, es la que se muestra (`referenceKind: anytime`).
- **Pasos:** cada paso trae `{ patient, level, doctor, start, end, delay, penalty, afterGoal }`.

**Errores:** siempre `{ code, message, field }`, también en 404 (`NOT_FOUND`), 405 (`METHOD_NOT_ALLOWED`) y 500 (`INTERNAL_ERROR`). Los errores de validación (`VALIDATION_ERROR`) y del dominio responden 422, con el mensaje en español.

**Tipos estrictos:**
- Los números deben ser números y los booleanos booleanos: `"2"`, `2.0`, `true` o `"yes"` se rechazan.
- Los textos se recortan, así que `" P1 "` y `"P1"` son el mismo id.
- `goal.value` solo acepta un entero (K u horizonte) o una lista de ids.

**Tamaños:**
- No hay tope para pacientes ni médicos en `/api/solve`; 10¹² médicos funcionan.
- `/api/scenarios/generate` admite hasta 100 000 pacientes, para proteger la memoria del servidor.

**Variables de `.env`:**
- `ALLOWED_ORIGIN`: separadas por coma si son varias.
- `ALLOWED_ORIGIN_REGEX`: opcional, para los dominios de preview de Vercel, por ejemplo `https://healthcare-[a-z0-9-]+\.vercel\.app`.
- `SEARCH_TIME_LIMIT_MS`: por algoritmo e intento; 0 = sin límite.
- `FALLBACK_WEIGHTS`: JSON, por ejemplo `[1.5, 5]`.
- `TRACE_LIMIT`: nodos expandidos que se devuelven en la traza si la petición no manda `traceLimit`.
- `MAX_TRACE_LIMIT`: tope para `traceLimit` (30000 por defecto).
- `MAX_CSV_BYTES`.

## Postman

| Archivo | Para qué |
|---|---|
| `postman/healthcare.postman_collection.json` | Recorrido funcional: 17 peticiones |
| `postman/healthcare-pruebas.postman_collection.json` | Pruebas exhaustivas: 160 peticiones con oráculo independiente |
| `postman/healthcare.postman_environment.json` | Entorno local |
| `postman/healthcare.railway.postman_environment.json` | Entorno de Railway |

En la colección exhaustiva, cada respuesta de `/solve` se revisa en JavaScript:
- recalcula el óptimo por fuerza bruta (hasta 9 pendientes) y la línea base;
- verifica cada paso de cada agenda (médico, inicio, fin, retraso, penalización, acción válida, regla N1, meta y cierre);
- verifica las alertas, las métricas, el formato de error y las claves en camelCase.

## Comandos

```bash
uv sync
uv run pytest -v
uv run ruff format app tests
uv run fastapi dev app/main.py
```
