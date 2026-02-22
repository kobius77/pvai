# AI Agent Instructions

## CRITICAL RULE: Database Schema Changes

Whenever you modify database tables, SQLAlchemy models, schema files, or Vanna training structures, you MUST verify if the `/api/backup` and `/api/restore` endpoints require updating.

### Backup/Restore Requirements

1. **Dynamic Extraction**: The backup endpoint must use dynamic SQL (e.g., `SELECT * FROM table_name`) - never hardcode column names. This ensures new columns are automatically included.

2. **Versioning**: Always update `SCHEMA_VERSION` in main.py when schema changes occur. The backup must include a `manifest.json` with the current schema version.

3. **Restore Validation**: The restore endpoint must:
   - Read manifest.json first
   - Abort if schema version doesn't match
   - Detect schema drift (missing tables/columns)

4. **Testing**: After any schema change, run the backup/restore tests to ensure round-trip compatibility.
