#!/bin/bash

if [ -z "$1" ]; then
    # 没有参数：输出错误信息到标准错误流
    echo "ERROR: 未传入版本号参数！"
    echo "用法: $0 <版本号>"
    exit 1
fi

CURRENT_VERSION=$1

docker tag tkclaw-llm-proxy:latest 10.0.16.26:5000/tkclaw/tkclaw-llm-proxy:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-llm-proxy:v${CURRENT_VERSION}



docker tag tkclaw-nodeskclaw-backend:latest 10.0.16.26:5000/tkclaw/tkclaw-nodeskclaw-backend:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-nodeskclaw-backend:v${CURRENT_VERSION}


docker tag tkclaw-portal:latest 10.0.16.26:5000/tkclaw/tkclaw-portal:v${CURRENT_VERSION}
docker push 10.0.16.26:5000/tkclaw/tkclaw-portal:v${CURRENT_VERSION}



