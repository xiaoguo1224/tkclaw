#!/bin/bash

CURRENT_VERSION=1.2

docker tag tkclaw-llm-proxy:latest 10.0.16.26:5000/tkclaw/tkclaw-llm-proxy:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-llm-proxy:v${CURRENT_VERSION}



docker tag tkclaw-nodeskclaw-backend:latest 10.0.16.26:5000/tkclaw/tkclaw-nodeskclaw-backend:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-nodeskclaw-backend:v${CURRENT_VERSION}


docker tag tkclaw-portal:latest 10.0.16.26:5000/tkclaw/tkclaw-portal:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-portal:v${CURRENT_VERSION}



