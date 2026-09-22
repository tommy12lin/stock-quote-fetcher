const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/stock_quote_fetcher/static/app.js','utf8').split('function setDirty()')[0];
function setup(responses) {
  const calls=[], storage=new Map(); let reloads=0;
  const context=vm.createContext({File:class File{},TypeError,Date,document:{getElementById:()=>({value:'30'})},
    sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    window:{location:{reload:()=>reloads++}},
    fetch:async(path,options)=>{calls.push({path,options});const next=responses.shift();if(next instanceof Error)throw next;return next;}});
  vm.runInContext(source,context);
  return {context,calls,storage,reloads:()=>reloads,run:code=>vm.runInContext(code,context)};
}
const response=(status,data,type='basic')=>({status,ok:status<400,type,headers:{get:()=> 'application/json'},json:async()=>data});
test('expired token renews once then resends identical write',async()=>{
 const s=setup([response(403,{code:'session_expired'}),response(200,{token:'renewed'}),response(200,{ok:true})]);
 await s.run("api('/api/portfolio','PUT',{revision:1})");
 assert.equal(s.calls.length,3);assert.equal(s.calls[1].path,'/api/session');
 assert.equal(s.calls[0].options.body,s.calls[2].options.body);
 assert.equal(s.calls[2].options.headers['X-Portfolio-Token'],'renewed');
});
test('second denial stops retry',async()=>{
 const s=setup([response(401,{code:'unauthorized'}),response(200,{token:'new'}),response(401,{code:'unauthorized',message:'denied'})]);
 await assert.rejects(s.run("api('/api/portfolio')"),/denied/);assert.equal(s.calls.length,3);
});
test('origin denial and conflict do not retry',async()=>{
 for(const [status,code] of [[403,'origin_denied'],[409,'revision_conflict']]){
 const s=setup([response(status,{code,message:'denied'})]);
 await assert.rejects(s.run("api('/api/portfolio','PUT',{})"));assert.equal(s.calls.length,1);
 }
});
test('redirect preserves dirty draft and reloads without resending write',async()=>{
 const s=setup([response(0,{},'opaqueredirect')]);
 s.run("dirty=true;draft=[{ticker:'TEST'}];saved={revision:2}");
 await assert.rejects(s.run("api('/api/portfolio','PUT',{})"));
 assert.equal(s.reloads(),1);assert.equal(s.calls.length,1);
 assert.equal(JSON.parse(s.storage.get('portfolio-login-draft')).revision,2);
 assert.equal(s.calls[0].options.redirect,'manual');
});
test('network error triggers at most one reload in cooldown and no write replay',async()=>{
 const s=setup([new TypeError('network'),new TypeError('network')]);
 await assert.rejects(s.run("api('/api/portfolio','PUT',{})"));
 s.run('loginRedirecting=false');
 await assert.rejects(s.run("api('/api/portfolio','PUT',{})"));
 assert.equal(s.reloads(),1);assert.equal(s.calls.length,2);
});
test('session endpoint failure does not recurse',async()=>{
 const s=setup([response(401,{code:'unauthorized'}),response(401,{code:'unauthorized',message:'denied'})]);
 await assert.rejects(s.run("api('/api/portfolio')"),/denied/);assert.equal(s.calls.length,2);
});
test('a cut-short long refresh reports the cut instead of reloading',async()=>{
 for(const failure of [new TypeError('network'),response(0,{},'opaqueredirect')]){
 const s=setup([failure]);
 await assert.rejects(s.run("api('/api/portfolio/refresh','POST',{},true,false)"),/連線時限/);
 assert.equal(s.reloads(),0);assert.equal(s.calls.length,1);
 }
});
test('a refresh cut short leaves no login draft behind',async()=>{
 const s=setup([new TypeError('network')]);
 s.run("dirty=true;draft=[{ticker:'TEST'}];saved={revision:2}");
 await assert.rejects(s.run("api('/api/portfolio/refresh','POST',{},true,false)"));
 assert.equal(s.storage.get('portfolio-login-draft'),undefined);
});
