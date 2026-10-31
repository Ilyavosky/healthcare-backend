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
- **Límite de búsqueda:** `search` acepta `max_expanded` y `time_limit_ms` (por defecto sin límite). No restringen la entrada; detienen una corrida que crece demasiado con `SearchLimitError`, que reporta los nodos expandidos.

## Supuestos

Médicos idénticos; el nivel de triage es un dato de entrada; duraciones fijas y sin interrupción; un médico libre siempre atiende; el entorno es una foto de la sala en `t0` y se replanifica cuando cambia.

## Comandos

```bash
uv sync
uv run pytest -v
uv run ruff format app tests
uv run fastapi dev app/main.py
```
