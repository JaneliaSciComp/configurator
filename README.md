# Configurator [![Picture](https://raw.github.com/janelia-flyem/janelia-flyem.github.com/master/images/HHMI_Janelia_Color_Alternate_180x40.png)](http://www.janelia.org)

[![GitHub last commit](https://img.shields.io/github/last-commit/JaneliaSciComp/configurator.svg)](https://github.com/JaneliaSciComp/configurator)
[![GitHub commit merge status](https://img.shields.io/github/commit-status/badges/shields/master/5d4ab86b1b5ddfb3c4a70a70bd19932c52603b8c.svg)](https://github.com/JaneliaSciComp/configurator)

[![Python](https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![nginx](https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white)](https://www.nginx.com/)
[![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/en/2.2.x/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Swagger](https://img.shields.io/badge/Swagger-85EA2D?style=for-the-badge&logo=Swagger&logoColor=white)](https://swagger.io/)

## REST API for generalized configuration

This python flask app provides REST API endpoints for centralized configuration. Configuration data is stored as JSON in a Mongo database, and backed up in flat files.

This system uses MongoDB, gunicorn and nginx, and depends on docker and docker-compose
to run.

To run on production:

    sh restart_prod.sh
    
## Installation

1. Update files for the MongoDB read/write user
    ```
    cp mongo-init_template.js mongo-init.js
    cp api/config_template.cfg api/config.cfg
    ```
2. In mongo-init.js, replace the asterisks with the desired password.
3. In api/config.cfg, on the MONGO_URI line:
   a. Replace the asterisks with the desired password.
   b. Replace "hostname" with the correct hostname.
4. Update docker-compose-prod.yml or docker-compose-dev.yml as appropriate to reflect
   the desired password for the root user in the MONGO_INITDB_ROOT_PASSWORD line.
5. Update nginx.conf or nginx-dev.conf as appropriate to reflect the correct hostname.
6. Run the application using restart_prod.sh or restart_dev.sh as appropriate.
7. The API is now available at `http://your-hostname/`. Opening this url in your browser will bring up the API documentation.


Rob Svirskas (<svirskasr@janelia.hhmi.org>)

[Scientific Computing](http://www.janelia.org/research-resources/computing-resources)  
