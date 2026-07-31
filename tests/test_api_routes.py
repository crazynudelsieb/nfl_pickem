"""/api/groups and /api/search used to 500 unconditionally.

Both iterated User.get_groups() as if it returned GroupMember rows; it returns
Group objects, so every call raised AttributeError. Nothing in the UI calls
them, which is why the breakage went unnoticed.
"""

from app.models import Group


def login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def test_api_groups_returns_user_groups(app, users, group):
    client = app.test_client()
    login(client, users[0])

    response = client.get("/api/groups")

    assert response.status_code == 200
    payload = response.get_json()
    assert [g["name"] for g in payload] == ["Test Group"]


def test_api_groups_includes_invite_code_for_members(app, users, group):
    client = app.test_client()
    login(client, users[0])

    payload = client.get("/api/groups").get_json()

    assert payload[0]["invite_code"] == group.invite_code


def test_api_search_returns_results(app, db, users, group):
    client = app.test_client()
    login(client, users[0])

    response = client.get("/api/search?q=Test")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["query"] == "Test"
    assert [g["name"] for g in payload["results"]["groups"]] == ["Test Group"]


def test_api_search_withholds_invite_code(app, db, users, group):
    """A public group the caller has not joined must not leak its join code."""
    outsider = Group(name="Public Club", creator_id=users[1].id, is_public=True)
    db.session.add(outsider)
    db.session.commit()

    client = app.test_client()
    login(client, users[0])

    payload = client.get("/api/search?q=Public").get_json()
    found = [g for g in payload["results"]["groups"] if g["name"] == "Public Club"]

    assert found, "public group should be discoverable"
    assert "invite_code" not in found[0]


def test_api_search_empty_query(app, users, group):
    client = app.test_client()
    login(client, users[0])

    response = client.get("/api/search?q=")

    assert response.status_code == 200
    assert response.get_json() == {"results": {}}
