FROM python:3.12-slim AS assets
WORKDIR /assets
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend .
RUN DJANGO_SECRET_KEY=build-only-static-assets DJANGO_DEBUG=true DATABASE_ENGINE=sqlite python manage.py collectstatic --noinput
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist/agenda/browser /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
COPY --from=assets /assets/staticfiles /usr/share/nginx/html/static
