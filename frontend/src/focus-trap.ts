import {Directive,ElementRef,inject} from '@angular/core';
@Directive({selector:'dialog[appFocusTrap]',standalone:true,host:{'(keydown)':'onKeydown($event)'}})
export class FocusTrap {
 private element=inject<ElementRef<HTMLDialogElement>>(ElementRef);
 onKeydown(event:KeyboardEvent){if(event.key!=='Tab')return;const dialog=this.element.nativeElement;if(!dialog.open)return;const items=Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])')).filter(e=>e.getClientRects().length>0&&e.tabIndex>=0);if(!items.length){event.preventDefault();dialog.focus();return;}const first=items[0];const last=items[items.length-1];const active=document.activeElement;if(event.shiftKey&&active===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&active===last){event.preventDefault();first?.focus();}}
}
