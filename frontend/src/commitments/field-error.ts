import {Component,input} from '@angular/core';
import {AbstractControl} from '@angular/forms';
@Component({selector:'app-field-error',standalone:true,template:`@if(message()){<small class="field-error" [id]="errorId()">{{message()}}</small>}`})
export class FieldError {
 control=input.required<AbstractControl>();label=input.required<string>();errorId=input.required<string>();
 message(){const c=this.control();if(!c.touched||!c.invalid)return '';if(c.hasError('required'))return 'Informe '+this.label()+'.';if(c.hasError('maxlength'))return 'Use no máximo '+c.getError('maxlength').requiredLength+' caracteres.';return 'Revise '+this.label()+'.';}
}
