#!/bin/sh

docker-compose -f docker-compose-dev.yml down
docker image ls | grep configurator-app | awk '{print $3}' | xargs docker image rm
docker volume rm config-manager_static_volume
#docker pull registry.int.janelia.org/jacs/configurator:latest
docker-compose -f docker-compose-dev.yml up -d
