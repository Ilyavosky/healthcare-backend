from app.search.generator import generate_patients


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_generate_is_reproducible(client):
    data = client.post("/api/scenarios/generate", json={"n": 6, "seed": 3}).json()
    assert data["seed"] == 3
    expected = generate_patients(6, 3)
    assert [p["id"] for p in data["patients"]] == [p.patient_id for p in expected]
    assert [p["wait"] for p in data["patients"]] == [p.wait for p in expected]


def test_generate_without_seed_returns_one(client):
    data = client.post("/api/scenarios/generate", json={"n": 4}).json()
    assert isinstance(data["seed"], int)
    again = client.post("/api/scenarios/generate", json={"n": 4, "seed": data["seed"]})
    assert again.json()["patients"] == data["patients"]


def test_generate_any_size(client):
    data = client.post("/api/scenarios/generate", json={"n": 300, "seed": 1}).json()
    assert len(data["patients"]) == 300


def test_generate_rejects_zero(client):
    response = client.post("/api/scenarios/generate", json={"n": 0})
    assert response.status_code == 422
    assert response.json()["field"] == "n"


def test_generated_scenario_can_be_solved(client):
    scenario = client.post("/api/scenarios/generate", json={"n": 7, "seed": 9}).json()
    response = client.post(
        "/api/solve", json={"patients": scenario["patients"], "doctors": 2}
    )
    assert response.status_code == 200
    assert response.json()["sameCost"] is True


def test_cors_allows_frontend_origin(client):
    response = client.options(
        "/api/solve",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_other_origin(client):
    response = client.options(
        "/api/solve",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def preflight(client, origin: str):
    return client.options(
        "/api/solve",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


def test_cors_default_allows_next_dev_server(client):
    response = preflight(client, "http://localhost:3000")
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_regex_allows_vercel_previews():
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        allowed_origin="https://healthcare.vercel.app",
        allowed_origin_regex=r"https://healthcare-[a-z0-9-]+\.vercel\.app",
    )
    client = TestClient(create_app(settings))
    exact = preflight(client, "https://healthcare.vercel.app")
    preview = preflight(client, "https://healthcare-git-develop-mayte.vercel.app")
    other = preflight(client, "https://otro.vercel.app")
    assert (
        exact.headers["access-control-allow-origin"] == "https://healthcare.vercel.app"
    )
    assert (
        preview.headers["access-control-allow-origin"]
        == "https://healthcare-git-develop-mayte.vercel.app"
    )
    assert "access-control-allow-origin" not in other.headers
