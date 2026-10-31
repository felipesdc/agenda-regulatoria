import {Injectable} from '@angular/core';

export interface CommitmentQuery {
  q: string;
  status: string;
  overdue: boolean;
  record_id: string;
}
export interface CommitmentQueryState {
  filters: CommitmentQuery;
  page: number;
}

// Fallback for list links without query parameters. No localStorage or sessionStorage.
@Injectable({providedIn:'root'})
export class CommitmentQueryStore {
  private states = new Map<string,CommitmentQueryState>();
  read(user:string,mode:string):CommitmentQueryState|undefined {
    const state=this.states.get(user+':'+mode);
    return state?{page:state.page,filters:{...state.filters}}:undefined;
  }
  save(user:string,mode:string,state:CommitmentQueryState):void {
    this.states.set(user+':'+mode,{page:state.page,filters:{...state.filters}});
  }
  clear():void {this.states.clear();}
}
