#!/scratch/anaconda3/envs/Doberman/bin/python3
import time
import logging
import DobermanDB
import alarmDistribution
import datetime
from argparse import ArgumentParser
import DobermanLogging
import Plugin
import psutil
from subprocess import Popen, PIPE, TimeoutExpired, DEVNULL
from threading import Thread
import utils
import signal
dtnow = datetime.datetime.now

__version__ = '3.2.0'


class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    Closes all processes in the end.
    '''

    def __init__(self, db):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_message_time = None

        self.db = db

        self.alarmDistr = alarmDistribution.alarmDistribution(db)

    def close(self):
        """
        Shuts down
        """
        if self.db is None:  # already shut down
            return
        self.logger.info('Shutting down')
        self.db = None  # not responsible for cleanup here
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def Start(self):
        last_tty_update_time = self.db.getDefaultSettings(name='tty_update')
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        self.logger.info('tty settings last set %s, boot time %s' % (
            last_tty_update_time, boot_time))
        if boot_time > last_tty_update_time:
            if not utils.refreshTTY(self.db):
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
        cmd = '/scratch/anaconda3/envs/Doberman/bin/python3 Plugin.py --name %s --runmode %s' % (name, runmode)
        _ = Popen(cmd, shell=True, stdout=DEVNULL, stderr=DEVNULL, close_fds=False, cwd='/scratch/doberman')

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
                    self.checkAlarms()
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
                    alarm_doc = {'name' : 'doberman', 'when' : dtnow(), 'howbad' : 0,
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

    def checkAlarms(self):
        doc_filter = {'acknowledged' : {'$exists' : 0}}
        messages = {}
        msg_format = '{name} : {when} : {msg}'
        num_msg = 0
        updates = {'$set' : {'acknowledged' : dtnow()}}
        db_col = ('logging','alarm_history')
        if self.db.Count(*db_col, doc_filter) == 0:
            return
        for doc in self.db.readFromDatabase(*db_col, doc_filter, sort=[('howbad',-1)]):
            howbad = int(doc['howbad'])
            if (howbad,) not in messages:
                messages[(howbad,)] = []
            self.db.updateDatabase(*db_col, {'_id' : doc['_id']}, updates)
            messages[(howbad,)].append(doc)
            num_msg += 1
        if messages:
            self.logger.warning(f'Found {num_msg} alarms!')
            for (lvl,), msg_docs in messages.items():
                message = '\n'.join(map(lambda d : msg_format.format(**d), msg_docs))
                self.sendMessage(lvl, message)
        return

    def sendMessage(self, level, message):
        """
        Sends 'message' to the contacts specified by 'level'
        """
        # testrun?
        runmode = self.db.getDefaultSettings(name='runmode')
        mode_doc = self.db.getDefaultSettings(runmode=runmode)
        if mode_doc['testrun'] == -1:
            self.logger.warning('Testrun, will not send message: %s' % message)
            return -1
        now = dtnow()
        runtime = (now - self.start_time).total_seconds()/60

        if runtime < mode_doc['testrun']:
            self.logger.warning('Testrun still active (%.1f/%i min). Messages not sent' % (runtime, mode_doc['testrun']))
            return -2
        if self.last_message_time is not None:
            dt = (now - self.last_message_time).total_seconds()/60
            if dt < mode_doc['message_time']:
                self.logger.warning('Sent a message too recently (%i minutes), '
                    'message timer at %i' % (dt, mode_doc['message_time']))
                return -3

        for prot, recipients in self.db.getContactAddresses(level).items():
            if prot == 'sms':
                if self.alarmDistr.sendSMS(recipients, message) == -1:
                    self.logger.error('Could not send SMS')
                    return -4
            else:
                subject = 'Doberman alarm level %i' % level
                if self.alarmDistr.sendEmail(toaddr=recipients, subject=subject,
                                         message=message) == -1:
                    self.logger.error('Could not send email!')
                    return -5
        self.last_message_time = now
        return 0

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
    if opts.refresh:
        if not utils.refreshTTY(db):
            logger.error('Failed!')
            return 2
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
