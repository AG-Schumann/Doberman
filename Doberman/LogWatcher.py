#!/usr/bin/env python3

import Doberman
import argparse
import datetime
import time
import os
from pymongo import MongoClient

def cuts(delay, level):
    then = datetime.datetime.now() - datetime.timedelta(seconds=delay)
    return {'when': {'$gte': then}, 'level': {'$gte': level}}


def main(db):
    parser = argparse.ArgumentParser(usage='%(prog)s: like tail -f but for Doberman messages')
    parser.add_argument('--delay', type=int, default=5,
                        help='How often to refresh (in seconds)')
    parser.add_argument('--level', type=int, choices=range(10, 60, 10), default=20,
                        help='Minimum level of message to display')
    args = parser.parse_args()
    msg_format = '{when} | {level} | {name} | {funcname} | {lineno} | {msg}'
    try:
        while True:
            for doc in db.read_from_db('logging', 'logs', cuts(args.delay, args.level)):
                print(msg_format.format(**doc))
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print('Quiting is for losers, but ok')
    return


if __name__ == '__main__':
    try:
        mongo_uri = os.environ['DOBERMAN_MONGO_URI']
        mongo_client = MongoClient(mongo_uri)
        experiment_name = os.environ['DOBERMAN_EXPERIMENT_NAME']
    except KeyError:
        print("Specify environment variables 'DOBERMAN_MONGO_URI' and 'DOBERMAN_EXPERIMENT_NAME'")
    else:
        db = Doberman.Database(mongo_client=mongo_client, experiment_name=experiment_name)
        try:
            main(db)
        except Exception as e:
            print('Caught a %s: %s' % (type(e), e))
        db.close()
