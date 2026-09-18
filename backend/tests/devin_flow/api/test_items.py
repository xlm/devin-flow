from fastapi.testclient import TestClient


def test_list_items_empty(unit_client: TestClient) -> None:
    response = unit_client.get("/api/items")
    assert response.status_code == 200
    assert response.json() == []


def test_create_then_list(unit_client: TestClient) -> None:
    created = unit_client.post("/api/items", json={"name": "widget"})
    assert created.status_code == 201
    assert created.json() == {"id": 1, "name": "widget"}
    assert unit_client.get("/api/items").json() == [{"id": 1, "name": "widget"}]


def test_create_duplicate_is_409(unit_client: TestClient) -> None:
    assert unit_client.post("/api/items", json={"name": "dup"}).status_code == 201
    response = unit_client.post("/api/items", json={"name": "dup"})
    assert response.status_code == 409
    assert response.json() == {"detail": "item 'dup' already exists"}
    assert len(unit_client.get("/api/items").json()) == 1


def test_create_requires_name(unit_client: TestClient) -> None:
    assert unit_client.post("/api/items", json={}).status_code == 422
