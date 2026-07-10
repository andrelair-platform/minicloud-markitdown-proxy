# Contributing

## Branch strategy

| Branch | Protection | CI output | GitOps update |
|---|---|---|---|
| `main` | PR required + GPG-signed commits | `<sha>-amd64` — cosign-signed | bumps `manifests/ai/10-markitdown-proxy.yaml` |
| `staging` | PR required | `staging-<sha>-amd64` — cosign-signed | none |
| `dev` | open push | `dev-<sha>-amd64` | none |

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add .epub support via MarkItDown
fix: handle missing file extension gracefully
perf: increase httpx timeout for large image OCR
ci: pin cosign installer to v3.5
chore: bump markitdown to 0.5
```

## Dev workflow

```bash
pip install "fastapi==0.115.6" "uvicorn[standard]==0.32.1" \
            "httpx==0.27.2" "markitdown[all]" "python-multipart==0.0.12"

# Run — Docling URL only needed for image file testing
DOCLING_URL=http://localhost:5001 uvicorn main:app --reload --port 8000

# Test
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/v1/convert/file \
  -F "file=@/path/to/test.pdf" | python3 -m json.tool
```

## PR checklist

- [ ] `GET /health` returns 200 locally
- [ ] `POST /v1/convert/file` tested with at least one PDF and one Office file
- [ ] Response format is `{"document": {"md_content": "..."}}` for all file types
- [ ] No secrets or credentials added to any file
- [ ] If routing logic changed: note which file types are affected and whether Docling is now called for new formats
- [ ] Commit messages follow Conventional Commits

## Code standards

- Keep `main.py` as a single file — the service is intentionally minimal
- The response format must always match Docling's `{"document": {"md_content": "..."}}` — Open WebUI and rag-ingest both depend on this contract
- No Co-Authored-By lines — commits represent the owner's portfolio work
