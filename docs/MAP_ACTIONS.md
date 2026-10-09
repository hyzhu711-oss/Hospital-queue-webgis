# Map-native actions

`contracts/map-actions.schema.json` defines the shared v1 actions: fit_bounds, highlight, filter, rank, compare, open_popup and fly_to. All hospital IDs must be in the verified final entities. The Python generator validates the schema and membership; the browser validates the entire action batch before mutating the map.

Leaflet and Cesium provide adapters for the same commands. Popups use DOM text rather than model HTML. Agent entities can be mapped even when the old user-scoped layer does not already contain them. Original map controls continue to use the legacy API. Result order becomes marker numbering; comparison highlights the selected hospitals and the answer exposes same-window metrics.

The Agent panel is hidden when `AGENT_SERVICE_URL` is unset. Set this on Node to the FastAPI URL to enable the panel and same-origin POST/SSE proxy. `AGENT_API_TOKEN` is sent only by the backend. Only the opaque session ID is retained in sessionStorage. Facts and map commands are queried again after navigation; old result replay was removed because browser storage is user-controlled and may contain stale data.

Browser location is explicitly requested by the location button. No default London coordinate is substituted for the user. Browser and server location reuse expires after five minutes. Hospital referents remain usable for the 30-minute session TTL and are resolved through fresh detail/statistics tools. A named follow-up does not extend a stale location's lifetime.

Browser checks exercised actual Leaflet lookup/popup/details, Cesium comparison/highlighting/flyTo, and invalid ordinal handling. A synthetic observation submitted through the original Leaflet report form (cleanliness 4.5, observed wait 8 minutes) appeared in history and a fresh Agent 24-hour aggregation with one report. This used an owned localhost memory fixture. Screenshots are saved as `docs/screenshots/agent-leaflet.jpg` and `agent-cesium.jpg`.

External OpenStreetMap tiles were blocked at one Leaflet zoom in this environment; local markers and tool execution remained functional. Location permission acceptance and external map-provider availability remain environment-dependent. Responsive breakpoints were not specifically tested.
