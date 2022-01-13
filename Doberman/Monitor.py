#!/usr/bin/env python3
import Doberman
from pymongo import MongoClient
import argparse
import os
import threading
import datetime
import pprint


def main(mongo_client):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--alarm', action='store_true', help='Start the alarm monitor')
    group.add_argument('--hypervisor', action='store_true', help='Start the hypervisor')
    group.add_argument('--sensor', help='Start the specified sensor monitor')
    group.add_argument('--pipeline', help='Start a pipeline monitor')
    group.add_argument('--status', action='store_true', help='Current status snapshot')
    args = parser.parse_args()

    k = 'DOBERMAN_EXPERIMENT_NAME'
    err_msg = f'Specify an experiment first via the environment variable {k}'
    if not os.environ.get(k):
        print(err_msg)
        return
    db = Doberman.Database(mongo_client=mongo_client, experiment_name=os.environ[k])
    kwargs = {'db': db}
    # TODO add checks for running systems
    if args.alarm:
        ctor = Doberman.AlarmMonitor
        kwargs['name'] = 'alarm_monitor'
    elif args.hypervisor:
        doc = db.get_experiment_config(name='hypervisor')
        if doc['status'] == 'online':
            if (Doberman.utils.dtnow()-doc['heartbeat']).total_seconds < 2*doc['period']:
                print('Hypervisor already running')
                return
            print(f'Hypervisor crashed?')
        ctor = Doberman.Hypervisor
        kwargs['name'] = 'hypervisor'
    elif args.sensor:
        ctor = Doberman.SensorMonitor
        kwargs['name'] = args.sensor
        if 'Test' in args.sensor:
            db.experiment_name = 'testing'
    elif args.pipeline:
        kwargs['name'] = f'{args.pipeline}'
        ctor = Doberman.PipelineMonitor
    elif args.status:
        pprint.pprint(db.get_current_status())
        return
    else:
        print('No action specified')
        return
    logger = Doberman.utils.get_logger(name=kwargs['name'], db=db)
    db.logger = logger
    kwargs['logger'] = logger
    monitor = ctor(**kwargs)
    monitor.event.wait()
    print('Shutting down')
    monitor.close()
    del monitor
    print('Main returning')


if __name__ == '__main__':
    if not (mongo_uri := os.environ.get('DOBERMAN_MONGO_URI')):
        print('Please specify a valid MongoDB connection URI via the environment '
              'variable DOBERMAN_MONGO_URI')
    else:
        with MongoClient(mongo_uri) as mongo_client:
            main(mongo_client)
