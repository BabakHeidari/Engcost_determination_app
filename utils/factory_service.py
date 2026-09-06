"""Canonical factory registry and factory-context service.

Factory identity is read exclusively from ``ProfileDataStore``.  Operational
data files may still contain factory-specific configuration, but they are not
allowed to decide whether a factory exists or whether a user may use it.
"""

from __future__ import annotations

import copy

from utils.profile_authorization import can_access_module


class FactoryNotFoundError(LookupError):
    """The supplied stable factory ID is absent from the registry."""


class FactoryInactiveError(PermissionError):
    """The supplied factory cannot be selected for current work."""


class FactoryAccessDeniedError(PermissionError):
    """The current user has no matching explicit/effective access."""


class FactoryService:
    """Expose safe factory view models and fail-closed context validation."""

    def __init__(self, store):
        self.store = store

    def list_factories(self) -> list[dict]:
        return [self._public(factory, include_active=True) for factory in self.store.list_factories()]

    def list_active_factories(self) -> list[dict]:
        return [self._public(factory) for factory in self.store.list_factories() if factory.get("is_active", True)]

    def get_factory(self, factory_id: str) -> dict | None:
        if not isinstance(factory_id, str) or not factory_id:
            return None
        factory = next((item for item in self.store.list_factories() if item.get("id") == factory_id), None)
        return self._public(factory, include_active=True) if factory else None

    def factory_exists(self, factory_id: str) -> bool:
        return self.get_factory(factory_id) is not None

    def get_accessible_factories(
        self, user: dict, module: str, permission: str = "READ", *, active_only: bool = True
    ) -> list[dict]:
        factories = self.store.list_factories()
        return [
            self._public(factory, include_active=not active_only)
            for factory in factories
            if (not active_only or factory.get("is_active", True))
            and can_access_module(user, module, factory.get("id"), permission)
        ]

    def get_selectable_factories(self, user: dict, context: str) -> list[dict]:
        """Return active options for a known factory-scoped module context."""
        return self.get_accessible_factories(user, context, "READ", active_only=True)

    def require_access(
        self, factory_id: str, user: dict, module: str, permission: str = "READ", *, require_active: bool = True
    ) -> dict:
        factory = self.get_factory(factory_id)
        if factory is None:
            raise FactoryNotFoundError("کارخانه در رجیستری سامانه وجود ندارد.")
        if require_active and not factory.get("is_active", True):
            raise FactoryInactiveError("کارخانه غیرفعال است.")
        if not can_access_module(user, module, factory_id, permission):
            raise FactoryAccessDeniedError("دسترسی به این کارخانه مجاز نیست.")
        return factory

    def operational_key(self, factory: dict | str) -> str:
        """Resolve the legacy operational-data key only after registry validation."""
        factory_id = factory if isinstance(factory, str) else factory["id"]
        source = next((item for item in self.store.list_factories() if item.get("id") == factory_id), None)
        if source is None:
            raise FactoryNotFoundError("کارخانه در رجیستری سامانه وجود ندارد.")
        return source.get("operational_key") or source["id"]

    @staticmethod
    def _public(factory: dict, *, include_active: bool = False) -> dict:
        result = {
            "id": factory["id"],
            "code": factory["code"],
            "name": factory.get("display_name") or factory.get("name") or factory["code"],
        }
        if factory.get("location") is not None:
            result["location"] = copy.deepcopy(factory["location"])
        if include_active:
            result["is_active"] = factory.get("is_active", True)
        return result
