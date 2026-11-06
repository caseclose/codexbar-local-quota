import Cocoa
import WebKit

// The only input is the user's plugin setting. The HTTP bridge cannot navigate this reader.
final class Reader: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    let home = FileManager.default.homeDirectoryForCurrentUser
    let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1050, height: 740))
    lazy var window = NSWindow(contentRect: web.frame, styleMask: [.titled, .closable, .resizable],
                               backing: .buffered, defer: false)
    var setting = "", candidate = "", settled = 0, generation = 0, polls = 0
    var target: URL?, loaded = false, busy = false, prompted = false
    var lastStart = Date.distantPast
    var lastDiagnostic: String?
    var previous: NSDictionary?
    var timer: Timer?
    let detector = (try? String(contentsOf: Bundle.main.url(forResource: "detect", withExtension: "js")!,
                                encoding: .utf8)) ?? ""

    func applicationDidFinishLaunching(_ n: Notification) {
        window.title = "Local Quota · Dashboard"
        window.contentView = web
        window.isReleasedWhenClosed = false
        window.center()
        web.navigationDelegate = self
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.tick() }
    }

    func show() {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if target != nil { show() }
        return true
    }

    func configuredPage() -> String {
        let file = home.appendingPathComponent(".config/codexbar/config.json")
        guard let data = try? Data(contentsOf: file),
              let config = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let providers = config["providers"] as? [[String: Any]],
              let provider = providers.first(where: { $0["id"] as? String == "local-quota" }),
              provider["enabled"] as? Bool != false,
              let settings = provider["pluginSettings"] as? [String: String] else { return "" }
        return (settings["PAGE_URL"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func dashboard(_ input: String) -> URL? {
        guard !input.isEmpty, input.utf8.count <= 2048, !input.contains(where: { $0.isWhitespace }),
              !input.contains("\\"), let u = URLComponents(string: input.contains("://") ? input : "https://" + input),
              u.scheme?.lowercased() == "https", let host = u.host, !host.isEmpty,
              u.user == nil, u.password == nil else { return nil }
        return u.url
    }

    func atTarget() -> Bool {
        guard let here = web.url, let target else { return false }
        guard here.scheme == "https", here.host?.lowercased() == target.host?.lowercased(),
              (here.port ?? 443) == (target.port ?? 443) else { return false }
        // A bare site may redirect to its dashboard; an explicit selection must still match.
        let requestedPath = target.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let actualPath = here.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return (requestedPath.isEmpty || requestedPath == actualPath)
            && (target.query == nil || target.query == here.query)
            && (target.fragment == nil || target.fragment == here.fragment)
    }

    func publish(_ state: String, _ quota: [String: Any]? = nil) {
        let diagnostic = setting + "\n" + state
        if quota == nil && lastDiagnostic == diagnostic { return }
        var obj: [String: Any] = ["page": setting, "state": state]
        if let quota { obj["quota"] = quota }
        let dest = home.appendingPathComponent("Library/Application Support/Local Quota Page/page.json")
        do {
            try JSONSerialization.data(withJSONObject: obj).write(to: dest, options: .atomic)
            lastDiagnostic = diagnostic
        }
        catch { NSLog("Local Quota: could not write page snapshot") }
    }

    func tick() {
        let value = configuredPage()
        if candidate != value { candidate = value; settled = 0 }
        settled = min(3, settled + 1)
        if candidate != setting {
            guard settled >= 3 else { return }
            generation += 1
            web.stopLoading()
            window.orderOut(nil)
            setting = candidate
            target = dashboard(setting)
            loaded = false; busy = false; prompted = false; lastStart = .distantPast
            publish(target == nil ? "invalid" : "loading")
        }
        guard let target else { return }
        if Date().timeIntervalSince(lastStart) >= 60 {
            generation += 1
            lastStart = Date(); previous = nil; polls = 0; busy = false
            // Leave an interactive sign-in flow alone while it is visible.
            if !window.isVisible {
                loaded = false
                web.load(URLRequest(url: target, cachePolicy: .reloadIgnoringLocalCacheData))
            }
        }
        guard polls >= 0, !busy, !web.isLoading else { return }
        polls += 1
        if !atTarget() || !loaded {
            if polls >= 12 {
                let redirected = web.url != nil && !atTarget()
                publish(redirected ? "signin" : "unavailable")
                if redirected && !prompted { prompted = true; show() }
            }
            return
        }
        let request = generation
        busy = true
        web.evaluateJavaScript(detector, in: nil, in: .defaultClient) { result in
            guard self.generation == request else { return }
            self.busy = false
            if case .success(let value) = result, let raw = value as? NSDictionary {
                guard self.previous?.isEqual(raw) == true else { self.previous = raw; return }
                var q = raw as? [String: Any] ?? [:]
                q["version"] = 1; q["observedAt"] = ISO8601DateFormatter().string(from: Date())
                self.publish("ready", q)
                self.polls = -1; self.prompted = false; self.window.orderOut(nil)
            } else {
                self.previous = nil
                if self.polls >= 16 {
                    self.publish("unrecognized")
                    if !self.prompted { self.prompted = true; self.show() }
                }
            }
        }
    }
    func webView(_ w: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        loaded = false; generation += 1; busy = false; previous = nil; polls = 0
    }
    func webView(_ w: WKWebView, didFinish navigation: WKNavigation!) { loaded = true }
    func webView(_ w: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { loaded = false; publish("unavailable") }
    }
    func webView(_ w: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { loaded = false; publish("unavailable") }
    }
    func webView(_ w: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.targetFrame?.isMainFrame != false && action.request.url?.scheme != "https" {
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }
}
umask(0o077)
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let reader = Reader()
app.delegate = reader
app.run()
