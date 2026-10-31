import {DestroyRef,inject} from '@angular/core';
import {ActivatedRoute,Params,Router} from '@angular/router';
const statuses=['pending','in_progress','awaiting_validation','completed','rejected','cancelled'];
const frequencies=['once','daily','weekly','fortnightly','monthly','bimonthly','quarterly','semiannual','yearly','custom'];
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const enums:Record<string,string[]>={status:statuses,priority:['low','normal','high','critical'],periodicity:frequencies,scale:['month','week','year'],group_by:['unit','entity','assignee','periodicity'],bucket:['overdue','upcoming','validation']};
const common=['q','unit','entity','category','requester','assignee','status','priority','periodicity','date_start','date_end'];
const lists=['q','status','overdue','page'];
export const queryKeys:Record<string,string[]>={
 '/compromissos':lists,'/minhas-atribuicoes':lists,'/validacoes':lists,
 '/auditoria':['record_id','page'], '/calendario':[...common,'scale','anchor'],
 '/relatorios':[...common,'overdue','page','group_page','group_by'],
 '/notificacoes':['q','status','page'],'/pendencias':['bucket','page'],
};
export function cleanQuery(path:string,params:Params):Record<string,string>{
 const result:Record<string,string>={};
 for(const key of queryKeys[path]||[]){const value=params[key];if(typeof value!=='string'&&typeof value!=='number'&&typeof value!=='boolean')continue;const text=String(value);
  if(!text||(key==='bucket'&&text==='overdue')||(key==='scale'&&text==='month')||(key==='group_by'&&text==='unit'))continue;
  if(['page','group_page'].includes(key)){if(/^[1-9]\d{0,5}$/.test(text)&&text!=='1')result[key]=text;continue;}
  if(key==='overdue'){if(text==='true')result[key]=text;continue;}
  if(['unit','entity','category','requester','assignee'].includes(key)){if(uuid.test(text))result[key]=text;continue;}
  if(['anchor','date_start','date_end'].includes(key)){if(/^\d{4}-\d{2}-\d{2}$/.test(text)&&!isNaN(Date.parse(text))&&new Date(text).toISOString().slice(0,10)===text)result[key]=text;continue;}
  const choices=path==='/notificacoes'&&key==='status'?['pending','sending','retry','accepted','failed','skipped','unknown']:enums[key];
  if(choices){if(choices.includes(text))result[key]=text;continue;}
  if(text.length<=200&&!/[\u0000-\u001f\u007f]/.test(text))result[key]=text;
 }
 return result;
}
const keyOf=(params:Params)=>JSON.stringify(Object.entries(params).sort(([a],[b])=>a.localeCompare(b)));
// One instance per screen. Browser history restores applied queries after any current request settles.
export class QueryUrl {
 private router=inject(Router);private route=inject(ActivatedRoute);private destroy=inject(DestroyRef);
 private path='/'+this.route.snapshot.pathFromRoot.flatMap(snapshot=>snapshot.url.map(segment=>segment.path)).join('/');private seen=keyOf(this.route.snapshot.queryParams);private pending:Params|null=null;private processing=false;private dead=false;
 private restore:((params:Record<string,string>)=>Promise<void>)|null=null;private busy:()=>boolean=()=>false;
 private deferred:Params|null=null;
 constructor(){this.destroy.onDestroy(()=>{this.dead=true;});}
 hasQuery(){return Object.keys(this.route.snapshot.queryParams).length>0;}
 read(){return cleanQuery(this.path,this.route.snapshot.queryParams);}
 watch(restore:(params:Record<string,string>)=>Promise<void>,busy:()=>boolean){this.restore=restore;this.busy=busy;const subscription=this.route.queryParams.subscribe(params=>{const key=keyOf(params);if(key===this.seen)return;this.seen=key;this.pending=params;void this.settled();});this.destroy.onDestroy(()=>subscription.unsubscribe());}
 async write(params:Params,replace=false){
  if(this.dead)return;const navigation=this.router.getCurrentNavigation();if(navigation&&(navigation.trigger!=='imperative'||this.router.serializeUrl(navigation.finalUrl||navigation.extractedUrl).split(/[?#]/)[0]!==this.path))return;const clean=cleanQuery(this.path,params);
  if(this.processing){this.deferred=clean;return;}
  if(this.pending)return;
  if(keyOf(clean)===keyOf(this.route.snapshot.queryParams))return;
  this.seen=keyOf(clean);
  await this.router.navigate([],{relativeTo:this.route,queryParams:clean,replaceUrl:replace,preserveFragment:false});
 }
 async settled(){
  if(this.dead||this.processing||this.busy()||!this.pending||!this.restore)return;
  this.processing=true;const params=this.pending;this.pending=null;
  try{await this.restore(cleanQuery(this.path,params));}finally{this.processing=false;const deferred=this.deferred;this.deferred=null;if(!this.pending&&deferred)await this.write(deferred,true);if(this.pending)void this.settled();}
 }
}
