// Generic CC Switch request/extractor host for TRUSTED local scripts.
// Node vm is not a security sandbox. No supplier-specific API logic here.
const vm = require("node:vm");
const MAX_BYTES = 2_000_000;

function failure(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}

async function execute(p, fetchImpl = fetch) {
  let context, request, url;
  try {
    let code = p.code;
    for (const key of ["apiKey", "baseUrl", "accessToken", "userId"]) {
      if (p[key] != null) code = code.split(`{{${key}}}`).join(p[key]);
    }
    context = vm.createContext(Object.create(null), {codeGeneration: {strings: false, wasm: false}});
    vm.runInContext(`globalThis.config = (${code});`, context, {timeout: 1000});
    request = JSON.parse(vm.runInContext("JSON.stringify(config.request)", context, {timeout: 1000}));
  } catch (_) {
    throw failure("SCRIPT");
  }
  try {
    url = new URL(request.url);
    const base = new URL(p.baseUrl);
    if (url.protocol !== "https:" || url.origin !== base.origin || url.username || url.password) {
      throw failure("ORIGIN");
    }
  } catch (_) {
    throw failure("ORIGIN");
  }
  if (String(request.method || "GET").toUpperCase() !== "GET") throw failure("METHOD");
  const controller = new AbortController();
  const seconds = Math.min(30, Math.max(1, Number(p.timeout) || 10));
  const timer = setTimeout(() => controller.abort(), seconds * 1000);
  let text;
  try {
    const response = await fetchImpl(url, {
      method: "GET", headers: request.headers || {}, signal: controller.signal, redirect: "error"
    });
    if (!response.ok) throw failure("HTTP");
    if (Number(response.headers.get("content-length")) > MAX_BYTES) throw failure("SIZE");
    const chunks = [];
    let size = 0;
    if (response.body) {
      for await (const chunk of response.body) {
        size += chunk.length;
        if (size > MAX_BYTES) throw failure("SIZE");
        chunks.push(chunk);
      }
    }
    text = Buffer.concat(chunks).toString("utf8");
  } catch (error) {
    if (error.code === "HTTP" || error.code === "SIZE") throw error;
    throw failure("NETWORK");
  } finally {
    clearTimeout(timer);
    controller.abort();
  }
  try {
    context.responseJSON = text;
    const result = vm.runInContext(
      "JSON.stringify(config.extractor(JSON.parse(responseJSON)))", context, {timeout: 1000}
    );
    return JSON.parse(result);
  } catch (_) {
    throw failure("SCRIPT");
  }
}

module.exports = {execute};
if (require.main === module) {
  let input = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", chunk => {
    input += chunk;
    if (input.length > MAX_BYTES) {
      process.stderr.write("SIZE");
      process.exit(1);
    }
  });
  process.stdin.on("end", async () => {
    try {
      process.stdout.write(JSON.stringify(await execute(JSON.parse(input))));
    } catch (error) {
      const allowed = ["SCRIPT", "ORIGIN", "METHOD", "HTTP", "SIZE", "NETWORK"];
      process.stderr.write(allowed.includes(error.code) ? error.code : "SCRIPT");
      process.exitCode = 1;
    }
  });
}
