---
name: Bug report
about: Report a broken or unexpected behaviour
labels: bug
---

## Describe the bug

<!-- A clear description of what is broken. -->

## Steps to reproduce

1. POST /v1/convert/file with file type: '...'
2. See error: '...'

## Expected behaviour

<!-- What should have happened? -->

## Environment

| Field | Value |
|---|---|
| Image tag | <!-- from manifests/ai/10-markitdown-proxy.yaml --> |
| File format | <!-- .pdf / .docx / .png / ... --> |
| File size | |
| Routing path taken | <!-- MarkItDown or Docling --> |
| Docling pod status | <!-- kubectl get pods -n ai -l app=docling --> |

## Logs

<!-- kubectl logs -n ai -l app=markitdown-proxy --tail=50 -->
