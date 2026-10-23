import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withXsrfConfiguration } from '@angular/common/http';
import { App } from './app';
bootstrapApplication(App,{providers:[provideHttpClient(withXsrfConfiguration({cookieName:'csrftoken',headerName:'X-CSRFToken'}))]}).catch(console.error);
