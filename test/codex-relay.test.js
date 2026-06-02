const assert = require("node:assert");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawnSync, spawn } = require("node:child_process");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const relay = path.join(root, "codex-relay");
const forward = path.join(root, "codex-relay-forward");

function run(bin, args = [], opts = {}) {
  return spawnSync(process.execPath, [bin, ...args], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      ...opts.env,
    },
  });
}

async function getFreePort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

test("help prints vps commands", () => {
  const res = run(relay, ["--help"]);
  assert.equal(res.status, 0);
  assert.match(res.stdout, /vps setup/);
});

test("proxy show uses env precedence and redacts credentials", () => {
  const home = path.join(os.tmpdir(), `codex-relay-test-${process.pid}`);
  const res = run(relay, ["proxy", "show"], {
    env: {
      HOME: home,
      HTTPS_PROXY: "http://user:secret@example.com:8080",
      HTTP_PROXY: "",
      http_proxy: "",
      https_proxy: "",
    },
  });
  assert.equal(res.status, 0);
  assert.match(res.stdout, /effective proxy: http:\/\/\*\*\*@example\.com:8080\//);
  assert.doesNotMatch(res.stdout, /secret/);
});

test("forwarder rejects targets outside allowlist", async () => {
  const upstream = net.createServer();
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  const upstreamPort = upstream.address().port;
  const relayPort = await getFreePort();
  const proc = spawn(process.execPath, [forward, `127.0.0.1:${relayPort}`, `http://127.0.0.1:${upstreamPort}`], {
    cwd: root,
    env: { ...process.env, FORWARD_ALLOW: "api.openai.com:443" },
    stdio: ["ignore", "ignore", "pipe"],
  });

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("forwarder did not start")), 3000);
    proc.stderr.on("data", (d) => {
      if (String(d).includes("codex-relay-forward")) {
        clearTimeout(timer);
        resolve();
      }
    });
  });

  const response = await new Promise((resolve) => {
    const client = net.connect(relayPort, "127.0.0.1", () => {
      client.write("CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n");
    });
    let data = "";
    client.on("data", (d) => { data += d.toString(); });
    client.on("end", () => resolve(data));
  });

  proc.kill();
  upstream.close();
  assert.match(response, /^HTTP\/1\.1 403 Forbidden/);
});
