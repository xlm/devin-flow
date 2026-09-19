# Playbooks

Each `<name>.md` is the body of a Devin Playbook, uploaded verbatim, so a
body must not reference repository files. The sibling
`<name>.schema.json`, when present, is attached as the playbook's
`structured_output_schema`. `uv run sync-playbooks` upserts every pair by
the playbook title (the first heading).

## Syncing

`uv run sync-playbooks` uploads every playbook to Devin. It requires
`DEVIN_API_TOKEN` (a service user with the ManageOrgPlaybooks permission)
and `DEVIN_ORG_ID`, via the environment or `.env`. It prints
`created <file>` or `updated <file>` per file and exits non-zero on
failure. `README.md` is skipped, titles must be unique across files, and
a macro already set on a playbook in the Devin UI is preserved on update.
