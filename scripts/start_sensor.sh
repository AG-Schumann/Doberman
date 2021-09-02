#!/bin/bash

USAGE="Usage: $0 <sensor name>"

if [[ -n `screen -ls | grep $1` ]]; then
  echo "Killing existing screen"
  screen -S $1 -X quit
fi
echo "Startng $1"
screen -S $1 -dm /bin/bash -c "./Monitor.py --sensor $1"
