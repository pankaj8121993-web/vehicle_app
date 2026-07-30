# Backend dependency resolution

**Workstream:** UX-R1  
**Python:** 3.11.15  
**Production accessed:** No

> **Update (UX-R1, P3-09):** `emergentintegrations` (and, transitively,
> `litellm`) is **not imported by any backend module or test** — `import server`
> succeeds without it. The pinned `emergentintegrations==0.2.0` is published only
> on the hosting platform's private index, so public CI (PyPI-only) could not
> resolve it and the backend job failed before collection. It has been removed
> from `backend/requirements.txt`. The LiteLLM URL-fragment conflict described
> below is therefore moot; the section is retained for history.

## Original conflict and graph

`backend/requirements.txt` directly requested a hash-qualified LiteLLM wheel.
`emergentintegrations==0.2.0` requires the same `litellm==1.80.0` wheel through
the same URL without the fragment. Pip treats URL requirements with different
fragments as distinct candidates and returned `ResolutionImpossible`; this was
not a semantic version incompatibility.

```text
requirements.txt
├── emergentintegrations==0.2.0
│   ├── openai==1.99.9
│   └── litellm @ .../litellm-1.80.0-py3-none-any.whl
└── litellm @ .../litellm-1.80.0-py3-none-any.whl#sha256=...
```

## Resolution

The duplicate direct LiteLLM URL was removed. The pinned
`emergentintegrations==0.2.0` requirement remains and supplies its exact
LiteLLM 1.80.0 dependency. No package was unpinned or removed, and no unrelated
backend dependency changed.

Clean verification:

```bash
python3 -m venv /tmp/fleetflow-phase3-clean-venv
/tmp/fleetflow-phase3-clean-venv/bin/python -m pip install --upgrade pip
/tmp/fleetflow-phase3-clean-venv/bin/pip install -r backend/requirements.txt
/tmp/fleetflow-phase3-clean-venv/bin/pip check
```

Result: clean installation passed; `pip check` reported no broken requirements.
Final relevant versions are emergentintegrations 0.2.0, LiteLLM 1.80.0 and
OpenAI 1.99.9.

Rollback is restoring the removed direct URL, which also restores the resolver
failure. Remaining limitation: the LiteLLM artifact is hosted outside PyPI, so
installation requires access to that immutable artifact URL.

