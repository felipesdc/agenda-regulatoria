import {Component,input,output,inject,signal} from '@angular/core';
import {DatePipe} from '@angular/common';
import {HttpClient,HttpErrorResponse} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
export interface Evidence {id:string;filename:string;media_type:string;size:number;sha256:string;inspection:string;uploaded_at:string;withdrawn:boolean;withdrawn_at:string|null;withdrawn_by:string|null;withdrawal_reason:string;can_withdraw:boolean;}
@Component({selector:'app-evidence',standalone:true,imports:[DatePipe],template:`
<section class="evidence-panel" aria-label="Anexos comprobatórios"><h4>Anexos comprobatórios</h4>
<p class="error" role="alert">{{error()}}</p><p role="status">{{message()}}</p>
@for(file of files();track file.id){<article class="evidence-file"><strong>{{file.filename}}</strong><small>{{(file.size/1024).toFixed(1)}} KB · {{file.uploaded_at|date:'dd/MM/yyyy HH:mm'}}</small><small>{{file.inspection==='development:structural_only'?'Ambiente local: formato validado, sem inspeção antivírus.':'Inspeção antivírus registrada.'}}</small><details><summary>Integridade SHA-256</summary><code>{{file.sha256}}</code></details>
@if(file.withdrawn){<p>Retirado por {{file.withdrawn_by}} em {{file.withdrawn_at|date:'dd/MM/yyyy HH:mm'}}: {{file.withdrawal_reason}}</p>}@else{<div class="workflow-buttons"><button type="button" (click)="download(file)" [disabled]="busy()">Baixar {{file.filename}}</button>@if(file.can_withdraw){<button type="button" (click)="selected.set(file.id)" [disabled]="busy()">Retirar {{file.filename}}</button>}</div>}
@if(selected()===file.id){<label [for]="'withdraw-'+file.id">Justificativa da retirada</label><textarea [id]="'withdraw-'+file.id" [value]="reason()" [readOnly]="busy()" (input)="reason.set($any($event.target).value)" maxlength="1000"></textarea><p>O arquivo será retirado do acesso normal. O original e seu histórico serão preservados.</p><button type="button" (click)="withdraw(file)" [disabled]="busy()||!reason().trim()">Confirmar retirada</button><button type="button" (click)="selected.set('');reason.set('')" [disabled]="busy()">Cancelar retirada</button>}
</article>}
</section>`})
export class EvidencePanel {
 files=input<Evidence[]>([]);changed=output<void>();private http=inject(HttpClient);busy=signal(false);error=signal('');message=signal('');selected=signal('');reason=signal('');
 private async guard(work:()=>Promise<void>){if(this.busy())return;this.busy.set(true);this.error.set('');this.message.set('');try{await work();}catch(e){if(e instanceof HttpErrorResponse&&e.error instanceof Blob){this.error.set('Não foi possível baixar o anexo. Verifique seu acesso e tente novamente.');}else this.error.set(e instanceof HttpErrorResponse?Object.values(e.error||{}).flat().join(' '):'Não foi possível concluir a operação.');}finally{this.busy.set(false);}}
 async download(file:Evidence){await this.guard(async()=>{const bytes=await firstValueFrom(this.http.get('/api/v1/evidence/'+file.id+'/download/',{responseType:'blob'}));const url=URL.createObjectURL(bytes),anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;document.body.appendChild(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);this.message.set('Download autorizado e registrado.');});}
 async withdraw(file:Evidence){if(!this.reason().trim())return;await this.guard(async()=>{await firstValueFrom(this.http.post('/api/v1/evidence/'+file.id+'/withdraw/',{reason:this.reason()}));this.selected.set('');this.reason.set('');this.changed.emit();});}
}
