# Local Quota for CodexBar

Display a quota exported by a local tool in the CodexBar menu bar. The plugin reads
`GET /v1/quota` from an explicitly approved `http://127.0.0.1:PORT` origin. Its card
shows used, limit, remaining, and the time the exporter observed the values.
Tested with the official macOS arm64 CodexBar v0.83.0 CLI.

## Install

1. Download [local-quota.js](./local-quota.js). In **CodexBar → Settings → Plugins → Install…**
   select the file, or copy it to `~/.config/codexbar/providers/`.
2. Start your exporter. For a quick test with synthetic values, run the optional
   Python 3 helper in this repository:

   ```sh
   python3 serve_quota.py --demo
   curl --noproxy '*' --fail http://127.0.0.1:8765/v1/quota
   ```

3. Set **Local origin** to `http://127.0.0.1:8765` (omit the route). Enable
   **Local Quota** and type that exact origin in CodexBar's network approval prompt.
   To test in an interactive terminal, run `codexbar plugins fetch local-quota --json`.
4. With **Merge Icons** enabled, select **Local Quota** and use **Current selection**
   as the icon source. The menu-bar number follows your used/remaining preference.
   The demo reports 25% used, 75% remaining and 75.00 USD available.

Stop the demo with Ctrl-C before starting a real exporter on that port.

## Supply your own data

Either implement the route directly or have a local tool atomically replace a
normalized JSON file and serve that one file:

```sh
python3 serve_quota.py --file /absolute/path/to/quota.json --port 8765
```

Example response (synthetic; replace the timestamp with the actual observation time):

```json
{"version":1,"observedAt":"2026-01-01T12:00:00Z","used":25,"limit":100,"currency":"USD"}
```

- `used` and `limit` are finite nonnegative numbers in the same unit. Currency is
  optional (three uppercase ASCII letters). A zero limit leaves the percentage
  unavailable; overage keeps the actual percentage and negative remaining amount.
- `observedAt` and optional `resetsAt` are UTC timestamps ending in Z, with optional
  1–3 fractional digits. Omit or null the reset when unknown. An elapsed reset,
  an observation older than **Maximum age** (15 minutes by default, configurable
  from 1 to 10080), or a clock more than 60 seconds ahead fails the refresh.
- The source observation appears in the details. CodexBar timestamps its own
  snapshot when it fetches. A failed refresh can leave the last good reading
  visible alongside the host's error.
- The optional helper reads one regular file, at most 64 KiB, on each request.
  It rejects final-component symlinks, extra JSON fields, unexpected Host headers
  and browser Origin requests. No request or response body is logged. Loopback is
  accessible to local processes; keep only quota fields in the feed. No browser,
  filesystem, secret or persistent-storage capability is requested by the plugin.
- Keep source-specific collection, account details, and authentication in your own
  exporter. Both the demo and integration test use synthetic data.

## Verify

```sh
python3 smoke.py /path/to/CodexBarCLI
```

On macOS this installs the plugin into an isolated temporary home, starts a
temporary loopback service, checks noninteractive access is denied before
approval, then drives the CLI approval prompt for that temporary origin. It
checks fresh/stale/recovered usage, overage, zero allocation, removed resets,
observation time and the helper's HTTP restrictions. No personal provider config
or saved approval is used.

To remove the plugin, use **Settings → Plugins → Delete…** and stop the exporter.
See the [CodexBar plugin guide](https://github.com/steipete/CodexBar/blob/main/docs/plugins.md)
for approval and display options.
