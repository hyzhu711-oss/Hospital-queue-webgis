# Spatial tool contract v1

`GET /api/tools/catalog` is the canonical JSON Schema catalog. `POST /api/tools/:name` executes one of the eight read-only tools listed in the P0 audit. Schemas forbid extra properties and type coercion. Set `GIS_TOOLS_TOKEN` for authenticated server-to-server access; existing demo APIs retain their original contract.

Coordinates are WGS84, distances are unrounded metres, time windows are UTC `[start,end)` with explicit offsets, at most 366 days. Searches return `complete`; incomplete candidates must not be treated as the entire search space. PostgreSQL executes each tool in a repeatable-read, read-only transaction, with a five-second statement timeout. Separate HTTP calls do not share a database snapshot.

New report properties `cleanlinessScore` (1–5) and `queueWaitMinutes` (0–1440) are optional. Historical values stay null. Cleanliness text is never converted into a score. Queue severity is the ordinal `sort_order` 1–5, excluding Unknown=0; it is not waiting minutes. Actual reported minutes are aggregated separately. Both aggregates retain sample counts and bounded contributing report IDs.

Ranking `weighted-cost-v1` minimizes `wd * min(distance_m/scale,1) + wq * (average_queue_severity-1)/4 + wc * (5-average_cleanliness)/4`. Weights sum to one; scale is the requested radius or 5000m. Missing metrics with positive weights exclude a candidate. Explicit cleanliness/queue/wait/radius filters precede top-k. Ties break by hospital ID. Scores represent the documented policy over crowdsourced data, not medical quality.

The migration runner records checksums, applies each new migration in a transaction, and adopts an established legacy schema without replaying seed upserts. Test fresh and existing deployments before applying to a managed database. No production migration was executed during development.

P1 local validation: 39 tests passed (the original 18 included). Real PostGIS tests in `tests/postgis.test.js` require `TEST_DATABASE_URL` pointing to the isolated `queuelens_test` database; these are skipped when unavailable. Local memory and SQL-binding tests do not prove real SQL execution. CI must run the PostGIS tests before deployment.
