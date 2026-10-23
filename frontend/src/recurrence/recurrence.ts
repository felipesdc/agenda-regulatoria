import {Component, input, output, inject, effect, DestroyRef, signal} from '@angular/core';
import {ReactiveFormsModule, FormBuilder, Validators} from '@angular/forms';
import {DatePipe} from '@angular/common';
import {HttpClient, HttpErrorResponse} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
export interface Rule {frequency:string;calendar:string;start:string;end:string;count:number;month_mode:string;month_day?:number;ordinal:number;weekday:number;interval:number;interval_unit:string;adjustment:string;exceptions:string[];}
export interface RuleState {enabled:boolean;rule:Rule|null;}
export const frequencies=[['once','Único'],['daily','Diário'],['weekly','Semanal'],['fortnightly','Quinzenal'],['monthly','Mensal'],['bimonthly','Bimestral'],['quarterly','Trimestral'],['semiannual','Semestral'],['yearly','Anual'],['custom','Intervalo personalizado']];
@Component({selector:'app-recurrence',standalone:true,imports:[ReactiveFormsModule,DatePipe],templateUrl:'./recurrence.html'})
export class Recurrence {
 start=input('');editableStart=input(false);retainRule=input(false);ruleChanged=output<RuleState>();
 private fb=inject(FormBuilder);private http=inject(HttpClient);private destroy=inject(DestroyRef);
 frequencies=frequencies;dates=signal<{scheduled_date:string;due_date:string}[]>([]);error=signal('');busy=signal(false);
 form=this.fb.nonNullable.group({frequency:['once'],calendar:['institution'],start:['',Validators.required],end:['',Validators.required],count:[12,[Validators.required,Validators.min(1),Validators.max(1000)]],month_mode:['day'],month_day:[0,[Validators.min(0),Validators.max(31)]],ordinal:[1,[Validators.min(1),Validators.max(31)]],weekday:[0],interval:[1,[Validators.min(1),Validators.max(365)]],interval_unit:['days'],adjustment:['none'],exceptions:['']});
 constructor(){this.form.valueChanges.pipe(takeUntilDestroyed(this.destroy)).subscribe(()=>{this.dates.set([]);this.emit();});effect(()=>{const start=this.start();if(start&&!this.editableStart()){this.form.patchValue({start,end:this.form.controls.end.value||start.slice(0,4)+'-12-31'});}this.emit();});}
 private state():RuleState{const f=this.form.getRawValue();if(f.frequency==='once')return {enabled:false,rule:null};if(this.form.invalid||f.end<f.start)return {enabled:true,rule:null};const {exceptions,month_day,...base}=f;return {enabled:true,rule:{...base,...(month_day?{month_day}:{}),exceptions:exceptions.split(/[\s,;]+/).filter(Boolean)}};}
 private emit(){this.ruleChanged.emit(this.state());}
 async preview(){const rule=this.state().rule;if(!rule)return;this.busy.set(true);this.error.set('');try{const response=await firstValueFrom(this.http.post<{dates:{scheduled_date:string;due_date:string}[]}>('/api/v1/recurrence/preview/',{rule,through:rule.end}));this.dates.set(response.dates);}catch(e){this.error.set(e instanceof HttpErrorResponse?JSON.stringify(e.error):'Não foi possível consultar as datas.');}finally{this.busy.set(false);}}
}
