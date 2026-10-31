import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('field feedback, searchable assignees and safe draft departure',async({page})=>{
 test.setTimeout(90000);
 const password=process.env['DEMO_PASSWORD'];if(!password)throw new Error('Configure DEMO_PASSWORD');
 await page.goto('/entrar');await page.getByLabel('Usuário',{exact:true}).fill('demandante1');await page.getByLabel('Senha',{exact:true}).fill(password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/painel$/);
 await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page).toHaveURL(/\/compromissos(?:\?|$)/);await page.getByRole('button',{name:'Novo compromisso',exact:true}).click();
 const title=page.locator('#create-title');await title.focus();await title.blur();await expect(page.locator('#create-title-error')).toHaveText('Informe o título.');await expect(title).toHaveAttribute('aria-invalid','true');
 await title.fill('Rascunho fictício de teste');await title.blur();await expect(page.locator('#create-title-error')).toHaveCount(0);await expect(title).toHaveAttribute('aria-invalid','false');
 const unit=page.locator('#create-unit');if(!await unit.inputValue())await unit.selectOption({index:1});
 const picker=page.getByRole('group',{name:'Responsáveis pela execução',exact:true});const first=picker.getByRole('checkbox').first();await expect(first).toBeVisible();const value=await first.inputValue();await first.check();
 await picker.getByRole('searchbox').fill('nome inexistente para teste');await expect(picker.getByRole('checkbox')).toHaveCount(0);await expect(picker.locator('.picker-summary')).toContainText('1 responsável');
 await picker.getByRole('searchbox').fill('');await expect(picker.locator('input[value="'+value+'"]').first()).toBeChecked();
 const remove=picker.getByRole('button',{name:/^Remover /}).first();await remove.click();await expect(picker.locator('.picker-summary')).toContainText('0 responsável');await expect(page.locator('#create-assignees-error')).toContainText('ao menos um responsável');
 await picker.locator('input[value="'+value+'"]').first().check();
 page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Fechar formulário',exact:true}).click();await expect(title).toHaveValue('Rascunho fictício de teste');
 page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('link',{name:'Calendário',exact:true}).click();await expect(page).toHaveURL(/\/compromissos(?:\?|$)/);await expect(title).toHaveValue('Rascunho fictício de teste');
 const tabClose=new Promise<void>(resolve=>page.once('dialog',async prompt=>{expect(prompt.type()).toBe('beforeunload');await prompt.dismiss();resolve();}));
 await page.close({runBeforeUnload:true});await tabClose;expect(page.isClosed()).toBe(false);await expect(title).toHaveValue('Rascunho fictício de teste');
 const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();expect(axe.violations).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.locator('.form-panel').screenshot({path:`../tests/e2e/artifacts/forms-${test.info().project.name}.png`});
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('link',{name:'Calendário',exact:true}).click();await expect(page).toHaveURL(/\/calendario(?:\?|$)/);
 await page.getByRole('link',{name:'Compromissos',exact:true}).click();await expect(page).toHaveURL(/\/compromissos(?:\?|$)/);await page.getByRole('button',{name:'Novo compromisso',exact:true}).click();await expect(title).toHaveValue('');
 await title.fill('Cadastro que será reiniciado');page.once('dialog',prompt=>prompt.accept());await page.getByRole('button',{name:'Novo compromisso',exact:true}).click();await expect(title).toHaveValue('');
 // Merely searching the picker must not create a business draft.
 await page.getByRole('searchbox',{name:'Buscar responsáveis',exact:true}).fill('busca');await page.locator('.form-panel form').evaluate(form=>form.addEventListener('submit',()=>form.setAttribute('data-test-submitted','true')));await page.getByRole('searchbox',{name:'Buscar responsáveis',exact:true}).press('Enter');await expect(page.locator('.form-panel form')).not.toHaveAttribute('data-test-submitted','true');let unexpected=false;page.once('dialog',async dialog=>{unexpected=true;await dialog.dismiss();});
 await page.getByRole('link',{name:'Meu perfil'}).click();await expect(page).toHaveURL(/\/perfil$/);expect(unexpected).toBe(false);page.removeAllListeners('dialog');
});
