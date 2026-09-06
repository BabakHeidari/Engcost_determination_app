# Profile module current state

As of Phase 6.5, Profile identity and authorization are read from the single
version-2 JSON store through `ProfileDataStore`. Authentication reloads active
users by stable ID. The Profile page displays system role and job title
separately, renders a single full-access state for either top-level admin, and
groups explicit grants for ordinary users.

The only roles with security meaning are `IT_ADMIN`,
`FINANCE_ECONOMIC_ADMIN`, and `USER`. Ordinary users fail closed without an
explicit grant. The Add User operation is implemented; broader editing,
activation, administrator reset and permission-edit operations remain disabled
until Phase 7.

An existing schema-v1 canonical file is upgraded automatically on its first
read/login using the locked, backed-up, atomic migration. The standalone
migration command remains available for proactive operational cutovers.
