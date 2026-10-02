// C7-4 D1：在 finpo 頁面的 DevTools Console 貼上執行。只讀 GET，輸出只有檢查結果與檔數，不含代碼與金額。
// 以字串的精確小數驗算（BigInt），不經過浮點數。
await (async () => {
  const dec = s => { const neg = s.startsWith('-'); const [i, f = ''] = s.replace('-', '').split('.'); return { n: BigInt((neg ? '-' : '') + i + f), s: f.length }; };
  const align = (a, b) => { const s = Math.max(a.s, b.s); return [a.n * 10n ** BigInt(s - a.s), b.n * 10n ** BigInt(s - b.s), s]; };
  const add = (a, b) => { const [x, y, s] = align(a, b); return { n: x + y, s }; };
  const neg = a => ({ n: -a.n, s: a.s });
  const mul = (a, b) => ({ n: a.n * b.n, s: a.s + b.s });
  const eq = (a, b) => { const [x, y] = align(a, b); return x === y; };
  const round2 = a => { if (a.s <= 2) return { n: a.n * 10n ** BigInt(2 - a.s), s: 2 }; const d = 10n ** BigInt(a.s - 2); const q = (a.n < 0n ? -a.n : a.n); let r = q / d; if ((q % d) * 2n >= d) r += 1n; return { n: a.n < 0n ? -r : r, s: 2 }; };
  const zero = { n: 0n, s: 0 };
  const sum = xs => xs.reduce(add, zero);
  const get = async m => (await fetch('/api/portfolio/valuation?market=' + m)).json();
  const v = { ALL: await get('ALL'), TW: await get('TW'), US: await get('US') };
  const out = {}, exact = {};
  for (const [m, r] of Object.entries(v)) {
    const fx = r.fx ? dec(String(r.fx)) : null;
    const factor = row => row.currency === 'TWD' ? dec('1') : fx;
    const valued = r.rows.filter(x => x.market_value !== null);
    const twd = valued.map(x => mul(dec(x.market_value), factor(x)));
    const cost = r.rows.map(x => mul(mul(dec(x.quantity), dec(x.buy_price)), factor(x)));
    exact[m] = { known: sum(twd), cost: sum(cost) };
    const c = {
      market_filter: r.rows.every(x => m === 'ALL' || x.market === m),
      count: r.rows.length === r.count,
      coverage: valued.length === r.coverage,
      row_value_is_price_x_qty: valued.every(x => eq(dec(x.market_value), mul(dec(x.price), dec(x.quantity)))),
      known_total: r.known_total !== null && eq(dec(r.known_total), round2(exact[m].known)),
      cost: r.cost !== null && eq(dec(r.cost), round2(exact[m].cost)),
      total: r.total === null ? 'null' : eq(dec(r.total), round2(exact[m].known)),
      profit: r.profit === null ? 'null' : eq(dec(r.profit), round2(add(exact[m].known, neg(exact[m].cost)))),
      summaries: r.summaries.every(s => eq(dec(s.known_subtotal), sum(valued.filter(x => x.currency === s.currency).map(x => dec(x.market_value))))
                                       && s.holding_count === r.rows.filter(x => x.currency === s.currency).length),
      chart_sum_within_rounding: (() => { if (!r.known_total) return 'n/a'; const d = add(sum(r.chart.map(x => dec(x.value))), neg(dec(r.known_total))); const lim = { n: 5n * BigInt(r.chart.length), s: 3 }; const [a, b] = align({ n: d.n < 0n ? -d.n : d.n, s: d.s }, lim); return a <= b; })(),
      chart_items: r.chart.length,
      other_members: (r.chart.find(x => x.ticker === '其他') || { members: [] }).members.length,
      status: r.status, count_n: r.count, coverage_n: r.coverage, needs_fx: r.needs_fx,
    };
    out[m] = c;
  }
  out.CROSS = {
    count_tw_plus_us: v.TW.count + v.US.count === v.ALL.count,
    known_tw_plus_us: eq(add(exact.TW.known, exact.US.known), exact.ALL.known),
    cost_tw_plus_us: eq(add(exact.TW.cost, exact.US.cost), exact.ALL.cost),
    same_fx: v.ALL.fx === v.TW.fx && v.ALL.fx === v.US.fx,
  };
  console.log(JSON.stringify(out, null, 2));
  return out;
})();
