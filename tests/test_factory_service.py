import pytest

from utils.factory_service import (
    FactoryAccessDeniedError,
    FactoryInactiveError,
    FactoryNotFoundError,
    FactoryService,
)


class Store:
    def __init__(self):
        self.factories = [
            {"id": "F1", "code": "F1", "name": "تهران", "display_name": "کارخانه تهران", "is_active": True, "operational_key": "Tehran"},
            {"id": "F2", "code": "F2", "name": "اراک", "is_active": False},
        ]

    def list_factories(self):
        return self.factories


ADMIN = {"system_role": "IT_ADMIN", "access_grants": []}
FINANCE = {"system_role": "FINANCE_ECONOMIC_ADMIN", "access_grants": []}
USER = {"system_role": "USER", "access_grants": [{
    "scope_type": "FACTORY", "factory_id": "F1", "module": "product", "permissions": ["READ"]
}]}


def test_admin_peers_see_every_active_factory_and_public_contract_is_minimal():
    service = FactoryService(Store())
    expected = [{"id": "F1", "code": "F1", "name": "کارخانه تهران"}]
    assert service.get_accessible_factories(ADMIN, "product") == expected
    assert service.get_accessible_factories(FINANCE, "product") == expected
    assert service.operational_key("F1") == "Tehran"


def test_user_access_is_explicit_module_specific_and_defaults_to_deny():
    service = FactoryService(Store())
    assert [item["id"] for item in service.get_accessible_factories(USER, "product")] == ["F1"]
    assert service.get_accessible_factories(USER, "cost_calculation") == []
    with pytest.raises(FactoryAccessDeniedError):
        service.require_access("F1", USER, "cost_calculation")


def test_unknown_and_inactive_factory_ids_fail_closed():
    service = FactoryService(Store())
    with pytest.raises(FactoryNotFoundError):
        service.require_access("unknown", ADMIN, "product")
    with pytest.raises(FactoryInactiveError):
        service.require_access("F2", ADMIN, "product")


def test_empty_registry_is_supported():
    store = Store()
    store.factories = []
    service = FactoryService(store)
    assert service.list_factories() == []
    assert service.get_accessible_factories(ADMIN, "product") == []
