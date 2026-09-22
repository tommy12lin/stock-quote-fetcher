'use strict';
const $ = id => document.getElementById(id);
let saved = null, draft = [], dirty = false, token = '', valuation = null, file = null, preview = null, loading = false, poll = null, valuationSequence = 0;
const colors = ['#2563eb','#d97706','#0f766e','#9333ea','#dc4c64','#65a30d','#0891b2','#9a5426','#6366c7','#c0268c','#34794b','#b39720','#164e78','#e58470','#786044'];
const fieldLabel = field => ({ticker:'股票代碼',quantity:'持有股數',buy_price:'平均買入價'}[field] || field || '');
const labels = {cached:'快取', stale:'延遲／過期', time_unknown:'時間未知', freshness_unknown:'時效未知', market_closed:'休市', session_unknown:'交易時段未知', future_time:'時間異常', currency_mismatch:'幣別異常', price_kind_mismatch:'價格口徑不符'};
const fmt = value => {if(value==null)return '—';const [whole,fraction]=String(value).split('.');return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')+(fraction===undefined?'':'.'+fraction);};
const date = value => value ? new Date(value).toLocaleString('zh-TW', {timeZone:'Asia/Taipei', hour12:false}) : '未知';
const signed = value => value == null ? '—' : (String(value).startsWith('-') ? '虧損 ' : '獲利 +') + fmt(value);
function el(tag, text, className) { const e = document.createElement(tag); if(text != null) e.textContent = text; if(className) e.className = className; return e; }
function message(text, success=false) { $('message').hidden=false; $('message').textContent=text; $('message').className=success?'success':''; }
let sessionRequest = null, loginRedirecting = false, recoveredRevision = null;
function resumeLogin() {
  // A failed write is never replayed after a network error. Preserve edits for login.
  if(loginRedirecting) throw new Error('正在重新登入。');
  const last = Number(sessionStorage.getItem('portfolio-login-at') || 0);
  if(Date.now()-last < 60000) throw new Error('連線失敗，請確認網路後重新整理；未保存內容仍保留。');
  if(dirty) sessionStorage.setItem('portfolio-login-draft', JSON.stringify({rows:draft,fx:$('fx').value,revision:saved?.revision}));
  sessionStorage.setItem('portfolio-login-at', String(Date.now()));
  loginRedirecting = true;
  window.location.reload();
  throw new Error('連線或登入已失效，正在重新登入；請在登入後確認操作結果。');
}
async function renewSession() {
  if(!sessionRequest) sessionRequest = api('/api/session', 'GET', undefined, false).then(data=>{token=data.token;}).finally(()=>{sessionRequest=null;});
  await sessionRequest;
}
// C4-1 makes the refresh POST a long request. A proxy or edge that cuts it short looks
// exactly like an Access redirect to fetch(), so that one call opts out of the reload and
// reports the cut instead; a genuine login expiry is caught by the next call.
function cutShort() {
  throw new Error('更新未能在連線時限內完成；既有價格保留，請稍後重試。若仍無法更新，請重新整理頁面。');
}
async function api(path, method='GET', body, retry=true, reloadOnRedirect=true) {
  const headers = {}; if(method!=='GET') { headers['X-Portfolio-Token']=token; if(!(body instanceof File)) headers['Content-Type']='application/json'; }
  let response;
  try {
    response = await fetch(path, {method,headers,redirect:'manual',body:body===undefined?undefined:body instanceof File?body:JSON.stringify(body)});
  } catch(error) {
    // CORS redirects and network outages are indistinguishable to fetch; bound reloads.
    if(error instanceof TypeError) return reloadOnRedirect ? resumeLogin() : cutShort();
    throw error;
  }
  if(response.type==='opaqueredirect' || response.redirected || response.headers.get('content-type')?.includes('text/html')) return reloadOnRedirect ? resumeLogin() : cutShort();
  const data = await response.json();
  if(retry && path!=='/api/session' && [401,403].includes(response.status) && ['unauthorized','session_expired'].includes(data.code)) {
    await renewSession();
    return api(path, method, body, false);
  }
  if(!response.ok) throw new Error(data.message + (data.issues?.length?'\n'+data.issues.map(x=>`${x.sheet||''} 第 ${x.row||'?'} 列 ${fieldLabel(x.field)}：${x.message}`).join('\n'):''));
  return data;
}
function setDirty() { dirty=true; $('draft-state').textContent='有未保存的修改 · 總覽仍使用已保存清單'; $('draft-state').className='dirty'; }
function draftRender() {
  $('draft').replaceChildren();
  draft.forEach((row,i)=>{ const tr=el('tr'); ['ticker','quantity','buy_price'].forEach(field=>{ const td=el('td'), input=el('input'); input.value=row[field]; input.setAttribute('aria-label',`第 ${i+1} 筆 ${field==='ticker'?'股票代碼':field==='quantity'?'持有股數':'平均買入價'}`); input.placeholder=field==='ticker'?'0050 / AAPL':'0'; if(field!=='ticker') input.inputMode='decimal'; input.addEventListener('input',()=>{row[field]=input.value;setDirty();}); td.append(input);tr.append(td); }); const td=el('td'), b=el('button','刪除'); b.setAttribute('aria-label',`刪除第 ${i+1} 筆持股`); b.onclick=()=>{draft.splice(i,1);setDirty();draftRender();}; td.append(b); tr.append(td); $('draft').append(tr); });
  if(!draft.length){const tr=el('tr'),td=el('td','尚無持股。上傳 Excel 或點選「新增持股」。','empty-cell');td.colSpan=4;tr.append(td);$('draft').append(tr);}
}
function add(){if(!saved)return;draft.push({ticker:'',quantity:'',buy_price:''});setDirty();draftRender();$('editor').scrollIntoView({behavior:'smooth'});$('draft').lastElementChild.querySelector('input').focus();}
function savedRender(){ $('version').textContent=`已保存版本 ${saved.revision}`; $('fx-time').textContent=saved.fx?`手動匯率 ${saved.fx} · 輸入時間 ${date(saved.fx_updated_at)}`:'尚未設定美元匯率'; }
async function loadValuation(){ const sequence=++valuationSequence; const v=await api('/api/portfolio/valuation?market='+$('market').value); if(sequence!==valuationSequence||!saved||v.portfolio_revision!==saved.revision)return; valuation=v;render(); }
function render(){
  const v=valuation, scope=$('market').selectedOptions[0].textContent;
  $('total-label').textContent=(v.total==null&&v.known_total!=null?'已知持股市值（非完整總額）':'持股總市值')+($('market').value==='ALL'?'':` · ${scope}`);
  $('total').textContent=fmt(v.total??v.known_total);$('cost').textContent=fmt(v.cost);$('profit').textContent=v.profit==null?'—':(v.profit.startsWith('-')?'':'+')+fmt(v.profit);
  $('profit').className='metric '+(v.profit?.startsWith('-')?'negative':'positive');$('return').textContent=v.return_pct==null?'完整報價與匯率齊全後顯示':`${signed(v.profit)} · 報酬率 ${v.return_pct.startsWith('-')?'':'+'}${v.return_pct}%`;
  $('total-note').textContent=v.needs_fx?'待輸入匯率：請在下方設定 USD / TWD':v.count?'TWD · 股票與 ETF 市值，不含現金':'上傳或新增持股，開始查看市值';
  $('coverage').textContent=`報價涵蓋 ${v.coverage} / ${v.count} 檔`;$('quality').textContent={complete:'可用估值',partial:'部分估值 · 缺價不計為零',degraded:'降級估值 · 請參閱逐股品質',unavailable:v.needs_fx?'待輸入匯率':'尚無可用估值'}[v.status];
  $('subtotals').textContent=v.summaries.map(s=>`${s.currency} ${s.total==null?'已知市值':'市值'} ${fmt(s.known_subtotal_display)}（${s.valued_count}/${s.holding_count} 檔）`).join('　／　');
  let times=$('market-times');if(!times){times=el('p',null,'muted');times.id='market-times';$('subtotals').after(times);}times.textContent=['TW','US'].map(m=>{const stamps=v.rows.filter(r=>r.market===m&&r.quote_time).map(r=>r.quote_time).sort();return stamps.length?`${m==='TW'?'台股':'美股'}報價時間：${date(stamps[0])} ～ ${date(stamps.at(-1))}`:'';}).filter(Boolean).join('　／　');
  $('count').textContent=`${v.count} 檔`;
  $('chart-note').textContent=`${scope} · ${v.missing.length?'已知市值配置，未納入：'+v.missing.join('、'):'依台幣市值計算市場內占比'}`;
  if(v.warning) message(v.warning);
  renderChart();renderDetails();
}
function renderChart(){
  const v=valuation;$('chart').replaceChildren();$('legend').replaceChildren();
  if(!v.chart.length){$('chart').className='chart-empty';$('chart').append(el('div','◔','empty-icon'),el('h3',v.needs_fx?'請先輸入美元匯率':v.count?'等待可用報價':'你的配置，從第一筆持股開始'),el('p',v.count?'完整價格與匯率齊全後，便可查看配置。':'上傳 Excel 或在下方手動新增持股。'));return;}
  $('chart').className='';
  const donut=el('div',null,'donut'),center=el('div',null,'donut-center');
  center.append(el('span',v.total==null?'已知市值 · TWD':'持股市值 · TWD'),el('strong',fmt(v.known_total)));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 240 240');svg.setAttribute('class','donut-segments');
  svg.setAttribute('role','group');svg.setAttribute('aria-label','持股市值配置，指向或聚焦色塊查看詳細資訊');
  const tooltip=el('div',null,'chart-tooltip');tooltip.id='allocation-tooltip';tooltip.setAttribute('role','tooltip');tooltip.hidden=true;
  // Normalize geometry so rounded percentages never leave a gap in the ring.
  const total=v.chart.reduce((sum,item)=>sum+Number(item.value),0);
  let cursor=0;
  v.chart.forEach((item,index)=>{
    const color=item.members?'#8792a2':colors[index];
    const description=item.name+' '+item.ticker+'：TWD '+fmt(item.value)+'，占比 '+item.weight+'%'+(item.members?'；包含 '+item.members.join('、'):'');
    const segment=document.createElementNS(svg.namespaceURI,'path');
    const angle=total>0?Number(item.value)/total*Math.PI*2:0;
    const point=(radius,a)=>[120+radius*Math.sin(a),120-radius*Math.cos(a)].join(' ');
    // Two arcs per edge also support a single holding's complete circle.
    const middle=cursor+angle/2,end=cursor+angle;
    segment.setAttribute('d','M '+point(119,cursor)+' A 119 119 0 0 1 '+point(119,middle)+' A 119 119 0 0 1 '+point(119,end)+' L '+point(85,end)+' A 85 85 0 0 0 '+point(85,middle)+' A 85 85 0 0 0 '+point(85,cursor)+' Z');
    cursor=end;segment.setAttribute('fill',color);segment.setAttribute('class','donut-segment');segment.setAttribute('tabindex','0');segment.setAttribute('aria-label',description);segment.setAttribute('aria-describedby',tooltip.id);
    svg.append(segment);
    const row=el('div',null,'legend-row');row.tabIndex=0;row.setAttribute('aria-label',description);
    const swatch=el('span',null,'swatch');swatch.style.background=color;
    const name=el('div',item.ticker);name.append(el('small',item.members?item.members.join('、'):item.name));
    const value=el('div',fmt(item.value),'right');value.append(el('small',item.weight+'%'));
    row.append(swatch,name,value);$('legend').append(row);
    const show=()=>{tooltip.textContent=description;tooltip.hidden=false;segment.classList.add('active');row.classList.add('active');};
    const hide=()=>{tooltip.hidden=true;segment.classList.remove('active');row.classList.remove('active');};
    [segment,row].forEach(target=>{target.addEventListener('pointerenter',show);target.addEventListener('pointerleave',hide);target.addEventListener('focus',show);target.addEventListener('blur',hide);target.addEventListener('keydown',event=>{if(event.key==='Escape')hide();});});
  });
  donut.append(svg,center,tooltip);$('chart').append(donut);
}
function renderDetails(){
  $('details').replaceChildren(); const rows=[...valuation.rows];rows.sort($('sort').value==='value'?(a,b)=>Number(b.twd_value??-1)-Number(a.twd_value??-1):(a,b)=>a.ticker.localeCompare(b.ticker));
  for(const r of rows){const tr=el('tr'),name=el('td',r.ticker);name.append(el('small',r.name));tr.append(name);[r.market==='TW'?'台股 · TWD':'美股 · USD',fmt(r.quantity),fmt(r.buy_price),r.market_value==null?'—':fmt(r.price),fmt(r.market_value_display),fmt(r.twd_value),fmt(r.cost),signed(r.profit),r.weight==null?'—':r.weight+'%'].forEach((value,i)=>tr.append(el('td',value,i===7?(r.profit?.startsWith('-')?'negative':'positive'):'')));const meta=el('td',r.failure_reason?'缺少可用價格':(r.quality_flags.map(f=>labels[f]||f).join('、')||'可用報價'));meta.append(el('small',`價格：${date(r.quote_time)}`),el('small',`取得：${date(r.received_at)}`),el('small',`${r.provider||'尚無來源'} · ${r.session==='closed'?'休市':r.session==='regular'?'一般交易時段':r.session||'時段未知'}`));tr.append(meta);$('details').append(tr);}
  if(!rows.length){const tr=el('tr'),td=el('td','尚無持股資料','empty-cell');td.colSpan=11;tr.append(td);$('details').append(tr);}
}
function saveStatus(text, error=false) { const status=$('save-status'); status.hidden=false; status.textContent=text; status.style.color=error?'#ad3e4a':'#237057'; status.style.whiteSpace='pre-line'; }
async function save(fxOnly=false){if(loading||!saved)return;loading=true;saveStatus('儲存中…');$('save').textContent='儲存中…';$('save').disabled=true;$('apply-fx').disabled=true;try{const fx=$('fx').value.trim(); const editing=JSON.stringify(draft);const p=await api('/api/portfolio','PUT',{revision:recoveredRevision??saved.revision,rows:fxOnly?saved.rows:draft.map(r=>({...r})),fx});saved=p;recoveredRevision=null;saveStatus(fxOnly?'匯率已保存。':'持股已保存。');if(!fxOnly&&editing===JSON.stringify(draft)) {draft=structuredClone(p.rows);dirty=$('fx').value.trim()!==fx;draftRender();}else if(fxOnly){dirty=JSON.stringify(draft)!==JSON.stringify(p.rows)||$('fx').value.trim()!==fx;}$('draft-state').textContent=dirty?'有未保存的修改 · 總覽仍使用已保存清單':'已保存 · 總覽使用此版本';$('draft-state').className=dirty?'dirty':'';savedRender();await loadValuation();message(fxOnly?'匯率已套用，已使用既有價格重新換算。':'持股已保存。可按「更新報價」取得新價格。',true);if(!fxOnly&&valuation&&valuation.coverage<valuation.count)refresh();}catch(e){saveStatus('儲存失敗，草稿仍保留。'+String.fromCharCode(10)+e.message,true);message(e.message);}finally{loading=false;$('save').textContent='儲存持股';$('save').disabled=false;$('apply-fx').disabled=false;}}
async function upload(sheet){if(!file)return;const current=file;$('confirm-import').disabled=true;try{const result=await api('/api/imports/preview?filename='+encodeURIComponent(current.name)+(sheet?'&sheet='+encodeURIComponent(sheet):''),'POST',current);if(file!==current)return;preview=result;$('filename').textContent=current.name;$('sheets').replaceChildren(...preview.sheets.map(name=>{const o=el('option',name);o.value=name;return o;}));$('sheets').value=preview.sheet;$('preview').replaceChildren();preview.rows.forEach((r,i)=>{const tr=el('tr');[String(i+2),r.ticker,r.quantity,r.buy_price].forEach(x=>tr.append(el('td',x)));$('preview').append(tr);});$('import-errors').textContent=preview.issues.map(x=>`第 ${x.row} 列 ${fieldLabel(x.field)}：${x.message}`).join('\n');const old=new Set(draft.map(r=>r.ticker.trim().toUpperCase())),next=new Set(preview.rows.map(r=>r.ticker));$('replace-note').textContent=`確認後將取代整份草稿：新增 ${[...next].filter(x=>!old.has(x)).length} 檔、移除 ${[...old].filter(x=>!next.has(x)).length} 檔。仍需點「儲存持股」才會保存。`;$('confirm-import').disabled=preview.issues.length>0;if(!$('import-dialog').open)$('import-dialog').showModal();}catch(e){message(e.message);}}
// The work now runs inside this request (D3), so the wait is the request itself. A job
// still comes back queued/running in one case: another instance holds a live lease, and
// then the existing poll is what follows it.
async function refresh(catalogOnly=false){if(!saved)return;$('refresh').disabled=true;$('job').textContent=catalogOnly?'正在更新官方股票清單，請保持分頁開啟…':'正在更新報價，請保持分頁開啟；工作在這個請求內完成，關閉分頁會中斷。';try{const job=await api(catalogOnly?'/api/catalog/refresh':'/api/portfolio/refresh','POST',{},true,false);if(['queued','running'].includes(job.status))return await watch(job.job_id);await settle(job);}catch(e){$('job').textContent='';$('refresh').disabled=false;message(e.message);}}
async function settle(job){$('job').textContent=job.message;$('refresh').disabled=false;if(job.portfolio_revision===saved.revision)await loadValuation();else message('先前版本的報價工作已完成；目前清單維持新版本，請再次更新報價。');}
async function watch(id){try{const job=await api('/api/jobs/'+id);if(['queued','running'].includes(job.status)){$('job').textContent=job.message;poll=setTimeout(()=>watch(id),1800);return;}await settle(job);}catch(e){$('refresh').disabled=false;message(e.message);}}
$('add').onclick=$('start-add').onclick=add;$('save').onclick=()=>save();$('apply-fx').onclick=()=>save(true);$('fx').oninput=setDirty;$('market').onchange=()=>loadValuation().catch(e=>message(e.message));$('sort').onchange=()=>valuation&&renderDetails();$('refresh').onclick=()=>refresh();
const catalogButton=el('button','更新股票清單','ghost');catalogButton.onclick=()=>refresh(true);$('editor').querySelector('.actions').prepend(catalogButton);
$('upload').onclick=()=>{if(saved)$('file').click();};$('file').onchange=()=>{file=$('file').files[0];if(!file)return;if(!file.name.toLowerCase().endsWith('.xlsx')||file.size>5*1024*1024){message('請選擇不超過 5 MiB 的 .xlsx 檔案。');return;}upload();};$('sheets').onchange=()=>upload($('sheets').value);
function closeImport(){$('import-dialog').close();file=null;preview=null;$('file').value='';}
$('cancel-import').onclick=$('close-import').onclick=closeImport;$('import-dialog').addEventListener('cancel',closeImport);$('confirm-import').onclick=()=>{if(!preview||preview.issues.length)return;draft=structuredClone(preview.rows);setDirty();draftRender();closeImport();$('editor').scrollIntoView({behavior:'smooth'});};
window.addEventListener('beforeunload',e=>{if(dirty&&!loginRedirecting){e.preventDefault();e.returnValue='';}});
(async()=>{try{token=(await api('/api/session')).token;saved=await api('/api/portfolio');draft=structuredClone(saved.rows);$('fx').value=saved.fx||'';savedRender();draftRender();const recovery=sessionStorage.getItem('portfolio-login-draft');if(recovery){const recovered=JSON.parse(recovery);draft=recovered.rows;recoveredRevision=recovered.revision;$('fx').value=recovered.fx;setDirty();draftRender();sessionStorage.removeItem('portfolio-login-draft');message(recovered.revision===saved.revision?'已恢復登入前的草稿，請確認後儲存。':'已恢復草稿，但已保存版本有變動；請核對內容後再儲存。');}await loadValuation();}catch(e){message(e.message+' 請重新整理頁面重試。');}})();
