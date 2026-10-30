import {provideRouter,withInMemoryScrolling} from '@angular/router';
import {routes} from './routes';
import {sessionExpiryInterceptor} from './session';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { App } from './app';
bootstrapApplication(App,{providers:[provideRouter(routes,withInMemoryScrolling({scrollPositionRestoration:'enabled'})),provideHttpClient(withInterceptors([sessionExpiryInterceptor]),withXsrfConfiguration({cookieName:'csrftoken',headerName:'X-CSRFToken'}))]}).catch(console.error);
