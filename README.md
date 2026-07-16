# minicloud-markitdown-proxy

[![CI](https://github.com/andrelair-platform/minicloud-markitdown-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/andrelair-platform/minicloud-markitdown-proxy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Supply chain: cosign](https://img.shields.io/badge/supply%20chain-cosign%20signed-green)](https://github.com/sigstore/cosign)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)](https://fastapi.tiangolo.com)

> A lightweight document conversion proxy that exposes a single Docling-compatible endpoint. Routing is by file type: scanned images go to Docling for OCR, everything else is handled locally by MarkItDown. The API contract is identical to Docling's `/v1/convert/file` so any consumer (Open WebUI, rag-ingest) needs zero config changes.

---

## Table of Contents

- [Where this fits in the RAG pipeline](#where-this-fits-in-the-rag-pipeline)
- [Why a proxy instead of calling Docling directly](#why-a-proxy-instead-of-calling-docling-directly)
- [Architecture](#architecture)
- [Routing table](#routing-table)
- [API](#api)
- [Running locally](#running-locally)
- [CI/CD pipeline](#cicd-pipeline)
- [Environment variables](#environment-variables)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Related services](#related-services)
- [License](#license)

---

## Where this fits in the RAG pipeline

`markitdown-proxy` is the conversion layer shared by two consumers:

```
Open WebUI (paperclip upload)  ──┐
                                  ├──→  markitdown-proxy  ──→  Markdown
rag-ingest  (POST /ingest)     ──┘
                                            │
                            ┌───────────────┴───────────────┐
                            ▼                               ▼
                    Docling (port 5001)            MarkItDown (in-pod)
                  scanned images only         PDFs, Office, HTML, text
```

Open WebUI's `DOCLING_SERVER_URL` env var points here. `rag-ingest` also calls it before chunking and embedding. Both get the same Markdown back, in the same response format.

---

## Why a proxy instead of calling Docling directly

Docling is a powerful layout analysis tool built for scanned documents — but it comes with a cost: the CPU image is 4.4 GB and running it on a text-based PDF triggers a full layout analysis pipeline that uses several hundred MB of memory per page.

The platform's documents are mostly machine-generated PDFs (contracts, regulatory filings) and Office files. Running all of them through Docling would:
- Exhaust memory on a CPU-only cluster
- Add 10–30 seconds of latency per document for no quality gain

The proxy solves this by routing only scanned images (where OCR is genuinely needed) to Docling, and handling everything else locally with MarkItDown (which uses PyMuPDF for PDFs — fast, low-memory, accurate on text-based files). Docling's API contract is preserved for both paths so neither consumer needs to know which backend ran.

---

## Architecture

```
POST /v1/convert/file
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│                   markitdown-proxy                        │
│  FastAPI · python:3.12-slim · UID 1000 · port 8000        │
│                                                           │
│  Extension check                                          │
│    .png .jpg .jpeg .tiff .bmp .gif .webp                  │
│        └──→  proxy to Docling :5001  (layout + OCR)       │
│                                                           │
│    .pdf .docx .xlsx .pptx .html .csv .txt .md             │
│        └──→  MarkItDown (in-pod, PyMuPDF for PDF)         │
│                                                           │
│  Response normalised to Docling format:                   │
│    {"document": {"md_content": "<markdown string>"}}      │
└───────────────────────────────────────────────────────────┘
        │                          │
        ▼                          ▼
Docling service             MarkItDown[all]
ai namespace · port 5001    python library in this pod
ghcr.io/docling-project/
docling-serve-cpu:v1.26.0
```

**Docling is a separate deployment** — `ghcr.io/docling-project/docling-serve-cpu:v1.26.0` running as its own pod in the `ai` namespace. This service only proxies to it for image files. For all other formats, conversion happens inside the `markitdown-proxy` pod itself with no network hop.

---

## Routing table

| Extension | Backend | Reason |
|---|---|---|
| `.png` `.jpg` `.jpeg` `.tiff` `.bmp` `.gif` `.webp` | Docling (OCR) | Scanned images require layout analysis + OCR |
| `.pdf` | MarkItDown (PyMuPDF) | Text-based PDFs — fast, accurate, avoids Docling memory overhead |
| `.docx` `.xlsx` `.pptx` | MarkItDown | Office format parsing |
| `.html` `.csv` | MarkItDown | Structured text formats |
| `.txt` `.md` | MarkItDown | Passthrough |

---

## API

### `POST /v1/convert/file`

Convert a document to Markdown. The endpoint path and response format are identical to Docling's API so any consumer using `DOCLING_SERVER_URL` works without changes.

```
Content-Type: multipart/form-data

file   required   Document to convert
```

**Response (200):**

```json
{
  "document": {
    "md_content": "## Article 3 — Garanties incluses\n\nLa présente police garantit..."
  }
}
```

**Error responses:**

| Code | Cause |
|---|---|
| `502` | Docling backend unreachable or returned an error (image files only) |
| `422` | MarkItDown conversion failed (corrupt or unsupported file) |

### `GET /health`

Returns `{"status": "ok"}`. Used by Kubernetes liveness probe.

### `GET /ready`

Returns `{"status": "ready"}`. Used by Kubernetes readiness probe.

---

## Running locally

The only external dependency is Docling — needed only for image files. For everything else the service runs fully standalone.

```bash
# Install dependencies
pip install "fastapi==0.115.6" "uvicorn[standard]==0.32.1" \
            "httpx==0.27.2" "markitdown[all]" "python-multipart==0.0.12"

# Run (Docling URL is optional — only needed if you're converting images)
DOCLING_URL=http://localhost:5001 uvicorn main:app --reload --port 8000

# Test with a PDF
curl -s -X POST http://localhost:8000/v1/convert/file \
  -F "file=@/path/to/document.pdf" | python3 -m json.tool

# Test health
curl http://localhost:8000/health
```

---

## CI/CD pipeline

Every push to `main` triggers `.github/workflows/ci.yml`:

```
push to main
    │
    ├─ 1. Connect to Tailscale (OAuth — TS_OAUTH_CLIENT_ID / TS_OAUTH_SECRET)
    ├─ 2. Trust minicloud CA (raw PEM — no base64 decode)
    ├─ 3. docker build → push to harbor.10.0.0.200.nip.io/library/markitdown-proxy:<sha>-amd64
    ├─ 4. Trivy scan — fails on unfixed CRITICAL CVEs
    ├─ 5. cosign sign (keyless — GitHub OIDC → Sigstore Fulcio)
    └─ 6. GPG-signed commit to minicloud-gitops bumping manifests/ai/10-markitdown-proxy.yaml
              └─ ArgoCD webhook → rolling update in ai namespace
```

**Branch behaviour:**

| Branch | Image tag | Cosign signed | GitOps bump |
|---|---|---|---|
| `main` | `<sha>-amd64` | yes | yes — `manifests/ai/10-markitdown-proxy.yaml` |
| `staging` | `staging-<sha>-amd64` | yes | no |
| `dev` | `dev-<sha>-amd64` | no | no |

**Required repository secrets:**

All 7 secrets are **org-level on `andrelair-platform`** (visibility: all). New repos inherit them automatically — no per-repo setup needed.

| Secret | Purpose |
|---|---|
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID — joins tailnet as `tag:ci` |
| `TS_OAUTH_SECRET` | Tailscale OAuth secret |
| `MINICLOUD_CA_CERT` | Self-signed CA PEM — lets Docker and cosign trust Harbor TLS |
| `HARBOR_USER` | Harbor registry username |
| `HARBOR_PASSWORD` | Harbor registry password |
| `GITOPS_TOKEN` | GitHub PAT (`repo` scope) for committing to `minicloud-gitops` |
| `GPG_PRIVATE_KEY` | Armored GPG private key for signing gitops commits (key `FD6D39D681DEFA34`) |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DOCLING_URL` | no | `http://docling.ai.svc.cluster.local:5001` | Docling service URL — only called for image files |

No secrets required. The proxy itself holds no credentials.

---

## Security

- **Non-root runtime** — image runs as UID 1000 (`appuser`), no shell
- **Supply chain** — every `main` image is Cosign-signed (keyless) and the gitops bump commit is GPG-signed
- **Network isolation** — the `ai` namespace has default-deny ingress + egress NetworkPolicies; markitdown-proxy is reachable only from `rag-ingest` and `open-webui` pods within the cluster; it has no public ingress
- **No credentials** — this service handles only file content; it holds no API keys, database passwords, or tokens
- **GitOps delivery** — no direct `kubectl apply`; all deploys go through ArgoCD with audit trail

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `POST /v1/convert/file` returns 502 | Docling pod unreachable (image files only) | Check `kubectl get pods -n ai -l app=docling`; port-forward Docling and test `GET /health` |
| Response `md_content` is empty for a PDF | PyMuPDF extracted no text — scanned/image-only PDF | If the PDF is scanned, ensure the file extension matches an image type so routing goes to Docling |
| 422 for a normally-supported format | MarkItDown raised a conversion error on a corrupt file | Check pod logs: `kubectl logs -n ai -l app=markitdown-proxy`; re-run with a known-good file to isolate |
| Open WebUI "document upload" fails | `DOCLING_SERVER_URL` env var pointing at wrong service | Verify the env var in the running pod points to `http://markitdown-proxy.ai.svc.cluster.local:8000` |
| CI fails: Harbor push rejected | Runner not on Tailscale tailnet | Ensure Tailscale OAuth step runs before Docker login |

---

## Related services

| Service | Role |
|---|---|
| [`minicloud-rag-ingest`](https://github.com/andrelair-platform/minicloud-rag-ingest) | Calls this proxy as the first step of the ingestion pipeline |
| `docling` (in-cluster, `ai` namespace) | OCR backend for scanned images — `ghcr.io/docling-project/docling-serve-cpu:v1.26.0` |
| `open-webui` | Points `DOCLING_SERVER_URL` here for paperclip document uploads |

---

## License

[MIT](LICENSE) © andrelair-platform
