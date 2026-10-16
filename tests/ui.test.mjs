import test from 'node:test';
import assert from 'node:assert/strict';
import {csvCell,csvExport,errorMessage,validatedSteps,getRevision,assertCurrent,invalidate,action,api}from '../app/static/common.js';

test('CSV export neutralizes formula-like text without changing numeric negatives',()=>{
 assert.equal(csvCell('=SUM(A1:A2)'), '"\'=SUM(A1:A2)"');
 assert.equal(csvCell('  +1'), '"\'  +1"');
 assert.equal(csvCell('-3'),'"\'-3"');
 assert.equal(csvCell(-3),'"-3"');
 assert.equal(csvCell('a,"b"'),'"a,""b"""');
 assert.equal(csvExport(['name'],[{name:'<script>alert(1)</script>'}]),'"name"\r\n"<script>alert(1)</script>"');
});
test('builder only accepts supported declarative operations',()=>{
 assert.throws(()=>validatedSteps([{op:'shell',params:{command:'x'}}]),/Unsupported/);
 assert.throws(()=>validatedSteps(Array.from({length:50},()=>({op:'select',params:{}}))),/49/);
 assert.deepEqual(validatedSteps([{op:'aggregate',params:{operation:'count'}}]),[{op:'aggregate',params:{operation:'count'}}]);
});
test('validation errors show the input location and useful message',()=>{
 assert.equal(errorMessage([{loc:['body','events',2,'timestamp'],msg:'Invalid timestamp'}]),'body.events.2.timestamp: Invalid timestamp');
});
function fakeDocument(){const nodes=new Map();const make=()=>({disabled:false,textContent:'',className:'',replaceChildren(...children){this.children=children;}});for(const id of ['status','run','export-report','print','results','technical','input']){const n=make();n.id=id;nodes.set(id,n);}nodes.get('export-report').disabled=true;nodes.get('print').disabled=true;global.document={getElementById:id=>nodes.get(id),createElement:()=>make(),querySelectorAll:()=>[...nodes.values()].filter(n=>!['status','results','technical'].includes(n.id))};return nodes;}
test('a delayed result is rejected after input generation changes',()=>{
 fakeDocument();const revision=getRevision();invalidate();assert.throws(()=>assertCurrent(revision),/Inputs changed/);assert.doesNotThrow(()=>assertCurrent(getRevision()));
});
test('pending work locks controls and restores them after failure without stale exports',async()=>{
 const nodes=fakeDocument();let resume;const pending=new Promise(resolve=>resume=resolve);const call=action(async()=>{assert.equal(nodes.get('input').disabled,true);await pending;throw new Error('Synthetic validation failure');});
 assert.equal(nodes.get('run').disabled,true);assert.equal(nodes.get('input').disabled,true);resume();await call;assert.equal(nodes.get('input').disabled,false);assert.equal(nodes.get('run').disabled,false);assert.equal(nodes.get('export-report').disabled,true);assert.match(nodes.get('status').textContent,/Synthetic validation failure/);
});
test('non-200 API response becomes a validation failure',async()=>{
 global.fetch=async()=>({ok:false,json:async()=>({detail:[{loc:['body','csv_text'],msg:'CSV quoting invalid'}]})});
 await assert.rejects(()=>api('/csv/preview',{csv_text:'bad'}),/body.csv_text: CSV quoting invalid/);
});

// Execute the real application event handlers with a small DOM fixture and deferred I/O.
// These are frontend state tests; they do not claim full browser rendering coverage.
import {fileURLToPath} from 'node:url';
const appSlug=fileURLToPath(new URL('..',import.meta.url)).split('/').filter(Boolean).at(-1);
let importSequence=0;
function applicationDOM(){
 const nodes=new Map();
 class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.disabled=false;this.textContent='';this.value='';this.files=[];this.style={};this.listeners={};this.checked=false;}
  set id(value){this._id=value;nodes.set(value,this);}get id(){return this._id;}
  append(...items){this.children.push(...items);if(this.tagName==='select'&&this.value===''&&items[0]?.value!==undefined)this.value=String(items[0].value);}
  replaceChildren(...items){this.textContent="";this.children=[];this.append(...items);}
  after(...items){this.siblings=items;}
  addEventListener(type,handler){this.listeners[type]=handler;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(n.tagName==='input'&&(selector!=='input:checked'||n.checked)?[n]:[]),...n.querySelectorAll(selector)]);}
 }
 const get=id=>{if(!nodes.has(id)){const node=new Element();node.id=id;}return nodes.get(id);};
 global.document={getElementById:get,createElement:tag=>new Element(tag),querySelectorAll:()=>[...nodes.values()]};
 return {nodes,get};
}
async function realApplication(){const fixture=applicationDOM();await import('../app/static/app.js?handler-test='+ ++importSequence);return fixture;}
function markEdited(fixture){
 if(appSlug==='ai-readiness-auditor'){fixture.get('score-strategy').value='1';fixture.get('questions').listeners.input();}
 else {const field=appSlug==='mlops-doctor'?'train':'csv';fixture.get(field).value='new_id,new_value\nnew,99';fixture.get(field).oninput();}
}
function inputValue(fixture){return fixture.get(appSlug==='ai-readiness-auditor'?'score-strategy':appSlug==='mlops-doctor'?'train':'csv').value;}
function requestConfiguration(){
 if(appSlug==='ai-readiness-auditor')return {dimensions:Object.fromEntries(['strategy','data','governance','people','infrastructure'].map(k=>[k,{score:5,evidence:['Synthetic delayed import']}]))};
 if(appSlug==='mlops-doctor')return {train_csv:'old,x,y\na,1,0',validation_csv:'old,x,y\nb,2,1',schema:{old:'string',x:'number',y:'number'},features:['x'],id_column:'old',target:'y'};
 if(appSlug==='processminer-ai')return {csv_text:'case,activity,time\nold,Start,2026-01-01T00:00:00Z',case_column:'case',activity_column:'activity',timestamp_column:'time'};
 return {csv_text:'team,value\nold,1',schema:{team:'string',value:'number'},steps:[]};
}
function previewResponse(){return {ok:true,json:async()=>({columns:['old','x','y'],row_count:1,preview:[{old:'old',x:'1',y:'0'}]})};}

test('actual configuration-import handler cannot overwrite edits after delayed file read',async()=>{
 const fixture=await realApplication();let release;
 fixture.get('config-file').files=[{size:50,text:()=>new Promise(resolve=>release=resolve)}];
 const pending=fixture.get('config-file').onchange();
 markEdited(fixture);const newest=inputValue(fixture),badge=fixture.get('data-origin').textContent;
 release(JSON.stringify(requestConfiguration()));await pending;
 assert.equal(inputValue(fixture),newest);
 assert.equal(fixture.get('data-origin').textContent,badge);
 assert.equal(fixture.get('export-report').disabled,true);
});

if(appSlug!=='ai-readiness-auditor'){
 test('actual preview handler discards delayed schema and mapping after an edit',async()=>{
  const fixture=await realApplication();const releases=[];
  global.fetch=()=>new Promise(resolve=>releases.push(resolve));
  fixture.get('csv').value='old,x,y\nold,1,0';fixture.get('train').value='old,x,y\nold,1,0';fixture.get('validation').value='old,x,y\nother,2,0';
  fixture.get('preview-data').textContent='Current preview sentinel';fixture.get('schema').textContent='Current schema sentinel';fixture.get('case-column').value='new_id';
  const pending=fixture.get('preview').onclick();assert.ok(releases.length>=1);markEdited(fixture);const newest=inputValue(fixture);
  for(const release of releases)release(previewResponse());await pending;
  assert.equal(inputValue(fixture),newest);
  assert.equal(fixture.get('preview-data').textContent,'Current preview sentinel');
  assert.equal(fixture.get('schema').textContent,'Current schema sentinel');
  assert.equal(fixture.get('case-column').value,'new_id');
 });
 test('actual synthetic-example completion cannot label edited input as synthetic',async()=>{
  const fixture=await realApplication();const releases=[];global.fetch=()=>new Promise(resolve=>releases.push(resolve));
  const pending=fixture.get('example').onclick();assert.ok(releases.length>=1);markEdited(fixture);const newest=inputValue(fixture);
  for(const release of releases)release(previewResponse());await pending;
  assert.equal(inputValue(fixture),newest);
  assert.match(fixture.get('data-origin').textContent,/Your input/);
  assert.doesNotMatch(fixture.get('data-origin').textContent,/Synthetic/);
 });
 test('actual CSV-file handler cannot overwrite edits after delayed text read',async()=>{
  const fixture=await realApplication();let release;let calls=0;global.fetch=async()=>{calls++;return previewResponse();};
  const fileID=appSlug==='mlops-doctor'?'train-file':'csv-file';fixture.get(fileID).files=[{size:50,text:()=>new Promise(resolve=>release=resolve)}];
  const pending=fixture.get(fileID).onchange();markEdited(fixture);const newest=inputValue(fixture);release('old,x,y\nold,1,0');await pending;
  assert.equal(inputValue(fixture),newest);assert.equal(calls,0);
 });
}
