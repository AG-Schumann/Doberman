#!/bin/bash

USAGE="Usage: $0 [--alarm] [--control] [--convert] [--device <device>] [--hypervisor] [--debug]"
folder="/global/software/doberman/Doberman"

x=0
debug_mode=false

while [[ $1 =~ ^- && ! $1 == '--' ]]; do
  case $1 in
    --alarm )
      target="alarm"
      screen_name="pl_alarm"
      x=$((x+1))
      ;;
    --control )
      target="control"
      screen_name="pl_control"
      x=$((x+1))
      ;;
    --convert )
      target="convert"
      screen_name="pl_convert"
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
    --debug )
      debug_mode=true
      ;;
    * )
      echo $USAGE
      exit 1
      ;;
  esac
  shift
done

if [[ $x != 1 ]]; then
  echo $USAGE
  exit 1
fi

if [[ -n $(screen -ls | grep $screen_name ) ]]; then
  echo "Killing existing screen"
  screen -S $screen_name -X quit
fi

command="cd $folder && ./Monitor.py --$target $name"
if [ "$debug_mode" = true ]; then
  command+=" --debug"
fi

echo "$command"
screen -S $screen_name -dm /bin/bash -c "$command"
