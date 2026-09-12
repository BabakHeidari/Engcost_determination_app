import json

from utils.audit import summarize_grant_changes
from utils.profile_store import ProfileDataStore, ProfileDataValidationError
from utils.profile_view import build_profile_view_model


def user(user_id, role="USER", grants=None):
    return {"id": user_id, "username": user_id, "email": f"{user_id}@example.com",
            "email_normalized": f"{user_id}@example.com", "full_name": user_id,
            "system_role": role, "job_title": "", "access_grants": grants or [],
            "is_active": True, "must_change_password": False, "password_hash": "hash",
            "password_scheme": "werkzeug", "revision": 1}


def seeded(tmp_path, limit=1000):
    store = ProfileDataStore(tmp_path / "app.json", audit_event_limit=limit)
    store.initialize({})
    store.create_factory({"id": "F1", "code": "F1", "name": "یک", "is_active": True})
    store.create_factory({"id": "F2", "code": "F2", "name": "دو", "is_active": True})
    store.create_user(user("admin", "IT_ADMIN"))
    store.create_user(user("ordinary"))
    return store


def test_required_user_events_are_canonical_safe_and_exactly_once(tmp_path):
    store = seeded(tmp_path)
    target = store.get_user_by_id("ordinary")
    grants = [{"scope_type": "FACTORY", "factory_id": "F1", "module": "product",
               "permissions": ["READ", "WRITE"]},
              {"scope_type": "GLOBAL", "factory_id": None, "module": "desk",
               "permissions": ["READ", "WRITE", "MODIFY"]}]
    store.update_user_as_actor("admin", "ordinary", {
        "job_title": "کارشناس", "access_grants": grants, "is_active": False,
    }, target["revision"])
    events = store.load_data()["audit_events"]
    actions = [event["action"] for event in events]
    for action in ("USER_UPDATED", "JOB_TITLE_CHANGED", "ACCESS_GRANTS_CHANGED", "USER_DEACTIVATED"):
        assert actions.count(action) == 1
    access = next(event for event in events if event["action"] == "ACCESS_GRANTS_CHANGED")
    assert access["changes"]["grants"] == [
        {"scope_type": "FACTORY", "factory_id": "F1", "module_id": "product", "before": "NONE", "after": "WRITE"},
        {"scope_type": "GLOBAL", "factory_id": None, "module_id": "desk", "before": "NONE", "after": "MODIFY"},
    ]
    assert not any(secret in json.dumps(events).casefold() for secret in ("password_hash", "reset_token", "session_id"))


def test_desk_policy_is_not_materialized_and_all_modules_normalize():
    assert summarize_grant_changes([], []) == []
    modules = ("cost_calculation", "dashboard", "desk", "factory_parameters",
               "general_parameters", "product", "profile")
    before, after = [], []
    for module in modules:
        scope = "GLOBAL" if module in {"dashboard", "desk", "general_parameters", "profile"} else "FACTORY"
        factory_id = None if scope == "GLOBAL" else "F1"
        before.append({"scope_type": scope, "factory_id": factory_id, "module": module, "permissions": ["READ"]})
        after.append({"scope_type": scope, "factory_id": factory_id, "module": module, "permissions": ["READ", "WRITE", "MODIFY"]})
    changes = summarize_grant_changes(before, after)
    assert {item["module_id"] for item in changes} == set(modules)
    assert all(item["before"] == "READ" and item["after"] == "MODIFY" for item in changes)
    assert "auth" not in json.dumps(changes)


def test_visibility_factory_isolation_and_safe_serialization(tmp_path):
    store = seeded(tmp_path)
    f1_grant = [{"scope_type": "FACTORY", "factory_id": "F1", "module": "product", "permissions": ["READ"]}]
    store.update_user("ordinary", {"access_grants": f1_grant})
    store.append_audit_event({"id": "mine", "occurred_at": "2026-01-01T00:00:00Z", "actor_user_id": "ordinary",
        "target_type": "user", "target_id": "ordinary", "action": "USER_UPDATED", "factory_id": "F1", "module_id": "product"})
    store.append_audit_event({"id": "hidden", "occurred_at": "2026-01-02T00:00:00Z", "actor_user_id": "ordinary",
        "target_type": "user", "target_id": "ordinary", "action": "USER_UPDATED", "factory_id": "F2", "module_id": "product"})
    model = build_profile_view_model(store, store.get_user_by_id("ordinary"))
    assert [event["id"] for event in model["audit_events"]] == ["mine"]
    assert "changes" not in json.dumps(model)


def test_retention_is_bounded_and_records_policy(tmp_path):
    store = seeded(tmp_path, limit=2)
    for index in range(3):
        store.append_audit_event({"id": f"e{index}", "actor_user_id": "admin", "target_type": "user",
                                  "target_id": "admin", "action": "USER_UPDATED"})
    data = store.load_data()
    assert [event["id"] for event in data["audit_events"]] == ["e1", "e2"]
    assert data["metadata"]["audit_retention"]["discarded_count"] == 1
    assert data["metadata"]["audit_retention"]["live_limit"] == 2


def test_secret_and_auth_module_metadata_fail_closed(tmp_path):
    store = seeded(tmp_path)
    for event in (
        {"action": "USER_UPDATED", "actor_user_id": "admin", "target_type": "user", "target_id": "ordinary", "changes": {"reset_token": "x"}},
        {"action": "ACCESS_GRANTS_CHANGED", "actor_user_id": "admin", "target_type": "user", "target_id": "ordinary", "module_id": "auth"},
    ):
        try:
            store.append_audit_event(event)
        except ProfileDataValidationError:
            pass
        else:
            raise AssertionError("unsafe audit event was accepted")


def test_known_legacy_events_are_normalized_in_place(tmp_path):
    store = seeded(tmp_path)
    store.append_audit_event({"id": "legacy", "actor_user_id": "admin", "target_type": "user",
                              "target_id": "ordinary", "action": "user.updated",
                              "details": {"changed_fields": ["full_name"]}})
    data = store.load_data()
    event = next(item for item in data["audit_events"] if item["id"] == "legacy")
    assert event["action"] == "USER_UPDATED"
    assert event["changes"] == {"changed_fields": ["full_name"]}
    assert "details" not in event
