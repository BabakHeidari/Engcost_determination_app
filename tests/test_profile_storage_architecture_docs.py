from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs/profile-json-storage-architecture.md"
IMPLEMENTATION_PLAN = ROOT / "docs/profile-module-implementation-plan.md"


def test_profile_storage_architecture_covers_required_decisions():
    document = ARCHITECTURE.read_text(encoding="utf-8")

    required_sections = [
        "## 1. Existing storage mechanism",
        "## 2. Existing authentication flow",
        "## 3. Existing user-file format",
        "## 4. Canonical file decision",
        "## 5. Proposed JSON schema",
        "## 6. User schema",
        "## 7. Factory schema",
        "## 8. Permission schema",
        "## 9. Audit schema",
        "## 10. Password-hashing strategy",
        "## 11. Existing-user migration strategy",
        "## 12. File placement and permissions",
        "## 13. Locking strategy",
        "## 14. Atomic-write strategy",
        "## 15. Backup and recovery strategy",
        "## 16. Excel alternative analysis",
        "## 17. File-by-file implementation plan",
        "## 18. Open product decisions",
    ]
    for section in required_sections:
        assert section in document

    assert "Data/Overall/auth_data.xlsx" in document
    assert "APP_DATA_FILE" in document
    assert "password_hash" in document
    assert "werkzeug.security.generate_password_hash" in document
    assert "os.replace" in document


def test_phase_plan_preserves_documentation_only_stop_boundary():
    plan = IMPLEMENTATION_PLAN.read_text(encoding="utf-8")

    assert "Phase 2 — JSON storage architecture | Complete in documentation" in plan
    assert "Phase 3 and later | **Not started**" in plan
    assert "No canonical file" in plan

