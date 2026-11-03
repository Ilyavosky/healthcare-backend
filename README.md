# healthcare-backend

API del proyecto **Healthcare: Priorización de Urgencias Médicas**. Recibe una sala de urgencias (pacientes, médicos, inicio y meta) y devuelve la agenda calculada con Costo Uniforme y A*.

## Requisitos

- [uv](https://docs.astral.sh/uv/getting-started/installation/). Instala Python 3.12 si no lo tienes.

## Instalación

```bash
git clone https://github.com/Ilyavosky/healthcare-backend.git
cd healthcare-backend
uv sync
```

## Configuración

Copia la plantilla y edita los valores que necesites:

```bash
cp .env.example .env
```

En Windows (PowerShell): `Copy-Item .env.example .env`.

| Variable | Valor de ejemplo | Para qué |
|---|---|---|
| `ALLOWED_ORIGIN` | `http://localhost:3000,http://localhost:5173` | Direcciones del frontend que pueden llamar a la API, separadas por coma. Agrega aquí la URL de tu frontend desplegado. |
| `ALLOWED_ORIGIN_REGEX` | vacío | Opcional. Expresión regular para direcciones variables, por ejemplo `https://healthcare-[a-z0-9-]+\.vercel\.app` para las vistas previas de Vercel. |
| `SEARCH_TIME_LIMIT_MS` | `10000` | Tiempo máximo de búsqueda por algoritmo, en milisegundos. `0` = sin límite. |
| `FALLBACK_WEIGHTS` | `[1.5, 5]` | Pesos de A* ponderado que se prueban si A* no termina a tiempo. |
| `TRACE_LIMIT` | `500` | Nodos de la traza que se devuelven si la petición no indica `traceLimit`. |
| `MAX_TRACE_LIMIT` | `30000` | Máximo de nodos de la traza que se puede pedir. |

Si no existe `.env`, se usan estos mismos valores.

## Ejecutar

```bash
uv run fastapi dev app/main.py
```

La API queda en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`. Para un servidor sin recarga automática, usa `uv run fastapi run app/main.py`.

## Rutas

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/health` | Comprueba que el servidor responde. |
| POST | `/api/scenarios/generate` | Genera `n` pacientes aleatorios. Con la misma `seed` devuelve los mismos pacientes. |
| POST | `/api/solve` | Resuelve una sala. Los campos de entrada y salida están en `/docs`. |

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/solve \
  -H "Content-Type: application/json" \
  -d '{"patients":[{"id":"P1","level":2,"wait":5,"duration":20},{"id":"P2","level":3,"wait":40,"duration":5},{"id":"P3","level":1,"wait":0,"duration":30}],"doctors":1}'
```

## Pruebas

```bash
uv run pytest
uv run ruff format app tests
```

## Postman

Importa en Postman la colección y el entorno de la carpeta `postman/`:

| Archivo | Uso |
|---|---|
| `healthcare.postman_collection.json` | Recorrido de la API (14 peticiones). |
| `healthcare-pruebas.postman_collection.json` | Pruebas completas (158 peticiones). |
| `healthcare.postman_environment.json` | Para el servidor local. |
| `healthcare.railway.postman_environment.json` | Para el servidor en Railway. |

Desde la terminal, con el servidor local encendido:

```bash
npx newman run postman/healthcare-pruebas.postman_collection.json -e postman/healthcare.postman_environment.json
```

## Despliegue en Railway

Conecta el repositorio en Railway. `railway.toml` ya define el comando de arranque y la verificación en `/api/health`. En la pestaña *Variables* del servicio agrega las mismas variables de `.env`, con `ALLOWED_ORIGIN` igual a la URL del frontend.
