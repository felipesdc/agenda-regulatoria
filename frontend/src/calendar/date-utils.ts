export type Scale='month'|'week'|'year';
export function iso(date:Date):string{return date.toISOString().slice(0,10);}
export function dateOf(value:string):Date{return new Date(value+'T12:00:00Z');}
export function shift(value:string,days:number):string{const d=dateOf(value);d.setUTCDate(d.getUTCDate()+days);return iso(d);}
export function weekStart(value:string):string{const d=dateOf(value);return shift(value,-((d.getUTCDay()+6)%7));}
export function monthStart(value:string):string{return value.slice(0,7)+'-01';}
export function monthGrid(value:string):string[]{const start=weekStart(monthStart(value));return Array.from({length:42},(_,i)=>shift(start,i));}
export function range(value:string,scale:Scale):[string,string]{if(scale==='year')return[value.slice(0,4)+'-01-01',value.slice(0,4)+'-12-31'];if(scale==='week'){const start=weekStart(value);return[start,shift(start,6)];}const days=monthGrid(value);return[days[0],days[41]];}
export function navigate(value:string,scale:Scale,direction:number):string{if(scale==='week')return shift(value,direction*7);const d=dateOf(value);const day=d.getUTCDate();d.setUTCDate(1);if(scale==='year')d.setUTCFullYear(d.getUTCFullYear()+direction);else d.setUTCMonth(d.getUTCMonth()+direction);const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0,12)).getUTCDate();d.setUTCDate(Math.min(day,last));return iso(d);}
