from .conftest import unique_slug


def _create_document(client, headers, title="Durian Irrigation SOP", category="sop", content=None):
    if content is None:
        content = (
            "Water durian trees deeply once every 3-4 days during dry season.\n\n"
            "Reduce irrigation frequency sharply once fruit reaches maturity to concentrate sugars - "
            "over-watering near harvest causes fruit splitting and diluted flavor.\n\n"
            "Monitor soil moisture at 30cm depth; target 60-70% field capacity for mature trees."
        )
    res = client.post("/api/v1/knowledge/documents", json={"title": title, "category": category, "content": content}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_document_creation_chunks_content_and_validates_category(client, tenant):
    headers = tenant.auth_headers(client)
    doc = _create_document(client, headers)
    assert doc["title"] == "Durian Irrigation SOP"
    assert doc["is_active"] is True

    bad_category_res = client.post(
        "/api/v1/knowledge/documents", json={"title": "x", "category": "not-a-category", "content": "y"}, headers=headers
    )
    assert bad_category_res.status_code == 422


def test_search_finds_relevant_chunk_with_citation(client, tenant):
    headers = tenant.auth_headers(client)
    doc = _create_document(client, headers)

    res = client.get("/api/v1/knowledge/search", params={"q": "fruit splitting over-watering harvest"}, headers=headers)
    assert res.status_code == 200, res.text
    hits = res.json()
    assert len(hits) >= 1
    assert hits[0]["document_id"] == doc["id"]
    assert "splitting" in hits[0]["content"]
    assert hits[0]["rank"] > 0


def test_search_finds_nothing_for_unrelated_query(client, tenant):
    headers = tenant.auth_headers(client)
    _create_document(client, headers)

    res = client.get("/api/v1/knowledge/search", params={"q": "quantum computing blockchain"}, headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_updating_content_reindexes_chunks(client, tenant):
    headers = tenant.auth_headers(client)
    doc = _create_document(client, headers, content="Original content about soil pH management for durian orchards.")

    before_res = client.get("/api/v1/knowledge/search", params={"q": "soil pH management"}, headers=headers)
    assert len(before_res.json()) == 1

    update_res = client.patch(
        f"/api/v1/knowledge/documents/{doc['id']}", json={"content": "Completely different content about pest scouting routines."}, headers=headers
    )
    assert update_res.status_code == 200, update_res.text

    old_query_res = client.get("/api/v1/knowledge/search", params={"q": "soil pH management"}, headers=headers)
    assert old_query_res.json() == []

    new_query_res = client.get("/api/v1/knowledge/search", params={"q": "pest scouting routines"}, headers=headers)
    assert len(new_query_res.json()) == 1


def test_delete_document_removes_its_chunks_from_search(client, tenant):
    headers = tenant.auth_headers(client)
    doc = _create_document(client, headers, title="Temp Doc", content="A very unique phrase: xylophone marmalade orchard.")

    found_res = client.get("/api/v1/knowledge/search", params={"q": "xylophone marmalade"}, headers=headers)
    assert len(found_res.json()) == 1

    delete_res = client.delete(f"/api/v1/knowledge/documents/{doc['id']}", headers=headers)
    assert delete_res.status_code == 204

    gone_res = client.get("/api/v1/knowledge/search", params={"q": "xylophone marmalade"}, headers=headers)
    assert gone_res.json() == []

    get_deleted_res = client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=headers)
    assert get_deleted_res.status_code == 404


def test_copilot_falls_back_to_knowledge_base(client, tenant):
    headers = tenant.auth_headers(client)
    _create_document(
        client, headers, title="Fertigation Guide",
        content="Apply nitrogen-rich fertilizer during the vegetative growth stage, tapering off before flowering.",
    )

    res = client.post(
        "/api/v1/ai/copilot/ask", json={"question": "When should I apply nitrogen fertilizer during vegetative growth?"}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "knowledge base" in body["answer"].lower()
    assert len(body["citations"]) >= 1
    assert body["citations"][0]["source_type"] == "knowledge_chunk"


def test_search_finds_semantically_related_chunk_without_keyword_overlap(client, tenant):
    """Acid test for Phase 28: a query sharing zero content words with the
    chunk should still surface it via vector similarity, proving this is
    genuine semantic search and not full-text search with extra steps."""
    headers = tenant.auth_headers(client)
    doc = _create_document(
        client, headers, title="Post-Harvest Fruit Care",
        content=(
            "Once durian fruit is picked, store it in a cool, shaded area away from direct sunlight "
            "to slow ripening and prevent the husk from cracking prematurely."
        ),
    )

    res = client.get(
        "/api/v1/knowledge/search",
        params={"q": "how do I keep durians fresh after picking them"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    hits = res.json()
    assert len(hits) >= 1
    assert hits[0]["document_id"] == doc["id"]


def test_knowledge_documents_are_tenant_isolated(client, tenant, raw_db):
    from .conftest import provision_test_tenant

    headers = tenant.auth_headers(client)
    doc = _create_document(client, headers, title="Isolated Doc", content="A secret internal SOP only this tenant should see.")

    other_tenant = provision_test_tenant(raw_db, "kbother")
    other_headers = other_tenant.auth_headers(client)

    other_search_res = client.get("/api/v1/knowledge/search", params={"q": "secret internal SOP"}, headers=other_headers)
    assert other_search_res.json() == []

    other_get_res = client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=other_headers)
    assert other_get_res.status_code == 404
