# Playbooks

Each `<name>.md` is the body of a Devin Playbook, uploaded verbatim, so a
body must not reference repository files. The sibling
`<name>.schema.json`, when present, is attached as the playbook's
`structured_output_schema`. `uv run sync-playbooks` upserts every pair by
the playbook title (the first heading).
