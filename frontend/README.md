# Frontend Dataset Viewer

Standalone frontend server for browsing connector output artifacts without changing backend ingestion code.

## What It Does

- Reads benchmark outputs from `datasets/cybersecurity_records` by default.
- Displays benchmarks, sources, statuses, counts, and latest snapshot files.
- Handles missing metadata gracefully (for example while `pentester_land` is still streaming).
- Provides paginated record browsing with search.
- Opens full normalized records and source-native `raw` payload trees.
- Keeps long text readable via expandable panels.

## Folder Layout

- `frontend/server.py`: lightweight API and static file server.
- `frontend/static/index.html`: application shell.
- `frontend/static/styles.css`: visual system and responsive layout.
- `frontend/static/app.js`: data loading and UI behavior.

## Run

From project root:

```bash
python frontend/server.py
```

Then open:

- `http://127.0.0.1:8710`

### Custom Datasets Directory

```bash
python frontend/server.py --datasets-root /path/to/datasets/cybersecurity_records
```

## API Endpoints

- `GET /api/health`
- `GET /api/benchmarks`
- `GET /api/benchmarks/<benchmark>/sources`
- `GET /api/benchmarks/<benchmark>/sources/<source>/records?offset=0&limit=50&q=`
- `GET /api/benchmarks/<benchmark>/sources/<source>/record?index=0`

## Notes

- This viewer is intentionally read-only.
- It does not modify ingestion outputs.
- For very large datasets, search is simple full-text matching and may take longer than basic pagination.
