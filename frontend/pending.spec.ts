import {test,expect} from '@playwright/test';
import {shift} from './src/calendar/date-utils';
import AxeBuilder from '@axe-core/playwright';
test('pending center matches scoped API counts, paginates and opens real details',async({page,browser})=>{
 test.setTimeout(90000);
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.goto('/pendencias');await expect(page).toHaveURL(/\/entrar\?returnTo=%2Fpendencias$/);
 await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();
 await expect(page).toHaveURL(/\/pendencias(?:\?|$)/);await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();
 // Real fixtures ensure every group has data even on an empty demonstration database.
 const today=(await(await page.request.get('/api/v1/pending-center/')).json()).as_of;
 const profile=await(await page.request.get('/api/v1/auth/me/')).json();const unit=profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id;
 const people=await(await page.request.get('/api/v1/assignable-users/?unit='+unit)).json();const executor=people.results.find((p:{username:string})=>p.username==='demandado1');
 const entities=await(await page.request.get('/api/v1/entities/')).json(),categories=await(await page.request.get('/api/v1/categories/')).json();
 const csrf=(await page.context().cookies()).find(c=>c.name==='csrftoken')!.value;
 const tag=`Pendência fictícia ${test.info().project.name} ${Date.now()}`;let validationId='';
 for(const [name,date] of [['atrasado',shift(today,-1)],['próximo',today],['validação',shift(today,7)]]){
  const response=await page.request.post('/api/v1/definitions/',{headers:{'X-CSRFToken':csrf},data:{title:tag+' '+name,description:'Registro fictício para testar a central.',unit,entity:entities.results[0].id,category:categories.results[0].id,assignees:[executor.id],reference_date:today,due_date:date}});expect(response.status()).toBe(201);if(name==='validação')validationId=(await response.json()).id;
 }
 const actor=await browser.newContext({baseURL:process.env['E2E_BASE_URL']||'http://localhost:8080'});
 try{
  const executorPage=await actor.newPage();await executorPage.goto('/');await executorPage.getByLabel('Usuário',{exact:true}).fill('demandado1');await executorPage.getByLabel('Senha',{exact:true}).fill(password);await executorPage.getByRole('button',{name:'Entrar',exact:true}).click();await expect(executorPage).toHaveURL(/\/painel$/);
  const headers={'X-CSRFToken':(await actor.cookies()).find(c=>c.name==='csrftoken')!.value};const path='/api/v1/occurrences/'+validationId;
  let row=await(await executorPage.request.get(path+'/')).json();let response=await executorPage.request.post(path+'/transition/',{headers,data:{operation:'start',revision:row.revision}});expect(response.status()).toBe(200);row=await response.json();
  response=await executorPage.request.post(path+'/actions/',{headers,data:{text:'Conferência fictícia concluída.'}});expect(response.status()).toBe(201);
  response=await executorPage.request.post(path+'/transition/',{headers,data:{operation:'submit',revision:row.revision}});expect(response.status()).toBe(200);
 }finally{await actor.close();}
 await page.getByRole('button',{name:'Atualizar pendências'}).click();await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();
 for(const [bucket,label] of [['overdue','Atrasados'],['upcoming','Próximos 7 dias'],['validation','Aguardando validação']]){
  const loaded=page.waitForResponse(r=>r.url().includes('/api/v1/pending-center/')&&new URL(r.url()).searchParams.get('bucket')===bucket&&new URL(r.url()).searchParams.get('page')==='1'&&r.request().method()==='GET');
  await page.locator('.pending-card').filter({hasText:label}).click();const response=await loaded;expect(response.status()).toBe(200);const data=await response.json();await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();
  await expect(page.locator('.pending-card[aria-pressed=true] strong')).toHaveText(String(data.counts[bucket]));
  await expect(page.locator('app-pending .pagination')).toContainText(data.count+' registros');
  await expect(page.locator('app-pending .commitment-row')).toHaveCount(data.results.length);
  if(data.results.length){await expect(page.locator('app-pending .commitment-row').first()).toContainText(data.results[0].identifier);}
  else await expect(page.locator('app-pending')).toContainText('Nenhuma pendência neste grupo.');
  if(data.next){await page.getByRole('button',{name:'Próximas pendências'}).click();await expect(page.locator('app-pending .pagination')).toContainText('Página 2');await page.getByRole('button',{name:'Pendências anteriores'}).click();await expect(page.locator('app-pending .pagination')).toContainText('Página 1');}
  if(data.results.length){await page.locator('app-pending .commitment-row').first().click();await expect(page.locator('dialog[open] .detail-panel')).toContainText(data.results[0].identifier);await page.getByRole('button',{name:'Fechar detalhes',exact:true}).click();await expect(page.locator('dialog[open]')).toHaveCount(0);await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();}
 }
 await page.locator('.pending-card').filter({hasText:'Aguardando validação'}).click();await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();
 await page.locator('app-pending .commitment-row').filter({hasText:tag+' validação'}).click();
 await page.getByRole('button',{name:'Aprovar conclusão',exact:true}).click();await expect(page.locator('dialog[open] .detail-meta .badge')).toContainText('Concluído');
 await page.getByRole('button',{name:'Fechar detalhes',exact:true}).click();await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();
 await expect(page.locator('app-pending .commitment-row').filter({hasText:tag+' validação'})).toHaveCount(0);
 const accessibility=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();expect(accessibility.violations).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`../tests/e2e/artifacts/pending-${test.info().project.name}.png`,fullPage:true});
 await page.reload();await expect(page.locator('app-pending')).toBeVisible();await expect(page).toHaveURL(/\/pendencias(?:\?|$)/);
 await page.getByRole('link',{name:'Painel inicial'}).click();await expect(page).toHaveURL(/\/painel$/);await page.getByRole('link',{name:'Abrir central de pendências'}).click();await expect(page).toHaveURL(/\/pendencias(?:\?|$)/);
});
