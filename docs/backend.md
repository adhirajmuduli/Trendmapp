# Backend (Python)

## /

### app.py
- **Purpose**
  - Quart app setup, config, static serving, blueprint registration, and core API routes.
- **Key functions/routes**
  - `index()` GET `/` renders `templates/index.html`.
  - `serve_geojson()` GET `/static/data/export.geojson` static GeoJSON passthrough.
  - `upload_data()` POST `/upload` handles CSV/Excel upload, saves to `uploads/`, reshapes/validates data, stores summary in `session`, returns JSON sample + stats (@app.py#116-310).
  - `generate_heatmap()` POST `/generate-heatmap` generates base64 PNG heatmaps for provided timestamps using IDW or KDE over lagoon bounds, returns `{ images: {ts: base64}, global_min, global_max }` (@app.py#340-566).
  - `animation_page()` GET `/animate` serves `templates/animation.html` (@app.py#567-570).
  - Error handlers `not_found_error`, `internal_error` (@app.py#573-580).
  - `upload_boundary()` POST `/upload-boundary` saves GeoJSON to `static/data/uploads/`, stores path in `session['boundary_geojson']`, returns URL path (@app.py#585-606).
  - `serve_legend()` GET `/legend/<timestamp>.png` returns PNG colorbar using provided query `min`, `max`, `colormap` (@app.py#608-653).
  - `polygon_to_path(polygon)` helper converts Shapely polygons to Matplotlib Paths (@app.py#325-338).
  - `allowed_file`, `clean_and_validate_data` helpers for upload processing (@app.py#59-101).
- **Inputs / Outputs / Side effects**
  - Inputs: multipart file uploads (`file`); JSON payloads for heatmap gen including `data`, `bandwidth`, `timestamp_columns`, `global_min/max`, `method`, `colormap`, optional `boundary_path`.
  - Outputs: JSON responses; base64-encoded images; dynamically generated PNG (legend); rendered HTML pages.
  - Side effects: writes files to `uploads/` and `static/data/uploads/`; stores data and boundary path in `session`; reads `static/data/export.geojson` or uploaded boundary.
- **Assumptions / Constraints / TODOs**
  - Expects upload wide-format (first two columns lat/lon, rest timestamps) or long-format with `latitude, longitude, timestamp, value`.
  - Bandwidth in km converted to degrees for KDE/IDW; grid size fixed (400).
  - Uses `matplotlib` with `'Agg'` backend; heavy numeric libs required.
- **Cross-file dependencies**
  - Registers `routes.data_api` and `routes.animation_api` blueprints.
  - Uses `shapely` for geometry, `scikit-learn` KDE, `scipy.ndimage.gaussian_filter`.
  - Serves templates and static assets referenced by `static/js/app.js`.

### db.py
- **Purpose**
  - Async SQLAlchemy engine/session setup; ORM models; env parsing.
- **Key elements**
  - Loads `DATABASE_URL` from `.env` or `oink.env`; converts to `postgresql+asyncpg`; strips unsupported query params; sets SSL connect args based on `sslmode` (@db.py#11-47).
  - `Base`, `Station`, `Parameter`, `Measurement` models with uniqueness on `(station_id, parameter_id, sampled_at)` (@db.py#71-99).
  - `get_db_session()` async context manager validates connection, yields session, commits/rollbacks (@db.py#104-119).
- **Inputs / Outputs / Side effects**
  - Inputs: `DATABASE_URL` env var.
  - Outputs: N/A (runtime DB connectivity).
  - Side effects: DB connections, commits/rollbacks.
- **Assumptions / Constraints**
  - Requires PostgreSQL accessible via asyncpg; pool config set (size, recycle, pre_ping).
- **Cross-file dependencies**
  - Imported by `routes/data_api.py`, `utils/animation_generator.py` (for ORM symbols in type hints), and `utils/animation_worker.py`.

## /routes

### routes/data_api.py
- **Purpose**
  - Data entry UI route and REST APIs for parameters, timestamps, table view, upsert, and deletion.
- **Key routes**
  - GET `/data-entry` serves `templates/data-entry.html` (@routes/data_api.py#20-26).
  - GET `/api/parameters` list parameter names (@routes/data_api.py#30-40).
  - POST `/api/parameters` add new parameter; 400 on duplicate (@routes/data_api.py#41-56).
  - GET `/api/timestamps` list distinct ISO timestamps descending (@routes/data_api.py#60-75).
  - GET `/api/table` pivot wide table: index `[station_id, latitude, longitude]`, columns `parameter_date`, values `value` (@routes/data_api.py#79-137).
  - POST `/api/table` upsert rows: creates parameters/stations if missing; on-conflict update by `(station_id, parameter_id, sampled_at)`; returns counts (@routes/data_api.py#138-221).
  - DELETE `/api/measurement` delete a measurement by lat/lon, parameter, timestamp (@routes/data_api.py#226-274).
  - `@bp.before_app_serving` `_init_async_db()` initializes tables once (@routes/data_api.py#280-293).
- **Inputs / Outputs / Side effects**
  - Inputs: JSON rows for upsert; lat/lon/parameter/timestamp for delete.
  - Outputs: JSON arrays (parameters, timestamps, pivot rows) and status objects.
  - Side effects: Inserts/updates/deletes database rows; creates missing parameters/stations.
- **Assumptions / Constraints**
  - Timestamp handling formats to `%Y-%m-%d` in table view; expects ISO date strings for POST/DELETE parsing.
- **Cross-file dependencies**
  - Uses `db.get_db_session`, `db.init_db`, and ORM models.
  - Consumed by `static/js/data_entry.js` for CRUD and `templates/data-entry.html` UI.

### routes/animation_api.py
- **Purpose**
  - Exposes `/api/animate` to generate a spatiotemporal MP4 for uploaded file slices.
- **Key route**
  - POST `/api/animate`: validates payload keys; calls `utils.animation_generator.fetch_data_for_animation` and `generate_spatiotemporal_video`; returns MP4 via `send_file` (@routes/animation_api.py#9-45).
- **Inputs / Outputs / Side effects**
  - Inputs: JSON `{ parameter, start_date, end_date, fps, frames_per_transition, filename, [colormap], [boundary_path] }`.
  - Outputs: MP4 bytes as attachment; 404 if no data.
  - Side effects: Reads from `uploads/<filename>` and GeoJSON boundary; CPU-bound interpolation.
- **Assumptions / Constraints**
  - Dates parsed with `datetime.fromisoformat`; requires uploaded file present on disk.
- **Cross-file dependencies**
  - Uses `utils.animation_generator` functions.

## /utils

### utils/animation_generator.py
- **Purpose**
  - Data reshaping from uploaded CSV/Excel to long format, filtering by date; spatiotemporal interpolation and MP4 encoding in-memory.
- **Key functions**
  - `fetch_data_for_animation(parameter, start_date, end_date, filename)` reads `uploads/<filename>`, standardizes columns, melts wide→long if needed, enforces required columns, coerces types, filters by date, returns DataFrame (@utils/animation_generator.py#15-88).
  - `generate_spatiotemporal_video(df, fps, frames_per_transition, cmap, boundary_path)` performs RBF spatial interpolation per timestamp over 300×300 grid clipped to GeoJSON boundary; cubic temporal interpolation between fields; encodes MP4 via `imageio.mimsave`; returns bytes (@utils/animation_generator.py#90-165).
- **Inputs / Outputs / Side effects**
  - Inputs: DataFrame or CSV/Excel filename; parameters above.
  - Outputs: Filtered DataFrame; MP4 bytes.
  - Side effects: Reads boundary GeoJSON; CPU/memory intensive interpolation.
- **Assumptions / Constraints**
  - Requires ≥4 points per timestamp for RBF; at least two timestamps for animation; uses `shape` from GeoJSON; default boundary `static/data/export.geojson`.
- **Cross-file dependencies**
  - Called by `routes/animation_api.py`.

### utils/animation_worker.py
- **Purpose**
  - Async utility to load DB-backed measurements and generate an animation file via a helper.
- **Key function**
  - `generate_interpolated_video(parameter, start_date, end_date, fps, frames_per_transition, cmap)` queries DB for parameter/date range, converts to DataFrame, calls `generate_animation_video`, returns bytes (@utils/animation_worker.py#9-49).
- **Inputs / Outputs / Side effects**
  - Inputs: parameter string, datetime range, fps/frames, colormap.
  - Outputs: MP4 bytes read from a generated file path.
  - Side effects: DB queries; writes temporary MP4 to disk via downstream generator.
- **Assumptions / Constraints / TODOs**
  - Imports `from generate_video import generate_animation_video` but repository provides `utils/video_generator.py` defining `generate_animation_video`. This import likely broken/stale.
  - Not referenced by routes; appears unused.
- **Cross-file dependencies**
  - Intended to use `db.AsyncSessionLocal` and `utils/video_generator.py`.

### utils/video_generator.py
- **Purpose**
  - Alternate video generation pipeline using linear temporal interpolation and scatter plot frames written via OpenCV.
- **Key function**
  - `generate_animation_video(df, output_name="animation.mp4", fps=30, duration_seconds=10)` writes MP4 to `static/animations/`, drawing per-frame scatter over GeoJSON polygon background (@utils/video_generator.py#22-112).
- **Inputs / Outputs / Side effects**
  - Inputs: DataFrame with `[latitude, longitude, sampled_at, value]`, fps, duration.
  - Outputs: File path to MP4 (string).
  - Side effects: Ensures `static/animations/` exists; reads `static/data/export.geojson`; writes video file.
- **Assumptions / Constraints**
  - Uses GeoPandas and OpenCV; expects multiple timestamps per coordinate for temporal interpolation; no spatial interpolation (scatter-based).
- **Cross-file dependencies**
  - Intended to be called by `utils/animation_worker.py`.
