#!/usr/bin/env python3
import Doberman
from pymongo import MongoClient
import argparse
import time
import os
from functools import partial
import socket


def main(client):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--alarm', action='store_true', help='Start the alarm monitor')
    group.add_argument('--host', action='store_true', help='Start this host\'s monitor')
    group.add_argument('--sensor', help='Start the specified sensor monitor')
    group.add_argument('--status', action='store_true', help='Current status snapshot')
    args = parser.parse_args()

    # TODO add checks for running systems
    if args.alarm:
        db = Doberman.Database(client, appname='AlarmMonitor')
        ctor = partial(Doberman.AlarmMonitor, 'AlarmMonitor', db)
    elif args.host:
        hostname = socket.getfqdn()
        db = Doberman.Database(client, appname='HostMonitor')
        ctor = partial(Doberman.HostMonitor, hostname, db)
    elif args.sensor:
        db = Doberman.Database(client, appname=args.sensor)
        ctor = partial(Doberman.SensorMonitor, args.sensor, db)
    elif args.status:
        pass
    else:
        return
    sh = Doberman.utils.SignalHandler()
    while sh.run:
        try:
            monitor = ctor()
            monitor.Setup()
            monitor.StartThreads()
            while monitor.sh.run:
                time.sleep(1)
            if 

if __name__ == '__main__':
    with MongoClient(os.environ['DOBERMAN_MONGO_URI']) as client:
        try:
            main(client)
        except Exception as e:
            print('Caught a %s: %s' % (type(e), e))
