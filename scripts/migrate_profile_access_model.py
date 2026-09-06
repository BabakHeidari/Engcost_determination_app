"""One-time locked migration from Profile schema v1 to canonical access model v2."""
import argparse
from pathlib import Path

from scripts.bootstrap_it_admin import store_path
from utils.profile_store import ProfileDataStore


def main():
    parser = argparse.ArgumentParser(description="Migrate Profile authorization to system_role/access_grants")
    parser.add_argument("path", nargs="?", type=Path, default=store_path())
    args = parser.parse_args()
    result = ProfileDataStore(args.path).migrate_access_model()
    if not result["migrated"]:
        print("Access model is already current.")
        return
    reviews = result["review_user_ids"]
    print(f"Access-model migration completed; manual review required for {len(reviews)} user(s).")
    if reviews:
        print("Review user IDs: " + ", ".join(reviews))


if __name__ == "__main__":
    main()
