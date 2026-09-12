"""Read-only Excel exchange export for canonical Profile JSON data.

Excel is deliberately a generated exchange artifact, never a runtime store.
Import is not enabled in Phase 11.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from utils.module_registry import MODULE_LABELS, MODULE_REGISTRY
from utils.profile_access_manager import permissions_to_level
from utils.profile_authorization import USER, get_effective_level, is_top_level_admin


EXPORT_SCHEMA_VERSION = "profile-exchange-v1"
SHEET_NAMES = ("Users", "Factories", "AccessGrants", "AuditEvents", "Metadata")
FORBIDDEN_EXCHANGE_FIELD_PARTS = (
    "password", "credential", "secret", "token", "session", "authorization", "cookie",
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_timestamp(value):
    return value if isinstance(value, str) else None


def _password_status(user):
    if user.get("must_change_password") or not user.get("password_hash"):
        return "RESET_REQUIRED"
    return "SET"


def _audit_change_summary(event):
    changes = event.get("changes")
    if not isinstance(changes, dict):
        return None
    grants = changes.get("grants")
    if isinstance(grants, list):
        safe = [
            {
                "scope_type": item.get("scope_type"),
                "factory_id": item.get("factory_id"),
                "module_id": item.get("module_id"),
                "before": item.get("before"),
                "after": item.get("after"),
            }
            for item in grants if isinstance(item, dict)
        ]
        return json.dumps(safe, ensure_ascii=False, sort_keys=True)
    fields = changes.get("changed_fields")
    if isinstance(fields, list) and all(isinstance(item, str) for item in fields):
        safe_fields = [
            item for item in fields
            if not any(part in item.casefold() for part in FORBIDDEN_EXCHANGE_FIELD_PARTS)
        ]
        return ", ".join(safe_fields) or None
    # Other audit details are intentionally excluded from the exchange layer.
    return None


def _access_rows(data):
    rows = []
    for user in data["users"]:
        if is_top_level_admin(user):
            continue
        explicit = {
            (grant["scope_type"], grant["factory_id"], grant["module"]): grant
            for grant in user.get("access_grants", [])
        }
        keys = set(explicit)
        if user.get("system_role") == USER and user.get("is_active", False):
            keys.add(("GLOBAL", None, "desk"))
        for scope_type, factory_id, module_id in sorted(
            keys, key=lambda item: (item[0], item[1] or "", item[2])
        ):
            grant = explicit.get((scope_type, factory_id, module_id))
            explicit_level = permissions_to_level(grant["permissions"]) if grant else "NONE"
            effective_level = get_effective_level(
                user, module_id, factory_id, scope_type=scope_type
            )
            policy_source = (
                "MANDATORY_DESK_MINIMUM"
                if module_id == "desk" and grant is None and effective_level == "READ"
                else "EXPLICIT_GRANT"
            )
            rows.append((
                user["id"], scope_type, factory_id, module_id,
                explicit_level, effective_level, policy_source,
            ))
    return rows


def _column_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell_xml(reference, value, *, header=False):
    style = ' s="1"' if header else ""
    if value is None:
        return f'<c r="{reference}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"{style}><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    text = escape(str(value))
    preserve = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f'<c r="{reference}" t="inlineStr"{style}><is><t{preserve}>{text}</t></is></c>'


def _sheet_xml(headers, rows):
    all_rows = [tuple(headers), *[tuple(row) for row in rows]]
    row_xml = []
    widths = [len(str(value)) if value is not None else 0 for value in headers]
    for row_number, row in enumerate(all_rows, start=1):
        cells = []
        for column_number, value in enumerate(row, start=1):
            if column_number <= len(widths) and value is not None:
                widths[column_number - 1] = max(widths[column_number - 1], len(str(value)))
            reference = f"{_column_name(column_number)}{row_number}"
            cells.append(_cell_xml(reference, value, header=row_number == 1))
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{min(width + 2, 48)}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    last = f"{_column_name(len(headers))}{len(all_rows)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetViews><sheetView workbookViewId="0" rightToLeft="1"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{columns}</cols><sheetData>{"".join(row_xml)}</sheetData>'
        f'<autoFilter ref="A1:{last}"/></worksheet>'
    )


def _xlsx_bytes(sheet_specs):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(sheet_specs) + 1)
        )
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + overrides + '</Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheets = "".join(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>' for index, (name, _, _) in enumerate(sheet_specs, start=1))
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + sheets + '</sheets></workbook>')
        relationships = "".join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(sheet_specs) + 1))
        relationships += f'<Relationship Id="rId{len(sheet_specs) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + relationships + '</Relationships>')
        archive.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font/><font><b/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs></styleSheet>')
        for index, (_, headers, rows) in enumerate(sheet_specs, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(headers, rows))
    return output.getvalue()

def build_profile_exchange_workbook(data, *, generated_at=None):
    """Build a workbook from one already-locked canonical snapshot."""
    generated_at = generated_at or _utc_now()
    sheets = []

    sheets.append(("Users", (
        "UserId", "FullName", "Email", "SystemRole", "JobTitle", "IsActive",
        "CreatedAt", "UpdatedAt", "LastLoginAt", "PasswordStatus", "AccessMode",
    ), [(
        user["id"], user.get("full_name"), user.get("email"), user.get("system_role"),
        user.get("job_title"), bool(user.get("is_active")),
        _safe_timestamp(user.get("created_at")), _safe_timestamp(user.get("updated_at")),
        _safe_timestamp(user.get("last_login_at")), _password_status(user),
        "IMPLICIT_FULL_ACCESS" if is_top_level_admin(user) else "EXPLICIT_GRANTS",
    ) for user in data["users"]]))

    sheets.append(("Factories", (
        "FactoryId", "Code", "Name", "Location", "Status", "CreatedAt", "UpdatedAt",
    ), [(
        factory["id"], factory.get("code"), factory.get("display_name") or factory.get("name"),
        factory.get("location"), "ACTIVE" if factory.get("is_active", True) else "INACTIVE",
        _safe_timestamp(factory.get("created_at")), _safe_timestamp(factory.get("updated_at")),
    ) for factory in data["factories"]]))

    sheets.append(("AccessGrants", (
        "UserId", "ScopeType", "FactoryId", "ModuleId", "ExplicitAccessLevel",
        "EffectiveAccessLevel", "PolicySource",
    ), _access_rows(data)))

    sheets.append(("AuditEvents", (
        "AuditEventId", "OccurredAt", "ActorUserId", "TargetType", "TargetId",
        "Action", "FactoryId", "ModuleId", "ModuleLabelFa", "ChangeSummary",
    ), [(
        event.get("id"), _safe_timestamp(event.get("occurred_at")), event.get("actor_user_id"),
        event.get("target_type"), event.get("target_id"), event.get("action"),
        event.get("factory_id"), event.get("module_id"),
        MODULE_LABELS.get(event.get("module_id")), _audit_change_summary(event),
    ) for event in data["audit_events"]]))

    metadata_rows = [
        ("ExportSchemaVersion", EXPORT_SCHEMA_VERSION),
        ("CanonicalSchemaVersion", data["schema_version"]),
        ("CanonicalRevision", data["metadata"]["revision"]),
        ("GeneratedAtUtc", generated_at),
        ("RuntimeSource", "canonical JSON (read-only snapshot)"),
        ("ImportEnabled", False),
        ("TopLevelAccess", "implicit full access; not expanded into AccessGrants"),
        ("MandatoryDeskPolicy", "active USER effective minimum READ"),
    ]
    metadata_rows.extend(
        (f"GrantableModule.{index}.Id", module["id"])
        for index, module in enumerate(MODULE_REGISTRY, start=1)
    )
    sheets.append(("Metadata", ("Key", "Value"), metadata_rows))
    return _xlsx_bytes(sheets)


def profile_exchange_bytes(store, *, generated_at=None):
    """Load one safe snapshot and serialize it without mutating canonical JSON."""
    data = store.load_data()
    return build_profile_exchange_workbook(data, generated_at=generated_at)
