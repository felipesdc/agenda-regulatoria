import {Component,inject,signal,computed} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {ReactiveFormsModule,FormBuilder,Validators} from '@angular/forms';
import {NavigationEnd,Router,RouterOutlet,RouterLink} from '@angular/router';
import {toSignal} from '@angular/core/rxjs-interop';
import {filter,firstValueFrom} from 'rxjs';
import {Session,safeReturn} from './session';
@Component({selector:'app-root',standalone:true,imports:[ReactiveFormsModule,RouterOutlet,RouterLink],templateUrl:'./app.html'})
export class App {
 private http=inject(HttpClient);private fb=inject(FormBuilder);private router=inject(Router);private session=inject(Session);
 profile=this.session.profile;units=this.session.units;busy=signal(false);error=this.session.error;
 private navigation=toSignal(this.router.events.pipe(filter(e=>e instanceof NavigationEnd)));
 private routeData=computed(()=>{this.navigation();let route=this.router.routerState.snapshot.root;while(route.firstChild)route=route.firstChild;return route.data;});
 section=computed(()=>this.routeData()['section']||'overview');pageTitle=computed(()=>this.routeData()['title']||'Agenda Regulatória');
 form=this.fb.nonNullable.group({username:['',Validators.required],password:['',Validators.required]});
 async login(){if(this.form.invalid||this.busy())return;this.busy.set(true);this.error.set('');try{
  await firstValueFrom(this.http.get('/api/v1/auth/csrf/'));await firstValueFrom(this.http.post('/api/v1/auth/login/',this.form.getRawValue()));
  if(!await this.session.refresh())throw new Error('Session unavailable');
  const target=safeReturn(this.router.parseUrl(this.router.url).queryParams['returnTo']);
  this.form.controls.password.reset();await this.router.navigateByUrl(target,{replaceUrl:true});
 }catch{this.error.set('Não foi possível entrar. Verifique as credenciais ou tente novamente mais tarde.');}finally{this.busy.set(false);}}
 async logout(){if(this.busy())return;this.busy.set(true);try{await firstValueFrom(this.http.post('/api/v1/auth/logout/',{}));this.session.clear();this.form.reset();await this.router.navigate(['/entrar'],{replaceUrl:true});}catch{this.error.set('Não foi possível encerrar a sessão. Tente novamente.');}finally{this.busy.set(false);}}
}
