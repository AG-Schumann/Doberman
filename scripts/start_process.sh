#!/bin/bash

USAGE="Usage: $0 <sensor|pipeline|hypervisor> <name>"
folder="/global/software/doberman/Doberman"

if [[ $# -ne 2 || -z $2 && $1 != 'hypervisor' ]]; then
  echo $USAGE
  exit 1
fi

case $1 in
  sensor )
    ;;
  pipeline )
    ;;
  hypervisor )
    ;;
  * )
    echo $USAGE
    exit 1
    ;;
esac

if [[ $1 == 'hypervisor' ]]; then
  screen_name=$1
else
  screen_name=$2
fi

if [[ -n $(screen -ls | grep $screen_name ) ]]; then
  echo "Killing existing screen"
  screen -S $screen_name -X quit
fi
echo "Starting $1 $2"
screen -S $screen_name -dm /bin/bash -c "cd $folder && ./Monitor.py --$1 $2"
