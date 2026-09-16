const {test} = require("node:test");
const assert = require("node:assert/strict");
const {execute} = require("../src/cc_balance_widget/usage_runner.cjs");
const fixture = {
  code: '({request:{url:"{{baseUrl}}/balance",headers:{Authorization:"Bearer {{apiKey}}"}},extractor:r=>({remaining:r.available,unit:"USD"})})',
  baseUrl: "https://example.com", apiKey: "fixture-not-a-real-key", timeout: 1
};

test("executes the actual extractor, not a hard-coded response mapping", async () => {
  const result = await execute(fixture, async (url, options) => {
    assert.equal(url.href, "https://example.com/balance");
    assert.equal(options.headers.Authorization, "Bearer fixture-not-a-real-key");
    assert.equal(options.redirect, "error");
    return Response.json({available: 12.34});
  });
  assert.deepEqual(result, {remaining: 12.34, unit: "USD"});
});

test("rejects cross-origin and write requests before any fetch", async () => {
  for (const [request, code] of [
    ['{url:"https://other.example/balance"}', "ORIGIN"],
    ['{url:"http://example.com/balance"}', "ORIGIN"],
    ['{url:"https://example.com/balance",method:"POST"}', "METHOD"],
  ]) {
    await assert.rejects(execute({...fixture, code: `({request:${request},extractor:r=>r})`},
      () => assert.fail("network called")), error => error.code === code);
  }
});

test("HTTP and oversized responses are rejected", async () => {
  await assert.rejects(execute(fixture, async () => new Response("", {status: 401})),
    e => e.code === "HTTP");
  await assert.rejects(execute(fixture, async () => new Response("x".repeat(2_000_001))),
    e => e.code === "SIZE");
});

test("script loops terminate", async () => {
  await assert.rejects(execute({...fixture, code: "(()=>{while(true){}})()"},
    () => assert.fail("network called")), e => e.code === "SCRIPT");
});

test("extractor loops terminate and network errors are sanitized", async () => {
  await assert.rejects(execute({...fixture, code: fixture.code.replace("r=>({remaining:r.available,unit:\"USD\"})",
    "()=>{while(true){}}")}, async () => Response.json({})), e => e.code === "SCRIPT");
  await assert.rejects(execute(fixture, () => {throw Error("fake-secret");}),
    e => e.code === "NETWORK" && !e.message.includes("fake-secret"));
});

test("timeout also covers streaming response body", async () => {
  const fetch = async (_url, options) => new Response(new ReadableStream({
    start(controller) {
      options.signal.addEventListener("abort", () => controller.error(Error("aborted")));
    }
  }));
  await assert.rejects(execute(fixture, fetch), e => e.code === "NETWORK");
});
