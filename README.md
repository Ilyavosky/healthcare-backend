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
