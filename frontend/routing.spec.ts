import {test,expect,Page} from '@playwright/test';
async function signIn(page:Page,user='demandante1'){
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await expect(page).toHaveURL(/\/entrar(?:\?|$)/);
 await page.getByLabel('Usuário',{exact:true}).fill(user);await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).not.toHaveURL(/\/entrar(?:\?|$)/);await expect(page.locator('.shell')).toBeVisible();
}
test('protected deep links, reload, menu URLs and browser history',async({page})=>{
 await page.goto('/calendario');await expect(page).toHaveURL(/\/entrar\?returnTo=%2Fcalendario$/);await expect(page.locator('app-calendar')).toHaveCount(0);
 await signIn(page);await expect(page).toHaveURL(/\/calendario$/);await expect(page.locator('.calendar-summary')).toContainText('compromissos');
 await page.reload();await expect(page.locator('app-calendar')).toBeVisible();await expect(page).toHaveURL(/\/calendario$/);
 await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page).toHaveURL(/\/compromissos$/);await expect(page).toHaveURL(/\/compromissos$/);await expect(page.getByRole('link',{name:'Compromissos',exact:true})).toHaveAttribute('aria-current','page');
 await page.getByRole('link',{name:'Meu perfil'}).click();await expect(page).toHaveURL(/\/perfil$/);await expect(page).toHaveURL(/\/perfil$/);
 await page.goBack();await expect(page).toHaveURL(/\/compromissos$/);await expect(page.getByLabel('Pesquisar compromissos')).toBeVisible();
 await page.goForward();await expect(page).toHaveURL(/\/perfil$/);await expect(page.getByRole('heading',{level:1})).toHaveText('Meu perfil');
 await page.getByRole('button',{name:'Sair',exact:true}).click();await expect(page).toHaveURL(/\/entrar$/);
 await page.goBack();await expect(page).toHaveURL(/\/entrar(?:\?|$)/);await expect(page.locator('.shell')).toHaveCount(0);
});
test('administrator guards, safe return URLs and expired sessions',async({page})=>{
 await page.goto('/entrar?returnTo=https%3A%2F%2Fexample.com');await signIn(page);await expect(page).toHaveURL(/\/painel$/);
 await page.goto('/auditoria');await expect(page).toHaveURL(/\/acesso-negado$/);await expect(page.locator('.audit-list')).toHaveCount(0);await expect(page.getByRole('heading',{level:1})).toHaveText('Acesso não autorizado');
 await page.goto('/campos-personalizados');await expect(page).toHaveURL(/\/acesso-negado$/);await expect(page.locator('app-custom-fields-admin')).toHaveCount(0);
 await page.goto('/rota-inexistente');await expect(page).toHaveURL(/\/nao-encontrado$/);
 await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page).toHaveURL(/\/compromissos$/);
 await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeEnabled();
 const cookie=(await page.context().cookies()).find(c=>c.name==='csrftoken')!;
 expect((await page.request.post('/api/v1/auth/logout/',{headers:{'X-CSRFToken':cookie.value},data:{}})).status()).toBe(200);
 // The page still has its old UI state: an API request must detect expiry and remove it.
 await page.getByRole('button',{name:'Filtrar',exact:true}).click();await expect(page).toHaveURL(/\/entrar\?returnTo=%2Fcompromissos$/);await expect(page.locator('.shell')).toHaveCount(0);
 await signIn(page,'admin');await expect(page).toHaveURL(/\/compromissos$/);
 await page.goto('/auditoria');await expect(page.locator('.audit-list')).toBeVisible();await expect(page).toHaveURL(/\/auditoria$/);
});
test('legacy occurrence links keep working and detail access remains scoped',async({page})=>{
 await page.goto('/');await signIn(page);await expect(page).toHaveURL(/\/painel$/);
 const profile=await(await page.request.get('/api/v1/auth/me/')).json();const unit=profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id;
 const rows=await(await page.request.get('/api/v1/occurrences/?unit='+unit)).json();expect(rows.results.length).toBeGreaterThan(0);const row=rows.results[0];
 await page.goto('/?occurrence='+row.id);await expect(page).toHaveURL(new RegExp('/compromissos/'+row.id+'$'));await expect(page.locator('.detail-panel')).toContainText(row.identifier);
 await page.reload();await expect(page.locator('.detail-panel')).toContainText(row.identifier);
 await page.getByRole('button',{name:'Sair',exact:true}).click();await signIn(page,'demandante2');
 await page.goto('/compromissos/'+row.id);await expect(page.locator('.detail-panel')).toHaveCount(0);await expect(page.locator('app-commitments .error')).not.toBeEmpty();await expect(page.locator('.shell')).toBeVisible();
 await page.goto('/compromissos/id-invalido');await expect(page).toHaveURL(/\/nao-encontrado$/);
});
