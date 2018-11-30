#!/usr/bin/env python3
import time
import logging
import DobermanDB
import argparse
import DobermanLogging
import utils
from BasePlugin import Plugin
from PID import FeedbackController
from BlindPlugin import BlindPlugin
import datetime


def main(db):
    names = db.Distinct('settings','controllers','name')
    runmodes = db.Distinct('settings','runmodes','mode')
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n Doberman plugin standalone')
    parser.add_argument('--name', type=str, dest='plugin_name', required=True,
                        help='Name of the controller',choices=names)
    parser.add_argument('--runmode', type=str, dest='runmode', choices=runmodes,
                        help='Which run mode to use', default='default')
    args = parser.parse_args()

    plugin_paths=['.']
    logger = logging.getLogger(args.plugin_name)
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    loglevel = db.getDefaultSettings(runmode=args.runmode,name='loglevel')
    logger.setLevel(int(loglevel))
    doc = db.ControllerSettings(args.plugin_name)
    if doc['status'] == 'online':
        if (datetime.datetime.now() - doc['heartbeat']).total_seconds < 3*utils.heartbeat_timer:
            logger.fatal('%s already running!' % args.plugin_name)
            return
    db.updateDatabase('settings','controllers',{'name' : args.plugin_name},
            {'$set' : {'runmode' : args.runmode, 'status' : 'online'}})
    logger.info('Starting %s' % args.plugin_name)
    if 'feedback' in doc:
        ctor = FeedbackController
    elif 'blind' in doc:
        ctor = BlindPlugin
    else:
        ctor = Plugin
    sh = utils.SignalHandler(logger)
    running = True
    try:
        plugin = ctor(db, args.plugin_name, plugin_paths)
        plugin.start()
        while running and not sh.interrupted:
            loop_start = time.time()
            db.Heartbeat(plugin.name)
            logger.debug('I\'m still here')
            while time.time() - loop_start < utils.heartbeat_timer and not sh.interrupted:
                time.sleep(1)
            if plugin.has_quit:
                logger.info('Plugin stopped')
                break
            if not (plugin.running and plugin.is_alive()):
                logger.error('Controller died! Restarting...')
                try:
                    plugin.running = False
                    plugin.join()
                    plugin = ctor(db, args.plugin_name, plugin_paths)
                    plugin.start()
                except Exception as e:
                    logger.critical('Could not restart: %s | %s' % (type(e), e))
                    plugin.running = False
                    plugin.join()
                    running = False
    except Exception as e:
        logger.fatal(f'Why did I catch a {type(e)} here? {e}')
    finally:
        db.updateDatabase('settings','controllers',{'name' : args.plugin_name},
                {'$set' : {'status' : 'offline'}})
        plugin.running = False
        plugin.join()
        logger.info('Shutting down')
        if hasattr(sh, 'signal_number') and sh.signal_number == 2:
            # only unmanage for SIGINT not SIGKILL
            db.ManagePlugins(args.plugin_name, 'remove')

    return

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e), e))
    db.close()

