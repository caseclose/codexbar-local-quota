// Read rendered text only. Never execute page-supplied markup or follow links.
(() => {
  const text = document.body?.innerText || "";
  if (!text || text.length > 250000) return null;
  const number = String.raw`(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?`;
  const amount = String.raw`(?:(USD|CNY|RMB|EUR|[$¥￥€])\s*)?(${number})\s*(USD|CNY|RMB|EUR|元|tokens?)?`;
  function unit(s) {
    if (!s) return "";
    return ({ "$":"USD", "€":"EUR", "¥":"CNY", "￥":"CNY", RMB:"CNY", "元":"CNY", TOKEN:"tokens", TOKENS:"tokens" })[s.toUpperCase()] || s.toUpperCase();
  }
  function read(m, offset) {
    const a = unit(m[offset]), b = unit(m[offset + 2]);
    if (a && b && a !== b) return null;
    const value = Number(m[offset + 1].replace(/,/g, ""));
    return Number.isFinite(value) ? {value, unit:a || b} : null;
  }
  function combine(a, b, remaining) {
    if (!a || !b || a.unit !== b.unit) return null;
    const used = remaining ? b.value - a.value : a.value;
    if (used < 0 || b.value <= 0) return null;
    return {used, limit:b.value, ...(a.unit && a.unit !== "tokens" ? {currency:a.unit} : {})};
  }
  const labels = {
    used: /^(?:(?:monthly|current|total)\s+)?(?:spent|used|usage|consumed)|^(?:本月|当前|累计)?(?:已用额度|已使用|已用|已消费|已消耗)/i,
    limit: /^(?:(?:monthly|total)\s+)?(?:limit|quota|budget|allocation)|^(?:本月|每月|月度|总)?(?:总额度|额度上限|额度|预算|配额)/i,
    remaining: /^(?:remaining(?:\s+(?:quota|balance|credits))?|available(?:\s+balance)?)|^(?:本月|当前)?(?:剩余额度|剩余|可用余额)/i
  };
  const single = new RegExp("^" + amount + "$", "i");
  const ratio = new RegExp("^" + amount + "\\s*(?:/|of)\\s*" + amount + "(?:\\s+\\d+(?:\\.\\d+)?%)?$", "i");
  const lines = text.split(/\n/).map(s => s.trim()).filter(Boolean);
  const positions = {};
  const found = {used:[], limit:[], remaining:[]}, pairs = [];
  for (let i = 0; i < lines.length; i++) {
    for (const [k,p] of Object.entries(labels)) {
      const label = lines[i].match(p);
      if (!label) continue;
      const rest = lines[i].slice(label[0].length).trim().replace(/^[:：]\s*/, "");
      const m = (rest || lines[i+1] || "").match(single);
      if (m) { found[k].push(read(m,1)); positions[k] = i; }
      if (k === "used" || k === "remaining") {
        // Responsive cards may render the numerator, slash and denominator on separate lines.
        const tail = [rest, ...lines.slice(i+1,i+4)].filter(Boolean);
        for (let count=1; count<=tail.length; count++) {
          const match = tail.slice(0,count).join(" ").match(ratio);
          if (match) { pairs.push(combine(read(match,1),read(match,4),k === "remaining")); break; }
        }
      }
    }
    // Require an adjacent usage/quota heading; a random fraction is not quota.
    if (/(?:usage|spend|spent|used|consumption)\s*(?:and|\/)\s*(?:quota|budget|limit)|(?:费用|用量|消耗|已用)\s*(?:与|和|\/)\s*(?:额度|预算|上限)/i.test(lines[i])) {
      const m = (lines[i+1] || "").match(ratio) || lines.slice(i+1,i+4).join(" ").match(ratio);
      if (m) pairs.push(combine(read(m,1),read(m,4),false));
    }
  }
  if (Object.values(found).some(arr => arr.length > 1 || arr.includes(null))) return null;
  function nearby(a,b) {
    const lower = Math.min(positions[a],positions[b]), upper = Math.max(positions[a],positions[b]);
    return upper-lower <= 6 && lines.slice(lower+1,upper).every(line =>
      single.test(line) || Object.values(labels).some(pattern => pattern.test(line)));
  }
  if (found.limit.length && found.used.length && nearby("limit","used")) pairs.push(combine(found.used[0],found.limit[0],false));
  if (found.limit.length && found.remaining.length && nearby("limit","remaining")) pairs.push(combine(found.remaining[0],found.limit[0],true));
  if (!pairs.length || pairs.some(x => !x)) return null;
  const first=pairs[0];
  if (pairs.some(x => Math.abs(x.used-first.used)>0.000001 || x.limit!==first.limit || x.currency!==first.currency)) return null;
  for (const [kind, expected] of [["used",first.used],["limit",first.limit],["remaining",first.limit-first.used]]) {
    if (found[kind].length && Math.abs(found[kind][0].value-expected)>0.000001) return null;
  }
  return first;
})()
