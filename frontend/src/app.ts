import {Reports} from './reports/reports';
import {CustomFieldsAdmin} from './customfields/admin';
import { Component, inject, signal, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { Notifications } from './notifications/notifications';
import { Calendar } from './calendar/calendar';
import { Commitments } from './commitments/commitments';
interface Membership { unit_id: string; unit__name: string; role: 'requester' | 'executor'; }
interface Profile { environment:string;id: string; username: string; name: string; administrator: boolean; memberships: Membership[]; }
interface Unit { id: string; name: string; code: string; }
@Component({selector:'app-root', standalone:true, imports:[ReactiveFormsModule,Commitments,Calendar,Notifications,CustomFieldsAdmin,Reports], templateUrl:'./app.html'})
export class App implements OnInit {
 linkedOccurrence=signal(new URLSearchParams(location.search).get('occurrence')||'');
 openNotification(id:string){this.linkedOccurrence.set(id);this.section.set('linked');}
 private http=inject(HttpClient); private fb=inject(FormBuilder);
 profile=signal<Profile|null>(null); units=signal<Unit[]>([]); busy=signal(false); error=signal(''); section=signal('overview');
 form=this.fb.nonNullable.group({username:['',Validators.required],password:['',Validators.required]});
 async ngOnInit(){try{await firstValueFrom(this.http.get('/api/v1/auth/csrf/')); await this.load();}catch{ /* Unauthenticated startup shows login. */ }}
 private async load(){const p=await firstValueFrom(this.http.get<Profile>('/api/v1/auth/me/')); const u=await firstValueFrom(this.http.get<{results:Unit[]}>('/api/v1/units/')); this.profile.set(p);this.units.set(u.results);if(this.linkedOccurrence())this.section.set("linked");}
 async login(){if(this.form.invalid||this.busy())return;this.busy.set(true);this.error.set('');try{await firstValueFrom(this.http.get('/api/v1/auth/csrf/'));await firstValueFrom(this.http.post('/api/v1/auth/login/',this.form.getRawValue()));await this.load();this.form.controls.password.reset();}catch{this.error.set('Não foi possível entrar. Verifique as credenciais ou tente novamente mais tarde.');}finally{this.busy.set(false);}}
 async logout(){this.busy.set(true);try{await firstValueFrom(this.http.post('/api/v1/auth/logout/',{}));this.profile.set(null);this.units.set([]);this.section.set('overview');this.linkedOccurrence.set('');history.replaceState(null,'',location.pathname);}catch{this.error.set('Não foi possível encerrar a sessão. Tente novamente.');}finally{this.busy.set(false);}}
}
