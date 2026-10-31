import {test,expect,Page} from '@playwright/test';
async function login(page:Page,user='demandante1'){
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.getByLabel('Usuário',{exact:true}).fill(user);await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.locator('.shell')).toBeVisible();
}
test('applied list filters survive reload, drafts stay out and browser history restores queries',async({page})=>{
 await page.goto('/entrar');await login(page);await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 const first=`URL fictícia & ação=+ # ${Date.now()}`;const second=first+' segundo';
 await page.getByLabel('Pesquisar compromissos').fill(first);await page.getByLabel('Situação',{exact:true}).selectOption('pending');await page.getByRole('button',{name:'Filtrar',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(first);await expect.poll(()=>new URL(page.url()).searchParams.get('status')).toBe('pending');
 await page.getByLabel('Pesquisar compromissos').fill('rascunho que não deve ir à URL');expect(new URL(page.url()).searchParams.get('q')).toBe(first);
 await page.reload();await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue(first);await expect(page.getByLabel('Situação',{exact:true})).toHaveValue('pending');await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 await page.getByLabel('Pesquisar compromissos').fill(second);await page.getByRole('button',{name:'Filtrar',exact:true}).click();await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(second);
 await page.goBack();await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue(first);await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 await page.goForward();await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue(second);await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
});
test('shared query resumes after login, cleans unknown values and still enforces unit scope',async({page})=>{
 await page.goto('/entrar');await login(page);await expect(page).toHaveURL(/\/painel$/);
 const profile=await(await page.request.get('/api/v1/auth/me/')).json();const unit=profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id;
 const records=await(await page.request.get('/api/v1/occurrences/?unit='+unit)).json();expect(records.results.length).toBeGreaterThan(0);const row=records.results[0];
 await page.getByRole('button',{name:'Sair',exact:true}).click();
 const query=new URLSearchParams({q:row.identifier,status:row.status,page:'999999',token:'fictitious-not-a-token',returnTo:'https://example.com'});
 await page.goto('/compromissos?'+query);await expect(page).toHaveURL(/\/entrar\?/);
 const target=new URL(page.url()).searchParams.get('returnTo')!;expect(target).toContain('q=');expect(target).not.toContain('token');expect(target).not.toContain('example.com');
 await login(page,'demandante2');await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue(row.identifier);await expect(page.locator('.commitment-row')).toHaveCount(0);
 await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBeNull();expect(new URL(page.url()).searchParams.get('token')).toBeNull();
 await page.goto('/compromissos?q=one&q=two&status=invalid&overdue=yes&page=-1&unexpected=test');await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();await expect.poll(()=>new URL(page.url()).search).toBe('');await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue('');
});
test('calendar and report periods, grouping and notification/pending filters restore from URLs',async({page})=>{
 test.setTimeout(90000);await page.goto('/entrar');await login(page);await expect(page).toHaveURL(/\/painel$/);
 await page.goto('/calendario?q=URL%20calend%C3%A1rio&scale=week&anchor=2028-02-29&priority=high');await expect(page.locator('.week-day')).toHaveCount(7);await expect(page.getByRole('button',{name:'Próximo período',exact:true})).toBeEnabled();
 await page.getByText('Filtros e favoritos',{exact:true}).click();await expect(page.getByLabel('Pesquisa',{exact:true})).toHaveValue('URL calendário');await page.getByLabel('Pesquisa',{exact:true}).fill('rascunho não aplicado');await page.getByRole('button',{name:'Próximo período',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('anchor')).toBe('2028-03-07');expect(new URL(page.url()).searchParams.get('q')).toBe('URL calendário');await page.reload();await page.getByText('Filtros e favoritos',{exact:true}).click();await expect(page.getByLabel('Pesquisa',{exact:true})).toHaveValue('URL calendário');await expect(page.locator('.week-day')).toHaveCount(7);
 await page.goto('/relatorios?q=URL%20relat%C3%B3rio&date_start=2028-02-01&date_end=2028-03-22&group_by=entity&page=999999&group_page=999999');await expect(page.getByRole('button',{name:'Consultar relatório',exact:true})).toBeEnabled();
 await expect(page.getByLabel('Início do período')).toHaveValue('2028-02-01');await expect(page.getByLabel('Fim do período')).toHaveValue('2028-03-22');await expect(page.getByLabel('Agrupar relatório por')).toHaveValue('entity');
 await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBeNull();await expect.poll(()=>new URL(page.url()).searchParams.get('group_page')).toBeNull();await page.reload();await expect(page.getByLabel('Pesquisar relatório')).toHaveValue('URL relatório');await expect(page.getByLabel('Agrupar relatório por')).toHaveValue('entity');
 await page.goto('/notificacoes?q=URL%20notifica%C3%A7%C3%A3o&status=failed&page=999999');await expect(page.locator('app-notifications input[formControlName=q]')).toHaveValue('URL notificação');await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBeNull();
 await page.goto('/pendencias?bucket=upcoming&page=999999');await expect(page.getByRole('button',{name:'Atualizar pendências'})).toBeEnabled();await expect(page.locator('.pending-card[aria-pressed=true]')).toContainText('Próximos 7 dias');await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBeNull();await page.reload();await expect(page.locator('.pending-card[aria-pressed=true]')).toContainText('Próximos 7 dias');
});

test('query history preserves business drafts and a late response cannot overwrite Back',async({page})=>{
 test.setTimeout(90000);await page.goto('/entrar');await login(page);await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 const first='URL primeira '+Date.now(),second=first+' segunda',third=first+' terceira';
 for(const value of [first,second]){await page.getByLabel('Pesquisar compromissos').fill(value);await page.getByRole('button',{name:'Filtrar',exact:true}).click();await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(value);await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();}
 await page.getByRole('button',{name:'Novo compromisso',exact:true}).click();await page.locator('#create-title').fill('Rascunho de negócio que não deve entrar na URL');
 let release!:()=>void,captured!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});const ready=new Promise<void>(resolve=>{captured=resolve;});
 await page.route('**/api/v1/occurrences/?**',async route=>{if(new URL(route.request().url()).searchParams.get('q')!==third){await route.continue();return;}const response=await route.fetch();captured();await gate;await route.fulfill({response});});
 await page.getByLabel('Pesquisar compromissos').fill(third);await page.getByRole('button',{name:'Filtrar',exact:true}).click();await ready;
 await page.goBack();await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(first);release();
 await expect(page.getByLabel('Pesquisar compromissos')).toHaveValue(first);await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 await expect(page.locator('#create-title')).toHaveValue('Rascunho de negócio que não deve entrar na URL');expect(page.url()).not.toContain('Rascunho');expect(new URL(page.url()).searchParams.get('q')).toBe(first);
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Fechar formulário',exact:true}).click();await expect(page.locator('.form-panel')).toHaveCount(0);
});
