#!/bin/sh

sudo /usr/local/bin/docker-compose -f docker-compose-prod.yml down
sudo docker image ls | grep registry.int.janelia.org | awk '{print $3}' | xargs sudo docker image rm
sudo docker volume rm config-manager_static_volume
sudo docker pull registry.int.janelia.org/jacs/configurator:latest
sudo /usr/local/bin/docker-compose -f docker-compose-prod.yml up -d
