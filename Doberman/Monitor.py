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
    group.add_argument('--host', action='store_true', help='Start this host\'s monitor')
    group.add_argument('--sensor', help='Start the specified sensor monitor')
    group.add_argument('--status', action='store_true', help='Current status snapshot')
    args = parser.parse_args()

    db_kwargs = {'mongo_client': mongo_client}
    err_msg = 'Specify an experiment first! This can be done either as an environment variable '
    err_msg += 'DOBERMAN_EXPERIMENT_NAME or in the file experiment_name'
    try:
        db_kwargs['experiment_name'] = os.environ['DOBERMAN_EXPERIMENT_NAME']
    except KeyError:
        try:
            with open(os.path.join(Doberman.utils.doberman_dir, 'experiment_name'), 'r') as f:
                db_kwargs['experiment_name'] = f.read().strip()
        except FileNotFoundError:
            print(err_msg)
            return
    if len(db_kwargs['experiment_name']) == 0:
            print(err_msg)
            return
    db = Doberman.Database(**db_kwargs)
    kwargs = {'db': db}
    # TODO add checks for running systems
    if args.alarm:
        ctor = Doberman.AlarmMonitor
        kwargs['name'] = 'alarm_monitor'
    elif args.host:
        doc = db.get_host_setting(db.hostname)
        if doc['status'] == 'online':
            if (datetime.datetime.utcnow() - doc['heartbeat']).seconds < 2 * doc['heartbeat_timer']:
                print(f'Host monitor {db.hostname}  already online!')
                return
            print(f'Host monitor {db.hostname} crashed?')
        ctor = Doberman.HostMonitor
        kwargs['name'] = db.hostname
    elif args.sensor:
        ctor = Doberman.SensorMonitor
        kwargs['name'] = args.sensor
        if 'Test' in args.sensor:
            db.experiment_name = 'testing'
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
    if threading.current_thread() is threading.main_thread():
        while not monitor.sh.event.is_set():
            monitor.event.wait(10)
    print('Shutting down')
    monitor.shutdown()
    print('Main returning')


if __name__ == '__main__':
    try:
        mongo_uri = os.environ['DOBERMAN_MONGO_URI']
        with MongoClient(mongo_uri) as mongo_client:
            main(mongo_client)
    except KeyError:
        try:
            with open(os.path.join(Doberman.utils.doberman_dir, 'connection_uri'), 'r') as f:
                mongo_uri = f.read().strip()
            with MongoClient(mongo_uri) as mongo_client:
                main(mongo_client)
        except FileNotFoundError:
            print('I need the connection uri to the Config DB. Specify either as an environment', end=' ')
            print('variable DOBERMAN_MONGO_URI or in the file connection_uri in the Doberman directory')
