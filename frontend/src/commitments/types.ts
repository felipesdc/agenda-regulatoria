import {Evidence} from './evidence-panel';
import {FormSchema} from '../customfields/types';
export interface Person { id:string; username:string; name:string; }
export interface Catalog { id:string; name:string; active:boolean; }
export interface Unit { id:string; name:string; code:string; }
export interface Profile { id:string; username:string; name:string; administrator:boolean; memberships:{unit_id:string;unit__name:string;role:'requester'|'executor'}[]; }
export interface Page<T> {count:number; next:string|null; previous:string|null;results:T[];}
export interface ActionRecord {evidence:Evidence[];id:string;author_name:string;text:string;created_at:string;}
export interface Transition {id:string;actor_name:string;previous_status:string;new_status:string;reason:string;created_at:string;}
export interface Occurrence {form_version?:string|null;custom_values?:Record<string,unknown>;form_schema?:FormSchema|null; periodicity:string;scheduled_date:string|null;series_revision:number;can_manage_series:boolean;series_versions?:{revision:number;effective_from:string;rule:Record<string,unknown>;holidays:string[];reason:string}[]; id:string; identifier:string;title:string;description:string;legal_basis:string;reference_date:string;due_date:string;priority:string;status:string;revision:number;overdue:boolean;entity_name:string;category_name:string;unit_name:string;unit:string;requester_name:string;assignees:Person[];available_transitions:string[];can_edit:boolean;can_add_action:boolean;actions?:ActionRecord[];transitions?:Transition[];versions?:{revision:number;snapshot:Record<string,unknown>;created_at:string}[]; }
export interface AuditEvent {id:string;occurred_at:string;actor_name:string;operation:string;record_type:string;record_id:string;reason:string;before:Record<string,unknown>;after:Record<string,unknown>;}
