/* Pyodide 工作线程：加载 CPython 与 tianwen 包，原样跑确定性管线与
 * 校验闸门。放在 Worker 里跑，是因为 requests 在 Pyodide 下走同步
 * XHR——主线程会冻结界面，Worker 则无碍。
 * 大模型请求由浏览器直达 OpenRouter，API Key 不经任何第三方服务器。 */

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

const status = (text) => postMessage({ type: "status", text });

async function init() {
  status("加载 Python 运行时（首次约十余 MB，请稍候）…");
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/",
  });

  status("加载依赖（requests、cnlunar）…");
  await pyodide.loadPackage(["micropip"]);
  try {
    await pyodide.loadPackage("requests");
  } catch (e) {
    await pyodide.pyimport("micropip").install("requests");
  }
  const wheel = new URL("wheels/cnlunar-0.2.4-py3-none-any.whl",
                        self.location.href).href;
  await pyodide.pyimport("micropip").install(wheel);

  status("加载天问程序与典籍数据…");
  const zip = await fetch(new URL("tianwen.zip", self.location.href));
  if (!zip.ok) throw new Error(`tianwen.zip 获取失败 HTTP ${zip.status}`);
  pyodide.unpackArchive(await zip.arrayBuffer(), "zip");

  const glue = await fetch(new URL("app.py", self.location.href));
  await pyodide.runPythonAsync(await glue.text());
  return pyodide;
}

const ready = init();

ready.then(
  () => postMessage({ type: "ready" }),
  (e) => postMessage({ type: "fatal", text: String(e) }),
);

onmessage = async (ev) => {
  const { type, payload, ask } = ev.data;
  let pyodide;
  try {
    pyodide = await ready;
  } catch (e) {
    return;   // 初始化失败已上报 fatal
  }
  try {
    let out;
    if (type === "run") {
      out = pyodide.globals.get("run")(JSON.stringify(payload));
    } else if (type === "followup") {
      out = pyodide.globals.get("followup")(ask);
    } else {
      return;
    }
    postMessage({ type: "result", data: JSON.parse(out) });
  } catch (e) {
    postMessage({ type: "result",
                  data: { kind: "error", text: String(e) } });
  }
};
