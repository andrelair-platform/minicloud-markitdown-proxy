## Summary

<!-- What does this PR change and why? 2-3 sentences. -->

## Type of change

- [ ] Bug fix
- [ ] New file format support
- [ ] Routing logic change (what goes to Docling vs MarkItDown)
- [ ] CI / tooling
- [ ] Documentation

## Checklist

- [ ] `GET /health` returns 200 locally
- [ ] `POST /v1/convert/file` tested with at least one real document
- [ ] Response format is always `{"document": {"md_content": "..."}}` for all paths
- [ ] No secrets or credentials in any file
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] If routing changed: both `rag-ingest` and `open-webui` consumers considered

## Related issues

<!-- Closes #<number> -->
