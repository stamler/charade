FROM python:3.6-alpine3.7

# Install supervisor to run everything
# pcre is a dependency for the pip-supplied uwsgi
# openssl is a dependency for python cryptography. May be updated to libressl
# bash is installed for debugging
RUN apk add --no-cache supervisor pcre openssl bash

# Install python package requirements
COPY ./requirements.txt /app/requirements.txt
WORKDIR /app
RUN apk add --no-cache --virtual .build_deps \
      # Shared dependencies
      build-base python3-dev \
      # PyNaCl dependencies
      libffi-dev openssl-dev \
      # uWSGI dependencies
      linux-headers pcre-dev
RUN pip install --upgrade -r requirements.txt
RUN apk del .build_deps

COPY supervisor-uwsgi.ini /etc/supervisor.d/supervisord.ini
COPY ./app /app

# Permissions for uWSGI
RUN adduser -D uwsgi && \
    chown -R uwsgi:uwsgi /app

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 9090

ENV mysqlHost=hostname \
    mysqlUser=username mysqlPassword=password \
    mysqlDatabase=database \
    mysqlPort=3306 \
    azureTenant=mycompany.onmicrosoft.com \
    azureApp=https://mycompany.com/278faa1b-fc9e-3d9f-a87c-a001a21beee8

CMD ["/start.sh"]

# docker run -v /local/dev/dir/app:/app -p 9090:9090 falcon_app
