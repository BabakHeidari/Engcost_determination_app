# Profile module current state

## Phase 12 final state

Phase 12 hardening and full regression are complete. The exact seven-module
registry, peer top-level roles, hierarchical grants, mandatory active-user Desk
READ baseline, dynamic canonical factory registry, Visual Access Manager,
friendly Persian HTML/JSON 403 split, bounded real audit, and exchange-only
Excel behavior remain the current contracts. Runtime secrets are environment
configured, debug/demo activation is explicit, and operators now have a
validated newest-backup recovery command. Deployment boundaries and the full
verification procedure are documented in
`docs/phase-12-hardening-and-operations.md`.

As of Phase 6.5, Profile identity and authorization are read from the single
version-2 JSON store through `ProfileDataStore`. Authentication reloads active
users by stable ID. The Profile page displays system role and job title
separately, renders a single full-access state for either top-level admin, and
groups explicit grants for ordinary users.

The only roles with security meaning are `IT_ADMIN`,
`FINANCE_ECONOMIC_ADMIN`, and `USER`. Ordinary users fail closed without an
explicit grant. The Add User operation is implemented; broader editing,
activation, administrator reset and permission-edit operations remain disabled
until Phase 7. Phase 6.7 factory creation is complete: either top-level role can
create an active canonical factory with identical authority, while ordinary
users cannot. The factory and secret-free audit event are committed atomically,
and the returned registry record is immediately available to Add User grants.

An existing schema-v1 canonical file is upgraded automatically on its first
read/login using the locked, backed-up, atomic migration. The standalone
migration command remains available for proactive operational cutovers.

## Phase 7 account management

Phase 7 adds administrator user editing, canonical access-grant replacement, role transitions, activation/deactivation, optimistic revision checks, and a separate administrator password-reset operation. Both top-level roles have identical authority; sensitive changes to a top-level account require a different top-level administrator, and no operation may remove the final active top-level administrator. See `docs/profile-user-management.md` for details.
