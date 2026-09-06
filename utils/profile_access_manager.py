"""Deterministic conversion between canonical grants and visual access levels."""

from utils.profile_authorization import MODULE_SCOPES, PERMISSION_LEVELS


def permissions_to_level(permissions):
    values = set(permissions or ())
    if "MODIFY" in values:
        return "MODIFY"
    if "WRITE" in values:
        return "WRITE"
    if "READ" in values:
        return "READ"
    return "NONE"


def grants_to_access_state(grants):
    state = {"global": {}, "factories": {}}
    for grant in grants or ():
        target = state["global"] if grant["scope_type"] == "GLOBAL" else state["factories"].setdefault(grant["factory_id"], {})
        current = permissions_to_level(grant.get("permissions"))
        previous = target.get(grant["module"], "NONE")
        levels = tuple(PERMISSION_LEVELS)
        target[grant["module"]] = max((previous, current), key=levels.index)
    return state


def access_state_to_grants(state):
    grants = []
    for module, level in sorted((state.get("global") or {}).items()):
        if level != "NONE":
            grants.append({"scope_type": "GLOBAL", "factory_id": None, "module": module,
                           "permissions": list(PERMISSION_LEVELS[level])})
    for factory_id, modules in sorted((state.get("factories") or {}).items()):
        for module, level in sorted(modules.items()):
            if level != "NONE":
                grants.append({"scope_type": "FACTORY", "factory_id": factory_id, "module": module,
                               "permissions": list(PERMISSION_LEVELS[level])})
    return grants
