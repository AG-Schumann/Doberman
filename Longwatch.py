#!/usr/bin/env python3
import DobermanDB
import argparse
import datetime
import time

def main():
    db = DobermanDB.DobermanDB()
    parser = argparse.ArgumentParser(usage='%(prog)s: like tail -f but for Doberman messages')
    parser.add_argument('--delay', type=int, default=5,
                        help='How often to refresh (in seconds)')
    parser.add_argument('--level', type=int, choices=range(10,60,10), default=20,
                        help='Minimum level of message to display')
    args = parser.parse_args()
    msg_format = '{when} | {level} | {name} | {funcname} | {lineno} | {msg}'
    try:
        while True:
            then = datetime.datetime.now() - datetime.timedelta(seconds = args.delay)
            cursor = db.readFromDatabase('logging','logs', {'when' : {'$gt' : then}, 'level' : {'$gte' : args.level}})
            for row in cursor:
                print(msg_format.format(**row))
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print('Quiting is for losers, but ok')
    finally:
        db.close()
    return

if __name__ == '__main__':
    main()
