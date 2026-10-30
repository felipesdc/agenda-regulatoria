import {Component,inject} from '@angular/core';
import {CanActivateFn,Router,Routes} from '@angular/router';
import {Session,safeReturn,occurrenceId} from './session';
import {WorkspacePage} from './workspace-page';
@Component({standalone:true,template:''})
export class LoginRoute {}
const authenticated:CanActivateFn=async(route,state)=>{
 const session=inject(Session),router=inject(Router);
 if(!await session.refresh())return router.createUrlTree(['/entrar'],{queryParams:{returnTo:safeReturn(state.url)}});
 if(route.data['administrator']&&!session.profile()?.administrator)return router.createUrlTree(['/acesso-negado']);
 return true;
};
const login:CanActivateFn=async route=>{
 const session=inject(Session),router=inject(Router);
 return await session.refresh()?router.parseUrl(safeReturn(route.queryParamMap.get('returnTo'))):true;
};
const legacy:CanActivateFn=route=>{
 const router=inject(Router),id=route.queryParamMap.get('occurrence');
 return router.parseUrl(id&&occurrenceId.test(id)?'/compromissos/'+id:'/painel');
};
function page(path:string,section:string,title:string,administrator=false):Routes[number]{return {path,title:title+' · Agenda Regulatória',component:WorkspacePage,canActivate:[authenticated],runGuardsAndResolvers:'always',data:{section,title,administrator}};}
export const routes:Routes=[
 {path:'',pathMatch:'full',component:LoginRoute,canActivate:[legacy]},
 {path:'entrar',component:LoginRoute,canActivate:[login]},
 page('painel','overview','Seu espaço de trabalho'),
 page('relatorios','reports','Relatórios'),page('calendario','calendar','Calendário'),
 page('compromissos','commitments','Compromissos'),
 {...page('compromissos/:id','linked','Detalhes do compromisso'),canActivate:[authenticated,(route)=>{const router=inject(Router);return occurrenceId.test(route.paramMap.get('id')||'')||router.createUrlTree(['/nao-encontrado']);}]},
 page('minhas-atribuicoes','mine','Minhas atribuições'),page('validacoes','validation','Validações pendentes'),
 page('campos-personalizados','fields','Campos personalizados',true),page('auditoria','audit','Trilha de auditoria',true),
 page('unidades','units','Minhas unidades'),page('notificacoes','notifications','Notificações'),page('perfil','profile','Meu perfil'),
 page('acesso-negado','forbidden','Acesso não autorizado'),page('nao-encontrado','not-found','Página não encontrada'),
 {path:'**',redirectTo:'nao-encontrado'},
];
