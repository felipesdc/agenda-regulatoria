import {test,expect,Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
async function login(page:Page,user:string,password:string){await page.goto('/entrar');await page.getByLabel('Usuário',{exact:true}).fill(user);await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/painel$/);}
test('private evidence upload, verified download, logical withdrawal and access scope',async({page})=>{
 test.setTimeout(120000);const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await login(page,'demandante1',password);
 const profile=await(await page.request.get('/api/v1/auth/me/')).json(),unit=profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id;
 const people=await(await page.request.get('/api/v1/assignable-users/?unit='+unit)).json(),executor=people.results.find((p:{username:string})=>p.username==='demandado1');
 const entities=await(await page.request.get('/api/v1/entities/')).json(),categories=await(await page.request.get('/api/v1/categories/')).json();
 const csrf=(await page.context().cookies()).find(c=>c.name==='csrftoken')!.value,today=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});
 const created=await page.request.post('/api/v1/definitions/',{headers:{'X-CSRFToken':csrf},data:{title:`Evidência fictícia ${test.info().project.name} ${Date.now()}`,description:'Verificação de anexos sem validade regulatória.',unit,entity:entities.results[0].id,category:categories.results[0].id,assignees:[executor.id],reference_date:today,due_date:today}});expect(created.status()).toBe(201);const row=await created.json();
 await page.getByRole('button',{name:'Sair',exact:true}).click();await login(page,'demandado1',password);await page.goto('/compromissos/'+row.id);
 await page.getByRole('button',{name:'Iniciar execução',exact:true}).click();await expect(page.locator('#action-files')).toBeEnabled();
 const policy=await(await page.request.get('/api/v1/evidence-policy/')).json();await page.getByLabel('Nova providência',{exact:true}).fill('Conferência fictícia com documento comprobatório.');
 await page.locator('#action-files').setInputFiles({name:'grande.txt',mimeType:'text/plain',buffer:Buffer.alloc(policy.max_file_bytes+1,65)});await expect(page.getByText('Revise o formato, a quantidade e o tamanho dos anexos.')).toBeVisible();await expect(page.getByRole('button',{name:'Registrar providência',exact:true})).toBeDisabled();await page.getByRole('button',{name:'Limpar anexos',exact:true}).click();
 await page.locator('#action-files').setInputFiles({name:'falso.pdf',mimeType:'application/pdf',buffer:Buffer.from('This is not a PDF')});const rejected=page.waitForResponse(r=>r.url().endsWith('/actions/')&&r.request().method()==='POST');await page.getByRole('button',{name:'Registrar providência',exact:true}).click();expect((await rejected).status()).toBe(400);await expect(page.locator('.history-item').filter({hasText:'Conferência fictícia com documento comprobatório.'})).toHaveCount(0);await page.getByRole('button',{name:'Limpar anexos',exact:true}).click();
 const bytes=Buffer.from('Comprovação fictícia — sem dados reais.\n','utf8'),name='comprovação.txt';await page.locator('#action-files').setInputFiles({name,mimeType:'application/octet-stream',buffer:bytes});
 const registered=page.waitForResponse(r=>r.url().endsWith('/actions/')&&r.request().method()==='POST');await page.getByRole('button',{name:'Registrar providência',exact:true}).click();const result=await registered;expect(result.status()).toBe(201);const evidence=(await result.json()).evidence[0];expect(evidence.sha256).toBe(createHash('sha256').update(bytes).digest('hex'));
 await expect(page.locator('app-evidence')).toContainText(name);await expect(page.locator('#action-files')).toHaveValue('');
 const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Baixar '+name,exact:true}).click();const download=await downloadEvent;expect(download.suggestedFilename()).toBe(name);expect(await readFile((await download.path())!)).toEqual(bytes);
 const response=await page.request.get('/api/v1/evidence/'+evidence.id+'/download/');expect(response.status()).toBe(200);expect(response.headers()['cache-control']).toContain('no-store');expect(response.headers()['content-disposition']).toContain('attachment;');
 const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();expect(axe.violations).toEqual([]);
 await page.screenshot({path:`../tests/e2e/artifacts/evidence-${test.info().project.name}.png`,fullPage:true});
 await page.getByRole('button',{name:'Retirar '+name,exact:true}).click();await expect(page.getByRole('button',{name:'Confirmar retirada',exact:true})).toBeDisabled();await page.getByLabel('Justificativa da retirada',{exact:true}).fill('Documento fictício anexado por engano.');await page.getByRole('button',{name:'Confirmar retirada',exact:true}).click();await expect(page.locator('app-evidence')).toContainText('Documento fictício anexado por engano.');await expect(page.getByRole('button',{name:'Baixar '+name,exact:true})).toHaveCount(0);expect((await page.request.get('/api/v1/evidence/'+evidence.id+'/download/')).status()).toBe(410);
 await page.getByRole('button',{name:'Sair',exact:true}).click();await expect(page).toHaveURL(/\/entrar$/);expect((await page.request.get('/api/v1/evidence/'+evidence.id+'/download/')).status()).toBe(403);
 await login(page,'demandante2',password);expect((await page.request.get('/api/v1/evidence/'+evidence.id+'/download/')).status()).toBe(404);
});
