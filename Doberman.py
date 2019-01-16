#!/scratch/anaconda3/bin/python3
import time
import logging
import DobermanDB
import datetime
import Plugin
import psutil
from subprocess import Popen, PIPE, TimeoutExpired, DEVNULL
import utils
from DobermanOverwatch import Monitor
dtnow = datetime.datetime.now


class SensorMonitor(Overwatch):
    '''
    Class to monitor sensor status (and other hosts)
    '''

    def Start(self):
        last_tty_update_time = self.db.GetHostStatus(fieldname='tty_update')
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        self.logger.info('tty settings last set %s, boot time %s' % (
            last_tty_update_time, boot_time))
        if boot_time > last_tty_update_time:
            if not utils.refreshTTY(self.db, self.db.hostname):
                self.logger.fatal('Could not assign tty ports!')
                return -1
        else:
            self.logger.debug('Not updating tty settings')
        return 0

    def StartController(self, name, runmode='testing'):
        """
        Starts the specified controller and releases it into the wild
        """
        self.logger.info('Starting %s' % name)
        self.db.ManagePlugins(name, 'add')
        info_doc = self.db.GetHostInfo()
        cmd = '%s Plugin.py --name %s --runmode %s' % (info_doc['exe_dir'], name, runmode)
        _ = Popen(cmd, shell=True, stdout=DEVNULL, stderr=DEVNULL, close_fds=False, cwd=info_doc['cwd_dir'])

    def Overwatch(self):
        self.watchBees()

    def watchBees(self):
        '''
        Watches all the bees
        '''
        self.sleep = False
        loop_time = utils.heartbeat_timer
        self.logger.info('Watch ALL the bees!')
        sh = utils.SignalHandler(self.logger)
        self.start_time = dtnow()
        try:
            while not sh.interrupted:
                loop_start_time = time.time()
                self.Heartbeat()
                if not self.sleep:
                    self.logger.debug('Still watching the bees...')
                    self.checkCommands()
                while (time.time()-loop_start_time) < loop_time and not sh.interrupted:
                    time.sleep(1)
                    self.checkCommands()
        except Exception as e:
            self.logger.fatal("Caught fatal exception: %s | %s" % (type(e), str(e)))
        finally:
            self.close()

    def Heartbeat(self):
        self.db.Heartbeat('doberman')
        managed_plugins = self.db.getDefaultSettings(name='managed_plugins')
        for name in managed_plugins:
            time_since = self.db.CheckHeartbeat(name)
            if time_since > 3*utils.heartbeat_timer:
                self.logger.info('%s hasn\'t reported in recently (%i seconds). Let me try restarting it...' % (name, time_since))
                # log alarm?
                #self.db.updateDatabase('settings','controllers',cuts={'name' : name},
                #        updates={'$set' : {'status' : 'offline'}})
                runmode = self.db.ControllerSettings(name)['runmode']
                self.StartController(name, runmode=runmode)
                time.sleep(5)
                if self.db.CheckHeartbeat(name) > utils.heartbeat_timer:
                    self.logger.error('I can\'t restart %s')
                    alarm_doc = {'name' : 'doberman', 'when' : dtnow(), 'howbad' : 1,
                            'msg' : '%s has died and I can\'t restart it' % name}
                    self.db.logAlarm(alarm_doc)
                else:
                    self.logger.info('Looks like we\'re good')

    def checkCommands(self):
        doc = self.db.FindCommand('doberman')
        db_col = ('settings','defaults')
        while doc is not None:
            self.logger.debug('%s' % doc)
            command = doc['command']
            self.logger.info(f"Found '{command}'")
            if command == 'sleep':
                self.sleep = True
                self.db.updateDatabase(*db_col,{},{'$set' : {'status' : 'sleep'}})
            elif command == 'wake':
                self.sleep = False
                self.db.updateDatabase(*db_col,{},{'$set' : {'status' : 'online'}})
            elif command.startswith('start'):
                _, name, runmode = command.split()
                if runmode == 'None':
                    runmode = self.db.getDefaultSettings(name='runmode')
                self.StartController(name, runmode)
            elif command.startswith('runmode'):
                _, runmode = command.split()
                self.db.updateDatabase(*db_col,{},{'$set' : {'runmode' : runmode}})
                loglevel = self.db.getDefaultSettings(runmode=runmode,name='loglevel')
                self.logger.setLevel(int(loglevel))
            else:
                self.logger.error("Command '%s' not understood" % command)
            doc = self.db.FindCommand('doberman')
        return


def main(db):
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')
    logger = logging.getLogger()
    logger.setLevel(20)
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    logger.info('Starting up')

    parser.add_argument("--version",
                       action="store_true",
                       help="Print version and exit")
    parser.add_argument('--refresh', action='store_true', default=False,
                        help='Refresh the ttyUSB mapping')
    opts = parser.parse_args()
    if opts.refresh:
        if not utils.refreshTTY(db):
            logger.error('Failed!')
            return 2
    doc = db.getDefaultSettings()
    if doc['status'] == 'online':
        if (dtnow() - doc['heartbeat']).total_seconds() < 3*utils.heartbeat_timer:
            logger.error('Is there an instance of Doberman already running?')
            return 2
    if opts.version:
        logger.info('Doberman version %s' % __version__)
        return 0
    loglevel = db.getDefaultSettings(runmode = 'default', name='loglevel')
    logger.setLevel(int(loglevel))
    # Load and start script
    doberman = Doberman(db)
    try:
        db.updateDatabase('settings','defaults',{},{'$set' : {
            'runmode' : 'testing', 'status' : 'online'}})
        if doberman.Start():
            logger.error('Something went wrong here...')
        else:
            doberman.watchBees()
            logger.debug('Dem bees got dun watched')
    except Exception as e:
        logger.error(str(type(e)))
        logger.error(str(e))
    finally:
        db.updateDatabase('settings','defaults',{},{'$set' : {'status' : 'offline'}})
        doberman.close()
    return 0

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e),e))
    db.close()
