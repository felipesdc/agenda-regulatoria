import {Component,forwardRef,input,signal,computed} from '@angular/core';
import {ControlValueAccessor,NG_VALUE_ACCESSOR} from '@angular/forms';
import {Person} from './types';
@Component({selector:'app-person-picker',standalone:true,providers:[{provide:NG_VALUE_ACCESSOR,useExisting:forwardRef(()=>PersonPicker),multi:true}],template:`
<fieldset class="person-picker" [disabled]="disabled()" [attr.aria-invalid]="invalid()" [attr.aria-describedby]="errorId()||null"><legend>{{label()}}</legend>
<label [for]="prefix()+'-search'">Buscar responsáveis</label><input [id]="prefix()+'-search'" type="search" (keydown.enter)="$event.preventDefault()" [value]="search()" (input)="search.set($any($event.target).value)" (blur)="touch()" placeholder="Nome ou usuário" autocomplete="off">
<p class="picker-help">Selecione um ou mais responsáveis. A busca mantém as seleções anteriores.</p>
<div class="picker-options">@for(person of filtered();track person.id){<label class="picker-option"><input type="checkbox" [value]="person.id" [checked]="selected().includes(person.id)" (change)="toggle(person.id,$any($event.target).checked)" (blur)="touch()"> <span>{{person.name}} ({{person.username}})</span></label>}@empty{<p>{{people().length?'Nenhum responsável corresponde à busca.':'Selecione uma unidade com responsáveis disponíveis.'}}</p>}</div>
<p class="picker-summary" aria-live="polite">{{selected().length}} responsável(is) selecionado(s).</p>
@if(selected().length){<ul class="picker-selected" aria-label="Responsáveis selecionados">@for(id of selected();track id){<li><span>{{name(id)}}</span><button type="button" (click)="toggle(id,false)" [attr.aria-label]="'Remover '+name(id)">Remover</button></li>}</ul>}
</fieldset>`})
export class PersonPicker implements ControlValueAccessor {
 invalid=input(false);errorId=input('');people=input<Person[]>([]);label=input('Responsáveis pela execução');prefix=input('people');selected=signal<string[]>([]);search=signal('');disabled=signal(false);
 filtered=computed(()=>{const term=this.search().trim().toLocaleLowerCase('pt-BR');return this.people().filter(person=>(person.name+' '+person.username).toLocaleLowerCase('pt-BR').includes(term));});
 private change:(value:string[])=>void=()=>{};touch:()=>void=()=>{};
 name(id:string){const person=this.people().find(p=>p.id===id);return person?person.name+' ('+person.username+')':'Responsável indisponível';}
 writeValue(value:string[]|null){this.selected.set(value?[...value]:[]);this.search.set('');}
 registerOnChange(fn:(value:string[])=>void){this.change=fn;}
 registerOnTouched(fn:()=>void){this.touch=fn;}
 setDisabledState(value:boolean){this.disabled.set(value);}
 toggle(id:string,checked:boolean){if(this.disabled())return;const value=checked?[...new Set([...this.selected(),id])]:this.selected().filter(item=>item!==id);this.selected.set(value);this.change(value);this.touch();}
}
