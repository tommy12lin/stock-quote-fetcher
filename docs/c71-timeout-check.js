// C7-1／C7-2：只在「上游換成慢 origin 的預覽版本」的 preview URL 上執行，絕不在正式 finpo 上執行。
// 登入 Access 後，在 DevTools Console 貼上。全程約 6.5 分鐘，分頁保持在前景，期間不要重新整理。
// 只發 GET，路徑 /api/c71 在正式後端不存在。輸出只有秒數、狀態碼與錯誤代碼。
await (async () => {
  const probe = async s => {
    const started = performance.now();
    let status = 'network_error', code = null, role = null;
    try {
      const r = await fetch('/api/c71?s=' + s, { redirect: 'manual' });
      status = r.type === 'opaqueredirect' ? 'redirect' : r.status;
      const b = await r.json().catch(() => ({}));
      code = b.code ?? null; role = b.role ?? null;
    } catch (e) { code = e.name; }
    return { s, status, code, role, seconds: ((performance.now() - started) / 1000).toFixed(2) };
  };
  const rows = [];
  // 5 秒是正向對照：慢 origin 有回應、Worker 照常轉發。120 與 130 夾住 09-22 量到的 125 秒。
  for (const s of [5, 120, 130]) { rows.push(await probe(s)); console.log(rows.at(-1)); }
  // 前端那一層：app.js 的 api() 遇到 504 時，使用者實際會看到的訊息。
  const started = performance.now();
  let shown;
  try { await api('/api/c71?s=130'); shown = '（沒有拋出錯誤）'; } catch (e) { shown = e.message; }
  rows.push({ s: 130, status: 'app.js', code: shown, role: null, seconds: ((performance.now() - started) / 1000).toFixed(2) });
  console.table(rows);
})();
