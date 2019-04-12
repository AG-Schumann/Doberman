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
import os


def main(db):
    names = db.Distinct('settings','sensors','name')
    runmodes = db.Distinct('settings','runmodes','mode')
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n Doberman plugin standalone')
    parser.add_argument('--name', type=str, dest='plugin_name', required=True,
                        help='Name of the sensor',choices=names)
    parser.add_argument('--runmode', type=str, dest='runmode', choices=runmodes,
                        help='Which run mode to use', default='testing')
    args = parser.parse_args()

    plugin_paths=[utils.doberman_dir]
    logger = logging.getLogger(args.plugin_name)
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    loglevel = db.getDefaultSettings(runmode=args.runmode,name='loglevel')
    logger.setLevel(int(loglevel))
    doc = db.GetSensorSettings(args.plugin_name)
    if doc['status'] != 'offline':
        if (datetime.datetime.now() - doc['heartbeat']).total_seconds() < 3*utils.heartbeat_timer:
            logger.fatal('%s already running!' % args.plugin_name)
            return
    if args.runmode == 'default' and os.environ['USER'] != 'doberman':
        print('Only doberman can start plugins in the default runmode')
        return
    db.updateDatabase('settings','sensors',{'name' : args.plugin_name},
            {'$set' : {'runmode' : args.runmode, 'status' : 'online'}})
    logger.info('Starting %s' % args.plugin_name)
    if 'feedback' in doc:
        ctor = FeedbackController
    elif 'blind' in doc:
        ctor = BlindPlugin
    else:
        ctor = Plugin
    try:
        plugin = ctor(db, args.plugin_name, plugin_paths)
        sh = plugin.sh
        plugin.start()
        while not sh.interrupted:
            loop_until = time.time() + utils.heartbeat_timer
            db.Heartbeat(plugin.name)
            logger.debug('I\'m still here')
            while time.time() < loop_until and not sh.interrupted:
                time.sleep(1)
            if plugin.has_quit or sh.interrupted:
                logger.info('Plugin stopped')
                break
            if not plugin.is_alive():
                logger.error('Sensor died! Restarting...')
                try:
                    sh.interrupted = True
                    plugin.join()
                    plugin = ctor(db, args.plugin_name, plugin_paths)
                    plugin.start()
                    sh = plugin.sh
                except Exception as e:
                    logger.critical('Could not restart: %s | %s' % (type(e), e))
                    sh.interrupted = True
                    plugin.join()
    except Exception as e:
        logger.fatal(f'Why did I catch a {type(e)} here? {e}')
    finally:
        db.updateDatabase('settings','sensors',{'name' : args.plugin_name},
                {'$set' : {'status' : 'offline'}})
        plugin.sh.interrupted = True
        plugin.join()
        logger.info('Shutting down')
        if plugin.has_quit or (hasattr(sh, 'signal_number') and sh.signal_number == 2):
            # only unmanage for SIGINT or 'stop' command, not SIGKILL
            db.ManagePlugins(args.plugin_name, 'remove')

    return

if __name__ == '__main__':
    db = DobermanDB.DobermanDB(appname="plugin")
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e), e))
    #except KeyboardInterrupt:
    #    print('Not catching anything')
    logging.shutdown()
    db.close()

