# Frontend contract

`openapi.json` in this directory is the frozen API contract from Week 2. The
frontend builds against it; the mock server serves it.

Regenerate after any router change and commit the diff in the same PR:

```bash
make api                                             # in one terminal
curl -s localhost:8000/openapi.json | python -m json.tool > docs/api/openapi.json
```

A diff here that nobody asked for means someone changed the contract by accident.
