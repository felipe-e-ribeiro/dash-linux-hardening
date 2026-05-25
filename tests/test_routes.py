def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_import_page_returns_200(client):
    response = client.get("/import")
    assert response.status_code == 200


def test_api_reports_returns_json(client):
    response = client.get("/api/reports")
    assert response.status_code == 200
    assert response.is_json
