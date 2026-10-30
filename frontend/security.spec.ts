import {test,expect} from '@playwright/test';
test('security headers, CSRF, private responses and session revocation',async({page})=>{
 const response=await page.goto('/');expect(response!.headers()['content-security-policy']).toContain("script-src 'self'");expect(response!.headers()['x-frame-options']).toBe('DENY');expect(response!.headers()['x-content-type-options']).toBe('nosniff');expect(response!.headers()['cache-control']).toContain('no-store');
 const missing=await page.request.post('/api/v1/auth/login/',{data:{username:'admin',password:'not-a-secret'}});expect(missing.status()).toBe(403);
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.getByRole('heading',{name:'Seu espaço de trabalho'})).toBeVisible();
 const cookies=await page.context().cookies();expect(cookies.find(c=>c.name==='sessionid')!.httpOnly).toBe(true);const oldCookie=cookies.find(c=>c.name==='sessionid')!;expect((await page.request.get('/api/v1/dashboard/')).headers()['cache-control']).toContain('no-store');expect((await page.request.get('/api/v1/users/')).status()).toBe(403);
 expect((await page.request.post('/api/v1/auth/logout/',{data:{}})).status()).toBe(403);await page.getByRole('button',{name:'Sair',exact:true}).click();await expect(page.getByRole('heading',{name:'Acesse sua agenda'})).toBeVisible();await page.context().addCookies([oldCookie]);expect((await page.request.get('/api/v1/auth/me/')).status()).toBe(403);
});


test('API documentation renders under the application CSP',async({page})=>{
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.goto('/');await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.getByRole('heading',{name:'Seu espaço de trabalho'})).toBeVisible();
 const violations:string[]=[];page.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused to/i.test(message.text()))violations.push(message.text());});
 const response=await page.goto('/api/v1/docs/');expect(response!.status()).toBe(200);expect(response!.headers()['content-security-policy']).toContain("script-src 'self'");
 await expect(page.getByRole('heading',{level:1,name:/Agenda Regulatória/})).toContainText('Agenda Regulatória');
 await expect(page.locator('.swagger-ui .opblock').first()).toBeVisible();
 const script=await page.request.get('/api/v1/docs/?script=');expect(script.status()).toBe(200);expect(script.headers()['content-type']).toContain('application/javascript');
 expect(violations).toEqual([]);
 await page.screenshot({path:`../tests/e2e/artifacts/api-docs-${test.info().project.name}.png`,fullPage:true});
});
