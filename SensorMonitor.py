#!/scratch/anaconda3/bin/python3
import time
import logging
import DobermanDB
import datetime
import Plugin
import psutil
from subprocess import Popen, PIPE, TimeoutExpired, DEVNULL
import utils
from BaseMonitor import Monitor
dtnow = datetime.datetime.now


class SensorMonitor(Overwatch):
    '''
    Class to monitor sensor status
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
        host_info = self.db.GetHostSetting()
        cmd = '%s Plugin.py --name %s --runmode %s' % (host_info['python_exe'],
                name, runmode)
        _ = Popen(cmd, shell=True, stdout=DEVNULL, stderr=DEVNULL,
                close_fds=False, cwd=host_info['working_dir'])

    def Overwatch(self):
        managed_plugins = self.db.GetHostSetting('managed_plugins')
        for name in managed_plugins:
            time_since = self.db.CheckHeartbeat(name)
            if time_since > 3*utils.heartbeat_timer:
                self.logger.info('%s hasn\'t reported in recently (%i seconds). Let me try restarting it...' % (name, time_since))
                runmode = self.db.ControllerSettings(name)['runmode']
                self.StartController(name, runmode=runmode)
                time.sleep(5)
                if self.db.CheckHeartbeat(name) > utils.heartbeat_timer:
                    self.logger.error('I can\'t restart %s')
                    alarm_doc = {'name' : 'doberman', 'when' : dtnow(), 'howbad' : 0,
                            'msg' : '%s has died and I can\'t restart it' % name}
                    self.db.logAlarm(alarm_doc)
                    self.db.ManagePlugin(name, 'remove')
                else:
                    self.logger.info('Looks like we\'re good')

    def CheckCommands(self):
        doc = self.db.FindCommand()
        while doc is None:
            self.logger.debug('Found "%s"' % doc['command'])
            command = doc['command']
            if command == 'sleep':
                self.sleep = True
                self.db.SetHostSetting('status', 'sleep')
            elif command == 'wake':
                self.sleep = False
                self.db.SetHostSetting('status', 'online')
            elif command.startswith('start'):
                try:
                    _, name, runmode = command.split()
                except:
                    self.logger.error('Bad command: "%s"' % command)
                else:
                    if runmode == 'None':
                        runmode = self.db.GetHostSetting('runmode')
                    self.StartController(name, runmode)
            elif command.startswith('runmode'):
                try:
                    _, runmode = command.split()
                except:
                    self.logger.error('Bad command: "%s"' % command)
                self.db.SetHostSetting('runmode',runmode)
                loglevel = self.db.GetRunmodeSetting(runmode=runmode,
                        fieldname='loglevel')
                self.logger.setLevel(int(loglevel))
            else:
                self.logger.error('Command not understood: "%s"' % command)
            doc = self.db.FindCommand()

def main(db):
    parser = ArgumentParser(usage='%(prog)s [options] \n\nDoberman sensor monitor')
    logger = logging.getLogger()
    logger.setLevel(20)
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    logger.info('Starting up')

    parser.add_argument('--refresh', action='store_true', default=False,
                        help='Refresh the ttyUSB mapping')
    opts = parser.parse_args()
    if opts.refresh:
        if not utils.refreshTTY(db):
            logger.error('Failed!')
            return 2
    doc = db.GetHostSetting()
    if doc['status'] != 'offline':
        if (dtnow() - doc['heartbeat']).total_seconds() < 3*utils.heartbeat_timer:
            logger.error('Is the monitor already running on this host?')
            return 2
    loglevel = int(db.GetRunmodeSetting(runmode = 'default', fieldname='loglevel'))
    logger.setLevel(loglevel)
    # Load and start script
    monitor = ControllerMonitor(db)
    try:
        db.SetHostSetting('status','online')
        db.SetHostSetting('runmode','testing')
        if monitor.Start():
            logger.error('Something went wrong here...')
        else:
            monitor.LoopFcn()
            logger.debug('Shutting down')
    except Exception as e:
        logger.error(str(type(e)))
        logger.error(str(e))
    finally:
        db.SetHostSetting('status','offline')
        monitor.close()
    return 0

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e),e))
    db.close()
