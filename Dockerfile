FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY admin.html /usr/share/nginx/html/admin.html
COPY demo.html /usr/share/nginx/html/demo.html
COPY register.html /usr/share/nginx/html/register.html
COPY status.html /usr/share/nginx/html/status.html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://localhost/ || exit 1
