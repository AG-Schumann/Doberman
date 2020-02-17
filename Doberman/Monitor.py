#!/usr/bin/env python
import Doberman
from pymongo import MongoClient
import argparse
import time
import os
import threading
from functools import partial
from socket import getfqdn

def main(mongo_client):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--alarm', action='store_true', help='Start the alarm monitor')
    group.add_argument('--host', action='store_true', help='Start this host\'s monitor')
    group.add_argument('--sensor', help='Start the specified sensor monitor')
    group.add_argument('--status', action='store_true', help='Current status snapshot')
    parser.add_argument('--log', choices=['DEBUG','INFO','WARNING','ERROR','FATAL'],
                                help='Logging level', default='INFO')
    args = parser.parse_args()

    kwargs = {'mongo_client' : mongo_client, 'loglevel' : args.log}
    try:
        kwargs['experiment_name'] = os.environ['DOBERMAN_EXPERIMENT_NAME']
    except KeyError:
        print('You haven\'t specified an experiment, this might go badly')
    db = Doberman.Database(**kwargs)
    kwargs = {'db' : db, 'loglevel' : args.log}
    # TODO add checks for running systems
    if args.alarm:
        ctor = partial(Doberman.AlarmMonitor, **kwargs)
    elif args.host:
        if db.GetHostSetting(db.hostname, 'status') == 'online':
            print(f'Host monitor {db.hostname}  already online!')
            return
        ctor = partial(Doberman.HostMonitor, **kwargs)
    elif args.sensor:
        kwargs['_name'] = args.sensor
        if 'Test' in args.sensor:
            db.experiment_name = 'testing'
        # check if sensor is already running, otherwise start it
        else:
            ctor = partial(Doberman.SensorMonitor, **kwargs)
    elif args.status:
        pass
    else:
        return
    monitor = ctor()
    if threading.current_thread() is threading.main_thread():
        while not monitor.sh.event.is_set():
            monitor.event.wait(10)
    print('Shutting down')
    monitor.Shutdown()
    print('Main returning')

if __name__ == '__main__':
    try:
        mongo_uri = os.environ['DOBERMAN_MONGO_URI']
    except KeyError:
        with open(os.path.join(Doberman.utils.doberman_dir, 'connection_uri'), 'r') as f:
            mongo_uri = f.read().strip()
    with MongoClient(mongo_uri) as mongo_client:
        main(mongo_client)
