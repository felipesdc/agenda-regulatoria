import {PendingCenter} from './pending/pending';
import {Component,inject,computed} from '@angular/core';
import {ActivatedRoute,Router,RouterLink} from '@angular/router';
import {toSignal} from '@angular/core/rxjs-interop';
import {Session} from './session';
import {Reports} from './reports/reports';
import {CustomFieldsAdmin} from './customfields/admin';
import {Notifications} from './notifications/notifications';
import {Calendar} from './calendar/calendar';
import {Commitments} from './commitments/commitments';
@Component({standalone:true,imports:[PendingCenter,RouterLink,Reports,CustomFieldsAdmin,Notifications,Calendar,Commitments],templateUrl:'./workspace-page.html'})
export class WorkspacePage {
 private session=inject(Session);private route=inject(ActivatedRoute);private router=inject(Router);
 private data=toSignal(this.route.data,{initialValue:this.route.snapshot.data});
 private params=toSignal(this.route.paramMap,{initialValue:this.route.snapshot.paramMap});
 profile=this.session.profile;units=this.session.units;
 section=computed(()=>this.data()['section']);linkedOccurrence=computed(()=>this.params().get('id')||'');
 openNotification(id:string){void this.router.navigate(['/compromissos',id]);}
 closeLinked(){void this.router.navigate(['/notificacoes']);}
}
