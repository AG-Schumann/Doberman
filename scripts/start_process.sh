#!/bin/bash

USAGE="Usage: $0 <sensor|pipeline> <name>"
folder="/global/software/doberman/Doberman"

if [[ $# -ne 2 || -z $2 ]]; then
  echo $USAGE
  exit 1
fi

case $1 in
  sensor )
    ;;
  pipeline )
    ;;
  * )
    echo $USAGE
    exit 1
    ;;
esac

if [[ -n $(screen -ls | grep $2 ) ]]; then
  echo "Killing existing screen"
  screen -S $2 -X quit
fi
echo "Starting $1 $2"
screen -S $2 -dm /bin/bash -c "cd $folder && ./Monitor.py --$1 $2"
