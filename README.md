# charade
A Simultaneous Translator for mysql and JSON

MIT License
Copyright (c) 2018 Dean Stamler

Charade is a Python WSGI application that connects to a mysql database, loads the schema, and then presents a sensible JSON API based on that schema. Through configuration, it can also provide finer control over the JSON API it generates. Authentication is provided by Microsoft Azure AD.

Charade is built, tested, and deployed inside a Docker container.

### Installation
1. Set mysql and AzureAD environment variables in Dockerfile
2. cd /path/to/charade
3. [optional] edit config.py
3. docker build -t charade .

### Run
docker run -v /path/to/app:/app -p 9090:9090 charade

### TODO

- Write tests for the AzureADTokenValidator
- Make root return app-loading stuff for Vue.js and nothing more
- Make JSON api return errors formatted at JSON
- Finish all GET requests without customizations
- Build out generalized POST for creating new mysql objects
