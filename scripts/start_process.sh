#!/bin/bash

USAGE="Usage: $0 [--alarm] [--control] [--convert] [--device <device>] [--hypervisor]"
folder="/global/software/doberman/Doberman"

x=0

while [[ $1 =~ ^- && ! $1 == '--' ]]; do case $1 in
  --alarm )
    target="alarm"
    screen_name="alarm_monitor"
    x=$((x+1))
    ;;
  --control )
    target="control"
    screen_name="control_pipeline"
    x=$((x+1))
    ;;
  --convert )
    target="convert"
    screen_name="convert_pipeline"
    x=$((x+1))
    ;;
  -d | --device )
    shift
    name=$1
    target="device"
    screen_name=$1
    x=$((x+1))
    ;;
  --hypervisor )
    target="hypervisor"
    screen_name="hypervisor"
    x=$((x+1))
    ;;
  * )
    echo $USAGE
    exit 1
    ;;
esac; shift; done

if [[ $x != 1 ]]; then
  echo $USAGE
  exit 1
fi

if [[ -n $(screen -ls | grep $screen_name ) ]]; then
  echo "Killing existing screen"
  screen -S $screen_name -X quit
fi
echo "cd $folder && ./Monitor.py --$target $name"
screen -S $screen_name -dm /bin/bash -c "cd $folder && ./Monitor.py --$target $name"
