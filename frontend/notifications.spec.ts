import {test,expect,Page} from '@playwright/test';
const password=process.env['DEMO_PASSWORD'];
async function login(page:Page,user:string){if(!password)throw new Error('Configure DEMO_PASSWORD');await page.goto('/');await page.getByLabel('Usuário',{exact:true}).fill(user);await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page.getByRole('heading',{name:'Seu espaço de trabalho'})).toBeVisible();}
async function logout(page:Page){await page.getByRole('button',{name:'Sair',exact:true}).click();await expect(page.getByRole('heading',{name:'Acesse sua agenda'})).toBeVisible();}
test('notification policy, Redis worker, Mailpit SMTP, private history and internal link',async({page})=>{
 test.setTimeout(90000);
 const tag=`NOT fictício ${test.info().project.name} ${Date.now()}`;
 await login(page,'demandante1');
 const profile=await(await page.request.get('/api/v1/auth/me/')).json();
 const unit=profile.memberships.find((m:{role:string})=>m.role==='requester').unit_id;
 const people=await(await page.request.get('/api/v1/assignable-users/?unit='+unit)).json();const executor=people.results.find((p:{username:string})=>p.username==='demandado1');
 const entities=await(await page.request.get('/api/v1/entities/')).json();const categories=await(await page.request.get('/api/v1/categories/')).json();const csrf=(await page.context().cookies()).find(c=>c.name==='csrftoken')!.value;
 const today=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});
 const created=await page.request.post('/api/v1/definitions/',{headers:{'X-CSRFToken':csrf},data:{title:tag,description:'Resumo fictício para validação da fila SMTP.',unit,entity:entities.results[0].id,category:categories.results[0].id,assignees:[executor.id],reference_date:today,due_date:today}});expect(created.status()).toBe(201);const occurrence=await created.json();
 await page.getByRole('link',{name:'Notificações',exact:true}).click();await expect(page).toHaveURL(/\/notificacoes$/);await page.getByText('Políticas de alerta de vencimento',{exact:true}).click();
 await expect(page.getByLabel('Compromisso ou categoria').locator('option').filter({hasText:tag})).toHaveCount(1);
 await page.getByLabel('Compromisso ou categoria').selectOption(occurrence.definition);await page.getByLabel('Intervalos em dias').fill('0, -1');await page.getByLabel('Contagem de dias').selectOption('business');await page.getByLabel('Motivo da política').fill('Política fictícia testada no Mailpit');await page.getByRole('button',{name:'Salvar política de alerta',exact:true}).click();await expect(page.getByRole('status')).toContainText('Política salva');await logout(page);
 await login(page,'admin');await page.getByRole('link',{name:'Notificações',exact:true}).click();await expect(page).toHaveURL(/\/notificacoes$/);await page.getByRole('button',{name:'Verificar alertas e processar fila',exact:true}).click();await expect(page.getByRole('status')).toContainText('solicitados');await logout(page);
 await login(page,'demandado1');
 let delivery:{id:string;event_id:string;status:string;attempts:number;recipient_email:string;history:unknown[]}|undefined;
 await expect.poll(async()=>{const response=await page.request.get('/api/v1/notifications/?occurrence='+occurrence.id);expect(response.status()).toBe(200);const data=await response.json();delivery=data.results.find((r:{kind:string})=>r.kind==='assigned');return delivery?.status;},{timeout:45000,intervals:[500,1000,2000]}).toBe('accepted');
 expect(delivery!.attempts).toBe(1);expect(delivery!.history).toHaveLength(2);
 // Read local Mailpit without application cookies; SMTP acceptance is not inbox delivery.
 const matches=await fetch('http://localhost:8025/api/v1/search?query='+encodeURIComponent('subject:'+occurrence.identifier)).then(r=>r.json()) as {messages:{ID:string;Subject:string}[]};
 const assignedMessages=matches.messages.filter(m=>m.Subject.includes('Novo compromisso atribuído'));expect(assignedMessages).toHaveLength(1);const message=assignedMessages[0];
 const body=await fetch('http://localhost:8025/api/v1/message/'+message!.ID).then(r=>r.json()) as {Text:string;HTML:string};
 expect(body.Text).toContain(tag);expect(body.Text).toContain('/?occurrence='+occurrence.id);expect(body.HTML).toContain('Agenda Regulatória');
 await page.getByRole('link',{name:'Notificações',exact:true}).click();await expect(page).toHaveURL(/\/notificacoes$/);await page.getByLabel('Pesquisar avisos').fill(tag);await page.getByRole('button',{name:'Filtrar notificações',exact:true}).click();await expect(page.locator('.notification-list article').filter({hasNotText:tag})).toHaveCount(0);const notice=page.locator('.notification-list article').filter({hasText:tag}).filter({hasText:'Novo compromisso atribuído'});await expect(notice).toContainText('Aceito pelo SMTP');await expect(notice).toContainText('Entrega não confirmada');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../tests/e2e/artifacts/notifications-${test.info().project.name}.png`,fullPage:true});
 await notice.getByRole('button',{name:'Abrir ocorrência'}).click();await expect(page.locator('.detail-panel')).toContainText(tag);await page.goto('/?occurrence='+occurrence.id);await expect(page.locator('.detail-panel')).toContainText(tag);await logout(page);
 await login(page,'demandante2');const invisible=await page.request.get('/api/v1/notifications/'+delivery!.id+'/');expect(invisible.status()).toBe(404);
});
