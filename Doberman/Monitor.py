#!/usr/bin/env python3
import Doberman
from pymongo import MongoClient
try:
    from influxdb import InfluxDBClient
    has_influx=True
except ImportError:
    has_influx=False
try:
    from kafka import KafkaProducer
    has_kafka=True
except ImportError:
    has_kafka=False
import argparse
import time
import os
from functools import partial
import socket


def main(mongo_client, influx_client=None, kafka_producer=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--alarm', action='store_true', help='Start the alarm monitor')
    group.add_argument('--host', action='store_true', help='Start this host\'s monitor')
    group.add_argument('--sensor', help='Start the specified sensor monitor')
    group.add_argument('--status', action='store_true', help='Current status snapshot')
    args = parser.parse_args()

    db = Doberman.Database(mongo_client,
                           influx_client=influx_client,
                           kafka_producer=kafka_producer)

    # TODO add checks for running systems
    if args.alarm:
        ctor = partial(Doberman.AlarmMonitor, 'AlarmMonitor', db)
    elif args.host:
        hostname = socket.getfqdn()
        ctor = partial(Doberman.HostMonitor, hostname, db)
    elif args.sensor:
        if influx_client is None and kafka_producer is None:
            print('This host has neither Kafka nor Influx?? '
                    'What am I supposed to do with the data??')
            #return
        ctor = partial(Doberman.SensorMonitor, args.sensor, db)
    elif args.status:
        pass
    else:
        return
    sh = Doberman.utils.SignalHandler()
    monitor = None
    while sh.run:
        #try:
        monitor = ctor()
        monitor.StartThreads()
        while monitor.sh.run:
            time.sleep(1)
        #except Exception as e:
        #print('Caught a %s: %s' % (type(e), e))
        break
    monitor.Shutdown()
    print('Main returning')

if __name__ == '__main__':
    try:
        mongo_client = MongoClient(os.environ['DOBERMAN_MONGO_URI'])
    except KeyError:
        with open(os.path.join(Doberman.utils.doberman_dir, 'connection_uri'), 'r') as f:
            mongo_client = MongoClient(f.read().strip())
    if has_influx:
        influx_client = InfluxDBClient()
    else:
        influx_client = None
    if has_kafka:
        kafka_producer = KafkaProducer()
    else:
        kafka_producer = None
    #try:
    main(mongo_client, influx_client, kafka_producer)
    #except Exception as e:
    #    print('Caught a %s: %s' % (type(e), e))
    #finally:
    mongo_client.close()
    #    if has_influx:
    #        influx_client.close()
    #    if has_kafka:
    #        kafka_producer.close()
