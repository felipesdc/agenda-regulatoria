import {QueryUrl} from '../query-url';
import {DraftGuard} from '../draft-guard';
import {Component,inject,signal,OnInit,input,viewChild,ElementRef,Injector,afterNextRender} from '@angular/core';
import {HttpClient,HttpErrorResponse} from '@angular/common/http';
import {DatePipe} from '@angular/common';
import {firstValueFrom} from 'rxjs';
import {Commitments} from '../commitments/commitments';
import {Profile,Unit,Page,Occurrence} from '../commitments/types';
import {FocusTrap} from '../focus-trap';
type Bucket='overdue'|'upcoming'|'validation';
interface PendingPage extends Page<Occurrence>{as_of:string;counts:Record<Bucket,number>;bucket:Bucket;}
@Component({selector:'app-pending',standalone:true,imports:[DatePipe,Commitments,FocusTrap],templateUrl:'./pending.html'})
export class PendingCenter implements OnInit {
 profile=input.required<Profile>();units=input.required<Unit[]>();
 private drafts=inject(DraftGuard);private http=inject(HttpClient);private injector=inject(Injector);dialog=viewChild<ElementRef<HTMLDialogElement>>('dialog');
 data=signal<PendingPage|null>(null);bucket=signal<Bucket>('overdue');page=signal(1);busy=signal(false);error=signal('');selected=signal('');
 buckets:{key:Bucket;label:string;help:string}[]=[{key:'overdue',label:'Atrasados',help:'Em aberto, com vencimento anterior a hoje.'},{key:'upcoming',label:'Próximos 7 dias',help:'Em aberto, de hoje até hoje + 7 dias, inclusive.'},{key:'validation',label:'Aguardando validação',help:'Conclusões submetidas, ainda sem validação.'}];
 labels:Record<string,string>={pending:'Pendente',in_progress:'Em andamento',awaiting_validation:'Aguardando validação',rejected:'Rejeitado'};
 private url=new QueryUrl();private restoreQuery(params:Record<string,string>){this.data.set(null);this.bucket.set((params['bucket']||'overdue') as Bucket);this.page.set(Number(params['page']||1));}
 ngOnInit(){this.restoreQuery(this.url.read());this.url.watch(async params=>{this.restoreQuery(params);await this.load(this.bucket(),this.page(),true);},()=>this.busy());void this.load(this.bucket(),this.page(),true);}
 async load(bucket=this.bucket(),page=this.page(),replace=false){
  if(this.busy())return;this.busy.set(true);this.error.set('');
  try{let result:PendingPage;try{result=await this.fetch(bucket,page);}catch(e:unknown){if(e instanceof HttpErrorResponse&&e.status===404&&page>1){page=1;result=await this.fetch(bucket,page);}else throw e;}
   this.data.set(result);this.bucket.set(bucket);this.page.set(page);await this.url.write({bucket,page},replace);
  }catch{this.error.set('Não foi possível carregar as pendências. Tente atualizar novamente.');}finally{this.busy.set(false);void this.url.settled();}
 }
 private fetch(bucket:Bucket,page:number){return firstValueFrom(this.http.get<PendingPage>('/api/v1/pending-center/',{params:{bucket,page}}));}
 open(id:string){this.selected.set(id);afterNextRender(()=>this.dialog()?.nativeElement.showModal(),{injector:this.injector});}
 close(){if(!this.drafts.confirmDiscard())return;this.dialog()?.nativeElement.close();this.selected.set('');void this.load(this.bucket(),this.page(),true);}
}
