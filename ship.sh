#!/bin/bash
set -e
git push
docker build -t siddharths96/karaoke .
docker push siddharths96/karaoke
