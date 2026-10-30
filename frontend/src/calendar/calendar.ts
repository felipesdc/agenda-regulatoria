import {FocusTrap} from '../focus-trap';
import {Component,input,signal,computed,inject,OnInit,viewChild,ElementRef} from '@angular/core';
import {HttpClient,HttpParams,HttpErrorResponse} from '@angular/common/http';
import {FormBuilder,ReactiveFormsModule} from '@angular/forms';
import {firstValueFrom} from 'rxjs';
import {Profile,Unit,Catalog,Person,Page,Occurrence} from '../commitments/types';
import {Commitments} from '../commitments/commitments';
import {Scale,range,monthGrid,shift,weekStart,navigate,dateOf} from './date-utils';
type CalendarEvent=Pick<Occurrence,'id'|'identifier'|'title'|'due_date'|'status'|'priority'|'overdue'>;
interface CalendarDay {date:string;total:number;status_counts:Record<string,number>;events:CalendarEvent[];}
interface CalendarResponse {date_start:string;date_end:string;total:number;days:CalendarDay[];}
interface Favorite {id:string;name:string;filters:Record<string,string>;}
@Component({selector:'app-calendar',standalone:true,imports:[FocusTrap,ReactiveFormsModule,Commitments],templateUrl:'./calendar.html'})
export class Calendar implements OnInit {
 profile=input.required<Profile>();units=input.required<Unit[]>();private http=inject(HttpClient);private fb=inject(FormBuilder);
 scale=signal<Scale>('month');anchor=signal(this.today());busy=signal(false);error=signal('');message=signal('');total=signal(0);days=signal<Record<string,CalendarDay>>({});
 entities=signal<Catalog[]>([]);categories=signal<Catalog[]>([]);requesters=signal<Person[]>([]);assignees=signal<Person[]>([]);favorites=signal<Favorite[]>([]);
 canCreate=computed(()=>this.profile().administrator||this.profile().memberships.some(m=>m.role==='requester'));creatingDate=signal('');
 selectedOccurrence=signal<string|null>(null);selectedDay=signal('');dayRows=signal<Occurrence[]>([]);dayCount=signal(0);dayPage=signal(1);dayBusy=signal(false);
 createDialog=viewChild<ElementRef<HTMLDialogElement>>('createDialog');
 detailDialog=viewChild<ElementRef<HTMLDialogElement>>('detailDialog');dayDialog=viewChild<ElementRef<HTMLDialogElement>>('dayDialog');
 weekdays=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];labels:Record<string,string>={pending:'Pendente',in_progress:'Em andamento',awaiting_validation:'Aguardando validação',completed:'Concluído',rejected:'Rejeitado',cancelled:'Cancelado'};
 filters=this.fb.nonNullable.group({q:[''],entity:[''],unit:[''],requester:[''],assignee:[''],category:[''],priority:[''],status:[''],periodicity:[''],date_start:[''],date_end:['']});
 favoriteForm=this.fb.nonNullable.group({name:[''],selected:['']});
 grid=computed(()=>monthGrid(this.anchor()));week=computed(()=>Array.from({length:7},(_,i)=>shift(weekStart(this.anchor()),i)));
 months=computed(()=>Array.from({length:12},(_,i)=>{const first=this.anchor().slice(0,4)+'-'+String(i+1).padStart(2,'0')+'-01';return{first,days:monthGrid(first),total:Object.values(this.days()).filter(d=>d.date.slice(0,7)===first.slice(0,7)).reduce((sum,d)=>sum+d.total,0)};}));
 title=computed(()=>this.scale()==='year'?this.anchor().slice(0,4):this.scale()==='week'?this.format(this.week()[0])+' — '+this.format(this.week()[6]):new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric',timeZone:'UTC'}).format(dateOf(this.anchor())));
 today(){return new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});}
 format(value:string){return new Intl.DateTimeFormat('pt-BR',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(dateOf(value));}
 monthName(value:string){return new Intl.DateTimeFormat('pt-BR',{month:'long',timeZone:'UTC'}).format(dateOf(value));}
 day(value:string):CalendarDay|undefined{return this.days()[value];}
 isToday(value:string):boolean{return value===this.today();}
 dayNumber(value:string){return Number(value.slice(8));}
 private async all<T>(path:string){const rows:T[]=[];while(path){const page=await firstValueFrom(this.http.get<Page<T>>(path));rows.push(...page.results);path=page.next?new URL(page.next,location.origin).pathname+new URL(page.next,location.origin).search:'';}return rows;}
 async ngOnInit(){try{const [entities,categories,people,favorites]=await Promise.all([this.all<Catalog>('/api/v1/entities/'),this.all<Catalog>('/api/v1/categories/'),firstValueFrom(this.http.get<{requesters:Person[];assignees:Person[]}>('/api/v1/calendar/people/')),this.all<Favorite>('/api/v1/calendar-favorites/')]);this.entities.set(entities.filter(e=>e.active));this.categories.set(categories.filter(c=>c.active));this.requesters.set(people.requesters);this.assignees.set(people.assignees);this.favorites.set(favorites);}catch(e){this.fail(e);}await this.load();}
 private fail(e:unknown){const data=e instanceof HttpErrorResponse?e.error:null;this.error.set(data&&typeof data==='object'?Object.values(data).flat().join(' '):'Não foi possível carregar o calendário. Tente novamente.');}
 private params(start:string,end:string){const values=this.filters.getRawValue();let p=new HttpParams().set('date_start',start).set('date_end',end);for(const [key,value] of Object.entries(values))if(value&&!['date_start','date_end'].includes(key))p=p.set(key,value);return p;}
 async load(){if(this.busy())return;this.busy.set(true);this.error.set('');this.days.set({});this.total.set(0);try{let[start,end]=range(this.anchor(),this.scale());const f=this.filters.getRawValue();if(f.date_start&&f.date_end&&f.date_start>f.date_end){this.error.set('A data inicial deve ser anterior ou igual à final.');return;}if(f.date_start&&f.date_start>start)start=f.date_start;if(f.date_end&&f.date_end<end)end=f.date_end;if(start>end)return;const p=await firstValueFrom(this.http.get<CalendarResponse>('/api/v1/calendar/',{params:this.params(start,end).set('summary',this.scale()==='year')}));this.days.set(Object.fromEntries(p.days.map(d=>[d.date,d])));this.total.set(p.total);}catch(e){this.fail(e);}finally{this.busy.set(false);}}
 async changeScale(scale:Scale){if(this.busy())return;this.scale.set(scale);await this.load();}
 async move(direction:number){if(this.busy())return;this.anchor.set(navigate(this.anchor(),this.scale(),direction));await this.load();}
 async goToday(){if(this.busy())return;this.anchor.set(this.today());await this.load();}
 async selectMonth(value:string){if(this.busy())return;this.anchor.set(value);this.scale.set('month');await this.load();}
 async showDay(value:string){if(this.busy()||this.dayBusy())return;const previousRange=range(this.anchor(),this.scale()).join('/');this.anchor.set(value);this.selectedDay.set(value);this.dayPage.set(1);this.dayRows.set([]);this.dayCount.set(0);this.dayDialog()?.nativeElement.showModal();if(previousRange!==range(this.anchor(),this.scale()).join('/'))await this.load();await this.loadDay();}
 async loadDay(){if(this.dayBusy())return;this.dayBusy.set(true);this.error.set('');try{const f=this.filters.getRawValue(),date=this.selectedDay();if((f.date_start&&date<f.date_start)||(f.date_end&&date>f.date_end)){this.dayRows.set([]);this.dayCount.set(0);return;}const p=await firstValueFrom(this.http.get<Page<Occurrence>>('/api/v1/occurrences/',{params:this.params(date,date).set('page',this.dayPage())}));this.dayRows.set(p.results);this.dayCount.set(p.count);}catch(e){this.fail(e);}finally{this.dayBusy.set(false);}}
 async dayNavigate(delta:number){if(this.dayBusy())return;this.dayPage.update(p=>p+delta);await this.loadDay();}
 createOnDay(){if(!this.canCreate())return;this.closeDay();this.creatingDate.set(this.selectedDay());this.createDialog()?.nativeElement.showModal();}
 closeCreate(){this.createDialog()?.nativeElement.close();this.creatingDate.set('');}
 closeDay(){this.dayDialog()?.nativeElement.close();}
 openOccurrence(id:string){this.closeDay();this.selectedOccurrence.set(id);this.detailDialog()?.nativeElement.showModal();}
 closeDetail(){this.detailDialog()?.nativeElement.close();this.selectedOccurrence.set(null);}
 async refresh(){await this.load();}
 async saveFavorite(){const name=this.favoriteForm.controls.name.value.trim();if(!name){this.error.set('Informe um nome para o favorito.');return;}if(this.busy())return;this.busy.set(true);this.error.set('');try{await firstValueFrom(this.http.post('/api/v1/calendar-favorites/',{name,filters:this.filters.getRawValue()}));this.favorites.set(await this.all<Favorite>('/api/v1/calendar-favorites/'));this.favoriteForm.controls.name.reset();this.message.set('Filtro salvo para seu usuário.');}catch(e){this.fail(e);}finally{this.busy.set(false);}}
 async applyFavorite(){const f=this.favorites().find(f=>f.id===this.favoriteForm.controls.selected.value);if(!f)return;this.filters.reset();this.filters.patchValue(f.filters);await this.load();}
 async removeFavorite(){const id=this.favoriteForm.controls.selected.value;if(!id||this.busy())return;this.busy.set(true);try{await firstValueFrom(this.http.delete('/api/v1/calendar-favorites/'+id+'/'));this.favorites.update(rows=>rows.filter(row=>row.id!==id));this.favoriteForm.controls.selected.reset();this.message.set('Favorito removido.');}catch(e){this.fail(e);}finally{this.busy.set(false);}}
}
