# Local Quota for CodexBar

Read quota from a dashboard URL or an existing local JSON feed. Dashboard mode
includes a generic macOS WebKit reader for signed-in and JavaScript-rendered pages.

## Read a dashboard URL

On macOS with CodexBar, Python 3 and Xcode Command Line Tools installed:

```sh
git clone https://github.com/caseclose/codexbar-local-quota.git
cd codexbar-local-quota
python3 install-page-reader.py
```

1. Open **CodexBar → Settings → Plugins → Local Quota**. Enter the dashboard
   address in **内部额度网址 / Dashboard URL**, e.g. `usage.example.invalid/billing`
   (illustrative). A bare hostname uses HTTPS. Use a dashboard link without
   embedded tokens or passwords. For internal pages, connect to the required network.
2. Approve the loopback origin shown by CodexBar. If a login window appears,
   sign in there. You can reopen **Local Quota Page Reader.app** in
   `~/Library/Application Support/Local Quota Page/` to complete sign-in.
3. The reader checks the rendered dashboard roughly once a minute. Its two
   background jobs start at user login. Only CodexBar needs a menu-bar icon.

The reader recognizes explicitly labeled used/limit or remaining/limit amounts
in English and Chinese, including labeled fractions. For example, “Used: 25 EUR”
and “Monthly limit: 100 EUR” yield 75 EUR remaining. Conflicting totals,
incompatible units, balance-only pages without a limit, and inaccessible
dashboards cannot produce a percentage. Open a more specific summary or switch
to the JSON feed for an unsupported layout. The reader observes the displayed
quota; choose a URL that opens the intended account and billing period.

WebKit keeps the login session locally. The reader inspects visible text on the
configured HTTPS origin and saves only the configured address, status and quota
snapshot. The plugin uses an approved IPv4 loopback endpoint. Browser-origin
requests are rejected. The helper does not upload page text or cookies.
The installer keeps existing CodexBar provider settings and selects its local
port. If another service occupies the port, use `--port 8766`. To keep a legacy
export available when the dashboard setting is blank, pass
`--feed /absolute/path/to/quota.json`.

To remove dashboard mode, clear the dashboard field. To uninstall the background
jobs, run the following in a terminal and remove the two corresponding plist
files from `~/Library/LaunchAgents/`. Remove the **Local Quota Page** support
folder if you also want to discard its reader and last snapshot.

```sh
launchctl bootout "gui/$(id -u)/io.github.caseclose.local-quota.reader"
launchctl bootout "gui/$(id -u)/io.github.caseclose.local-quota.http"
```

## Use a local JSON feed instead

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
- For JSON mode, keep source-specific authentication in your exporter. Both the demo and integration test use synthetic data.

## Verify

```sh
node page-reader/detect.test.js
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
