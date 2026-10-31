import {Directive,HostListener,Injectable,inject,OnDestroy} from '@angular/core';
import {AbstractControl,FormGroupDirective} from '@angular/forms';
@Injectable({providedIn:'root'})
export class DraftGuard {
 private forms=new Set<DraftForm>();private acknowledged=false;
 register(form:DraftForm){this.forms.add(form);}
 remove(form:DraftForm){this.forms.delete(form);}
 reset(group:AbstractControl){for(const form of this.forms)form.resetFor(group);}
 hasChanges(){return [...this.forms].some(form=>form.dirty());}
 confirmDiscard(){
  if(!this.hasChanges()||this.acknowledged)return true;
  if(!window.confirm('Há alterações não salvas. Deseja descartá-las e sair?'))return false;
  // Nested close callbacks share this action; a failed departure must keep the draft dirty.
  this.acknowledged=true;queueMicrotask(()=>{this.acknowledged=false;});
  return true;
 }
}
@Directive({selector:'form[appDraftGuard]',standalone:true})
export class DraftForm implements OnDestroy {
 private guard=inject(DraftGuard);private form=inject(FormGroupDirective);private changed=false;
 constructor(){this.guard.register(this);}
 dirty(){return this.changed||this.form.form.dirty;}
 resetFor(group:AbstractControl){if(this.form.form===group){this.changed=false;group.markAsPristine();}}
 @HostListener('input',['$event']) @HostListener('change',['$event']) onChange(event:Event){if(event.target instanceof HTMLInputElement&&event.target.type==='search')return;this.changed=true;}
 @HostListener('window:beforeunload',['$event']) beforeUnload(event:BeforeUnloadEvent){if(this.dirty()){event.preventDefault();event.returnValue='';}}
 ngOnDestroy(){this.guard.remove(this);}
}
