import {test,expect} from '@playwright/test';
import {monthGrid,range,navigate,weekStart} from './src/calendar/date-utils';
test('calendar dates handle leap years, month ends and weeks',()=>{
 expect(range('2028-02-29','year')).toEqual(['2028-01-01','2028-12-31']);
 expect(navigate('2028-02-29','year',1)).toBe('2029-02-28');
 expect(navigate('2026-01-31','month',1)).toBe('2026-02-28');
 expect(weekStart('2026-11-01')).toBe('2026-10-26');
 expect(range('2026-12-31','week')).toEqual(['2026-12-28','2027-01-03']);
 expect(monthGrid('2026-02-01')).toHaveLength(42);
 expect(new Set(monthGrid('2026-02-01')).size).toBe(42);
});
test('calendar navigation, filters, favorites, daily overflow and modal workflow',async({page})=>{
 test.setTimeout(90000);
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.goto('/');await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.getByRole('heading',{name:'Seu espaço de trabalho'})).toBeVisible();
 // Create real, clearly fictitious events through the same protected API as the UI.
 const data=await page.request.get('/api/v1/assignable-users/?unit='+await page.evaluate(async()=>{const p=await(await fetch('/api/v1/auth/me/')).json();return p.memberships.find((m:{role:string})=>m.role==='requester').unit_id;}));
 const people=await data.json();const profile=await(await page.request.get('/api/v1/auth/me/')).json();const entities=await(await page.request.get('/api/v1/entities/')).json();const categories=await(await page.request.get('/api/v1/categories/')).json();
 const tag=`CAL fictício ${test.info().project.name} ${Date.now()}`;
 const due=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});
 const cookie=(await page.context().cookies()).find(c=>c.name==='csrftoken');
 for(let i=0;i<5;i++){const r=await page.request.post('/api/v1/definitions/',{headers:{'X-CSRFToken':cookie!.value},data:{title:tag+' '+i,description:'Teste fictício do calendário.',unit:profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id,entity:entities.results[0].id,category:categories.results[0].id,assignees:[people.results[0].id],reference_date:due,due_date:due,priority:'high'}});expect(r.status()).toBe(201);}
 await page.getByRole('button',{name:'Calendário',exact:true}).click();
 await expect(page.locator('.month-grid .calendar-cell')).toHaveCount(42);
 await page.getByText('Filtros e favoritos',{exact:true}).click();
 await page.getByLabel('Pesquisa',{exact:true}).fill(tag);await page.getByLabel('Prioridade',{exact:true}).selectOption('high');await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await expect(page.locator('.calendar-summary')).toContainText('5 compromissos');
 await expect(page.locator('.month-grid .calendar-event')).toHaveCount(3);
 await page.getByRole('button',{name:'+2 compromissos',exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('5 compromissos');
 await expect(page.locator('dialog[open] .commitment-row')).toHaveCount(5);
 await page.getByRole('button',{name:'Fechar dia',exact:true}).click();
 await page.getByLabel('Nome do favorito').fill(tag);await page.getByRole('button',{name:'Salvar favorito',exact:true}).click();await expect(page.getByRole('status')).toContainText('Filtro salvo');
 await page.getByRole('button',{name:'Semana',exact:true}).click();await expect(page.locator('.week-day')).toHaveCount(7);await expect(page.locator('.calendar-summary')).toContainText('5 compromissos');
 await page.getByRole('button',{name:'Ano',exact:true}).click();await expect(page.locator('.mini-month')).toHaveCount(12);await expect(page.locator('.calendar-summary')).toContainText('5 compromissos');
 const month=new Intl.DateTimeFormat('pt-BR',{month:'long',timeZone:'America/Sao_Paulo'}).format(new Date());await page.getByRole('button',{name:new RegExp('^Abrir '+month+' '+due.slice(0,4))}).click();await expect(page.locator('.month-grid')).toBeVisible();
 await page.locator('.month-grid .calendar-event').first().click();await expect(page.locator('dialog[open] .detail-panel')).toContainText(tag);await expect(page.getByRole('button',{name:'Cancelar compromisso',exact:true})).toBeVisible();await page.getByRole('button',{name:'Fechar painel',exact:true}).click();
 // The next month's 42-day grid can still include today's trailing dates.
 await page.getByRole('button',{name:'Próximo período',exact:true}).click();await page.getByRole('button',{name:'Próximo período',exact:true}).click();await expect(page.locator('.calendar-summary')).toContainText('0 compromissos');await page.getByRole('button',{name:'Hoje',exact:true}).click();await expect(page.locator('.calendar-summary')).toContainText('5 compromissos');
 await page.getByRole('button',{name:'Limpar filtros',exact:true}).click();await page.getByLabel('Filtros salvos').selectOption({label:tag});await page.getByRole('button',{name:'Aplicar favorito',exact:true}).click();await expect(page.getByLabel('Pesquisa',{exact:true})).toHaveValue(tag);await expect(page.locator('.calendar-summary')).toContainText('5 compromissos');
 const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,elements:Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth&&getComputedStyle(e).position!=='absolute').slice(0,12).map(e=>({tag:e.tagName,class:e.className,width:e.getBoundingClientRect().width}))}));
 expect(overflow.scroll,JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width);
 await page.screenshot({path:`../tests/e2e/artifacts/calendar-${test.info().project.name}.png`,fullPage:true});
 await page.getByRole('button',{name:'Excluir favorito',exact:true}).click();await expect(page.getByRole('status')).toContainText('Favorito removido');
});
