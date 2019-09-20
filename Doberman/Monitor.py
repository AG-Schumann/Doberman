#!/usr/bin/env python3
import Doberman
from pymongo import MongoClient
import argparse
import time
import os
from functools import partial


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

    db = Doberman.Database(mongo_client, loglevel=args.log)
    kwargs = {'db' : db, 'loglevel' : args.log}
    try:
        db.experiment_name = os.environ['DOBERMAN_EXPERIMENT_NAME']
    except KeyError:
        print('You haven\'t specified an experiment, this might go badly')

    # TODO add checks for running systems
    if args.alarm:
        ctor = partial(Doberman.AlarmMonitor, **kwargs)
    elif args.host:
        ctor = partial(Doberman.HostMonitor, **kwargs)
    elif args.sensor:
        kwargs['_name'] = args.sensor
        if 'Test' in args.sensor:
            db.experiment_name = 'testing'
        ctor = partial(Doberman.SensorMonitor, **kwargs)
    elif args.status:
        pass
    else:
        return
    sh = Doberman.utils.SignalHandler()
    monitor = None
    while sh.run:
        try:
            monitor = ctor()
            monitor.event.wait()
        except Exception as e:
            print('Caught a %s: %s' % (type(e), e))
        break
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
