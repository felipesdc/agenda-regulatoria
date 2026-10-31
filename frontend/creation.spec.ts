import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('create from a calendar date and edit the occurrence',async({page})=>{
 test.setTimeout(90000);
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.goto('/');await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();
 const calendarReady=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/calendar/'&&response.status()===200);
 await page.getByRole('link',{name:'Calendário',exact:true}).click();await calendarReady;await expect(page).toHaveURL(/\/calendario(?:\?|$)/);
 await expect(page.locator('.calendar-summary')).toContainText('compromissos');
 const cell=page.locator('.calendar-cell.today');await cell.locator('.day-number').click();await expect(page.getByRole('button',{name:'Fechar dia',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Criar compromisso nesta data',exact:true}).click();
 const dialog=page.locator('dialog[open]');
 const today=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});
 await expect(dialog.locator('#create-due')).toHaveValue(today);
 await expect(dialog.locator('#create-title')).toBeFocused();
 await expect(dialog.getByRole('button',{name:'Salvar compromisso',exact:true})).toBeDisabled();
 const accessibility=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();expect(accessibility.violations).toEqual([]);
 await page.screenshot({path:`../tests/e2e/artifacts/creation-form-${test.info().project.name}.png`,fullPage:true});
 const title=`Criação fictícia ${test.info().project.name} ${Date.now()}`;
 await dialog.locator('#create-title').fill(title);await dialog.locator('#create-description').fill('Obrigação fictícia para verificar criação pela data.');
 const unit=dialog.locator('#create-unit');if(!await unit.inputValue()){await unit.selectOption({index:1});}
 await expect(dialog.locator('app-person-picker input[type=checkbox]').first()).toBeAttached();
 await dialog.locator('app-person-picker input[type=checkbox]').first().check();
 await dialog.locator('#create-entity').selectOption({index:1});
 const categories=await(await page.request.get('/api/v1/categories/')).json();
 // Use a category with no published required custom fields.
 for(const category of categories.results.filter((c:{active:boolean})=>c.active)){
  const schemas=await(await page.request.get('/api/v1/form-versions/?category='+category.id+'&latest=true')).json();
  if(!schemas.results.length){await dialog.locator('#create-category').selectOption(category.id);break;}
 }
 await dialog.getByRole('button',{name:'Salvar compromisso',exact:true}).click();
 await expect(dialog.locator('.detail-panel')).toContainText(title);
 await dialog.getByRole('button',{name:'Editar ocorrência',exact:true}).click();
 await expect(dialog.locator('#edit-title')).toHaveValue(title);
 await dialog.locator('#edit-title').fill(title+' revisado');
 page.once('dialog',prompt=>prompt.dismiss());await dialog.getByRole('button',{name:'Desistir da alteração',exact:true}).click();await expect(dialog.locator('#edit-title')).toHaveValue(title+' revisado');
 page.once('dialog',prompt=>prompt.dismiss());await page.getByRole('button',{name:'Fechar painel de criação',exact:true}).click();await expect(dialog.locator('#edit-title')).toBeVisible();
 await expect(dialog.getByRole('button',{name:'Salvar alteração',exact:true})).toBeDisabled();
 await dialog.locator('#edit-reason').fill('Correção fictícia para teste do formulário.');
 await dialog.getByRole('button',{name:'Salvar alteração',exact:true}).click();
 await expect(dialog.locator('.detail-panel h2')).toHaveText(title+' revisado');
 await page.getByRole('button',{name:'Fechar painel de criação',exact:true}).click();
 await page.getByText('Filtros e favoritos',{exact:true}).click();await page.getByLabel('Pesquisa',{exact:true}).fill(title);await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();await expect(cell).toContainText(title+' revisado');await page.screenshot({path:`../tests/e2e/artifacts/creation-${test.info().project.name}.png`,fullPage:true});
});
