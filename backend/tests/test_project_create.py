def test_create_project_returns_key_once(client):
    response = client.post("/api/v1/projects", json={"name": "My Web App"})
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "my-web-app"
    assert body["api_key"].startswith("flk_")

    # key works for ingestion
    created = client.post(
        "/api/v1/ingest/runs",
        json={"run_uuid": "11111111-2222-3333-4444-555555555555"},
        headers={"X-Api-Key": body["api_key"]},
    )
    assert created.status_code == 200

    # duplicate slug rejected
    assert client.post("/api/v1/projects", json={"name": "My Web App"}).status_code == 409

    # additional key can be minted
    extra = client.post(f"/api/v1/projects/{body['slug']}/keys").json()
    assert extra["api_key"].startswith("flk_")
    assert extra["api_key"] != body["api_key"]
