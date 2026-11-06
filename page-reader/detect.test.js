const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {runInNewContext} = require("node:vm");

const script = readFileSync(join(__dirname, "detect.js"), "utf8");
function scan(text) {
  return JSON.parse(JSON.stringify(runInNewContext(script, {document: {body: {innerText: text}}})));
}
assert.deepEqual(scan("Payments overview\nUsed\nEUR 3\n/\nEUR 45"), {used:3, limit:45, currency:"EUR"});
const expected = {used: 25, limit: 100, currency: "EUR"};
assert.deepEqual(scan("Monthly usage and budget\n€25 / €100"), expected);
assert.deepEqual(scan("Spent: EUR 25\nMonthly limit: 100 EUR"), expected);
assert.deepEqual(scan("Remaining balance\n75 EUR\nTotal quota\n100 EUR"), expected);
assert.deepEqual(scan("已用额度：25元\n总额度：100元"), {used:25, limit:100, currency:"CNY"});
assert.deepEqual(scan("Used: 1,234 tokens\nLimit: 1,000 tokens"), {used:1234, limit:1000});
for (const input of ["Sign in", "Invoice\n€25 / €100", "Used: 10 USD\nTotal quota: 40 EUR",
  "Used: $25\nUsed: $35\nLimit: $100", "Used: $25\nLimit: $100\nRemaining: $40",
  "Used: $25\nLimit: $0", "Used: 20%\nLimit: 100%", "Usage 1 through 4", "Plan A\nUsed: 30 EUR\nPlan B\nMonthly limit: 80 EUR"]) {
  assert.equal(scan(input), null, input);
}
console.log("PASS: rendered quota detection and ambiguous results");
