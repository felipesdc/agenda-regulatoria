import {cleanQuery} from './query-url';
import {Injectable,inject,signal} from '@angular/core';
import {HttpClient,HttpErrorResponse,HttpInterceptorFn} from '@angular/common/http';
import {Router} from '@angular/router';
import {catchError,from,mergeMap,throwError,firstValueFrom} from 'rxjs';
import {Profile,Unit,Page} from './commitments/types';
import {CommitmentQueryStore} from './commitments/query-state';
export interface SessionProfile extends Profile {environment:string;}
@Injectable({providedIn:'root'})
export class Session {
 private http=inject(HttpClient);private queries=inject(CommitmentQueryStore);
 profile=signal<SessionProfile|null>(null);units=signal<Unit[]>([]);error=signal('');
 private pending:Promise<boolean>|null=null;
 clear(){this.profile.set(null);this.units.set([]);this.queries.clear();}
 async refresh(force=false):Promise<boolean>{
  if(this.pending){if(!force)return this.pending;await this.pending;}
  this.pending=this.check();try{return await this.pending;}finally{this.pending=null;}
 }
 private async check(){try{
  const profile=await firstValueFrom(this.http.get<SessionProfile>('/api/v1/auth/me/'));
  let path='/api/v1/units/';const units:Unit[]=[];
  while(path){const page=await firstValueFrom(this.http.get<Page<Unit>>(path));units.push(...page.results);path=page.next?new URL(page.next,location.origin).pathname+new URL(page.next,location.origin).search:'';}
  if(this.profile()?.id!==profile.id)this.queries.clear();
  this.units.set(units);this.profile.set(profile);this.error.set('');return true;
 }catch(e){this.clear();this.error.set(e instanceof HttpErrorResponse&&[401,403].includes(e.status)?'':'Não foi possível verificar o acesso. Tente entrar novamente.');return false;}}
}
// A business permission denial must not log the user out. Check the actual session first.
export const sessionExpiryInterceptor:HttpInterceptorFn=(request,next)=>{
 const session=inject(Session),router=inject(Router);
 return next(request).pipe(catchError(error=>{
  if(!(error instanceof HttpErrorResponse)||![401,403].includes(error.status)||request.url.startsWith('/api/v1/auth/')||request.url.startsWith('/api/v1/units/')||!session.profile())return throwError(()=>error);
  const returnTo=router.url;
  return from(session.refresh()).pipe(mergeMap(valid=>{if(!valid)void router.navigate(['/entrar'],{queryParams:{returnTo:safeReturn(returnTo)},replaceUrl:true});return throwError(()=>error);}));
 }));
};
const paths=['/pendencias','/painel','/relatorios','/calendario','/compromissos','/minhas-atribuicoes','/validacoes','/campos-personalizados','/auditoria','/unidades','/notificacoes','/perfil'];
export const occurrenceId=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function safeReturn(value:unknown):string {
 if(typeof value!=='string'||!value.startsWith('/')||value.startsWith('//'))return '/painel';
 try{const url=new URL(value,'https://agenda.invalid');if(url.origin!=='https://agenda.invalid'||url.hash)return '/painel';
  if(!paths.includes(url.pathname)&&!new RegExp('^/compromissos/'+occurrenceId.source.slice(1,-1)+'$','i').test(url.pathname))return '/painel';
  const params:Record<string,string|string[]>={};url.searchParams.forEach((_,name)=>{const values=url.searchParams.getAll(name);params[name]=values.length===1?values[0]:values;});
  const query=new URLSearchParams(cleanQuery(url.pathname,params)).toString();return url.pathname+(query?'?'+query:'');
 }catch{return '/painel';}
}
