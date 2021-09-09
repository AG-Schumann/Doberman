#!/usr/bin/env python3
import Doberman
from pymongo import MongoClient
import argparse
import os
import threading
from functools import partial
import datetime

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

    db_kwargs = {'mongo_client' : mongo_client, 'loglevel' : args.log}
    try:
        db_kwargs['experiment_name'] = os.environ['DOBERMAN_EXPERIMENT_NAME']
    except KeyError:
        print('You haven\'t specified an experiment, this might go badly')
    db = Doberman.Database(**db_kwargs)
    kwargs = {'db' : db, 'loglevel' : args.log}
    # TODO add checks for running systems
    if args.alarm:
        ctor = partial(Doberman.AlarmMonitor, **kwargs)
    elif args.host:
        doc = db.GetHostSetting(db.hostname)
        if doc['status'] == 'online':
            if (datetime.datetime.utcnow() - doc['heartbeat']).seconds < 2*doc['heartbeat_timer']:
                print(f'Host monitor {db.hostname}  already online!')
                return
            else:
                print(f'Host monitor {db.hostname} crashed?')
        ctor = partial(Doberman.HostMonitor, **kwargs)
    elif args.sensor:
        kwargs['_name'] = args.sensor
        if 'Test' in args.sensor:
            db.experiment_name = 'testing'
        # check if sensor is already running, otherwise start it
        else:
            ctor = partial(Doberman.SensorMonitor, **kwargs)
    elif args.status:
        doc = db.GetCurrentStatus()
        print('Status snapshot:')
        for host in doc:
            print('Status for %s: %s (%.1f s ago)' % (host, doc[host]['status'], doc[host]['last_heartbeat']))
            if doc[host]['status'] == 'offline':
                print()
                continue
            for sensor, subdoc in doc[host]['sensors'].items():
                print()
                print('  %s: last heartbeat %.1f s ago' % (sensor, subdoc['last_heartbeat']))
                for rd, rddoc in subdoc['readings'].items():
                    if rddoc['status'] == 'online':
                        if rd == 'vbias': 
                            print('    %s (%s): %s, %s runmode, last value %.3f (%.1f s ago)' % (
                                rddoc['description'], rd, rddoc['status'], rddoc['runmode'],
                                rddoc['last_measured_value'], rddoc['last_measured_time']))
                        else:
                            print('    %s (%s): %s, %s runmode, last value %.1f (%.1f s ago)' % (
                                rddoc['description'], rd, rddoc['status'], rddoc['runmode'],
                                rddoc['last_measured_value'], rddoc['last_measured_time']))
                    else:
                        print('    %s (%s): %s' % (rddoc['description'], rd, rddoc['status']))
            print()
            print()

        return
    else:
        return
    monitor = ctor()
    if threading.current_thread() is threading.main_thread():
        while not monitor.sh.event.is_set():
            monitor.event.wait(10)
    print('Shutting down')
    monitor.Shutdown()
    del monitor
    print('Main returning')

if __name__ == '__main__':
    try:
        mongo_uri = os.environ['DOBERMAN_MONGO_URI']
    except KeyError:
        with open(os.path.join(Doberman.utils.doberman_dir, 'connection_uri'), 'r') as f:
            mongo_uri = f.read().strip()
    with MongoClient(mongo_uri) as mongo_client:
        main(mongo_client)
