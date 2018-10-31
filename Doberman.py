#!/scratch/anaconda3/bin/python3
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

__version__ = '3.0.0'

class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    Closes all processes in the end.
    '''

    def __init__(self, db):
        self.runmode = 'testing'
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_message_time = dtnow()

        self.db = db
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : True,
            'runmode' : self.runmode, 'status' : 'online'}})

        self.alarmDistr = alarmDistribution.alarmDistribution(db)

    def close(self):
        """
        Shuts down
        """
        if self.db is None:  # already shut down
            return
        self.logger.info('Shutting down')
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : False,
            'status' : 'offline'}})
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
        cmd = '/scratch/anaconda3/envs/Doberman/bin/python3 Plugin.py --name %s --runmode %s' % (name, runmode)
        _ = Popen(cmd, shell=True, stdout=DEVNULL, stderr=DEVNULL, close_fds=False, cwd='/scratch/doberman')

    def watchBees(self):
        '''
        Watches all the bees
        '''
        self.sleep = False
        loop_time = 30
        self.logger.info('Watch ALL the bees!')
        sighand = utils.SignalHandler()
        self.start_time = dtnow()
        try:
            while not sighand.interrupted:
                loop_start_time = time.time()
                self.Heartbeat()
                if not self.sleep:
                    self.logger.debug('Still watching the bees...')
                    self.checkAlarms()
                    self.checkCommands()
                while (time.time()-loop_start_time) < loop_time and not sighand.interrupted:
                    time.sleep(1)
                    self.checkCommands()
        except Exception as e:
            self.logger.fatal("Caught fatal exception: %s | %s" % (type(e), str(e)))
        finally:
            self.close()

    def Heartbeat(self):
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'heartbeat' : dtnow()}})

    def checkCommands(self):
        select = lambda : {'name' : 'doberman', 'acknowledged' : {'$exists' : 0},
                'logged' : {'$lte' : dtnow()}}
        updates = lambda : {'$set' : {'acknowledged' : dtnow()}}
        doc = self.db.FindCommand(select(), updates())
        while doc is not None:
            self.logger.info('%s' % doc)
            command = doc['command']
            self.logger.info(f"Found '{command}'")
            if command == 'sleep':
                self.sleep = True
                self.db.updateDatabase('settings','defaults',{},{'$set' : {'status' : 'sleep'}})
            elif command == 'wake':
                self.sleep = False
                self.db.updateDatabase('settings','defaults',{},{'$set' : {'status' : 'online'}})
            elif command.startswith('start'):
                _, name = command.split()
                runmode = self.db.getDefaultSettings(name='runmode')
                self.StartController(name, runmode)
            elif command.startswith('runmode'):
                _, runmode = command.split()
                self.db.updateDatabase('settings','defaults',{},{'$set' : {'runmode' : runmode}})
                loglevel = self.db.getDefaultSettings(runmode=runmode,name='loglevel')
                self.logger.setLevel(int(loglevel))
            else:
                self.logger.error("Command '%s' not understood" % command)
            doc = self.db.FindCommand(select(), updates())
        return

    def checkAlarms(self):
        doc_filter_alarms = {'acknowledged' : {'$exists' : 0}, 'howbad' : 2}
        doc_filter_warns =  {'acknowledged' : {'$exists' : 0}, 'howbad' : 1}
        msg_format = '{name} : {when} : {msg}'
        messages = {'alarms' : [], 'warnings' : []}
        updates = {'$set' : {'acknowledged' : dtnow()}}
        while self.db.Count('logging','alarm_history',doc_filter_alarms):
            alarm = self.db.FindOneAndUpdate('logging','alarm_history',doc_filter_alarms, updates)
            messages['alarms'].append(msg_format.format(**alarm))
        while self.db.Count('logging','alarm_history',doc_filter_warns):
            warn = self.db.FindOneAndUpdate('logging','alarm_history',doc_filter_warns, updates)
            messages['warnings'].append(msg_format.format(**warn))
        if messages['alarms']:
            self.logger.warning(f'Found {len(messages["alarms"])} alarms!')
            self.sendMessage('\n'.join(messages['alarms']), 'alarm')
        if messages['warnings']:
            self.logger.warning(f'Found {len(messages["warnings"])} warnings!')
            self.sendMessage('\n'.join(messages['warnings']), 'warning')
        return

    def sendMessage(self, message, howbad):
        """
        Sends a warning/alarm to the appropriate contacts
        """
        # permanent testrun?
        runmode = self.db.getDefaultSettings(name='runmode')
        mode_doc = self.db.getDefaultSettings(runmode=runmode)
        testrun = mode_doc['testrun']
        if testrun == -1:
            self.logger.warning('Testrun, no alarm sent. Message: %s' % message)
            return -1
        now = dtnow()
        runtime = (now - self.start_time).total_seconds()/60
        # still a testrun?
        if runtime < testrun:
            self.logger.warning('Testrun still active (%.1f/%i min). Message (%s) not sent' % (runtime, testrun, message))
            return -2
        if (now - self.last_message_time).total_seconds()/60 < mode_doc['message_time']:
            self.logger.warning('Sent a message too recently (%i minutes), '
                'message timer at %i' % ((now - self.last_message_time).total_seconds()/60, mode_doc['message_time']))
            return -3
        # who to send to?
        sms_recipients = [c['sms'] for c in self.db.getContacts('sms')]
        mail_recipients = [c['email'] for c in self.db.getContacts('email')]
        sent_sms = False
        sent_mail = False
        if sms_recipients and howbad == 'alarm':
            if self.alarmDistr.sendSMS(sms_recipients, message) == -1:
                self.logger.error('Could not send SMS, trying mail...')
                additional_mail_recipients = [contact['email'] for contact
                                              in self.db.getContacts()
                                              if contact['sms'] in sms_recipients
                                              if '@' in contact['email']
                                              if contact['email'] not in mail_recipients]
                mail_recipients = mail_recipients + additional_mail_recipients
                if not mail_recipients:
                    self.logger.error('No one to email :(')
            else:
                self.logger.error('Sent SMS to %s' % sms_recipients)
                sent_sms = True
        if mail_recipients:
            subject = 'Doberman %s' % howbad
            if self.alarmDistr.sendEmail(toaddr=mail_recipients, subject=subject,
                                         message=message) == -1:
                self.logger.error('Could not send %s email!' % howbad)
            else:
                self.logger.info('Sent %s email to %s' % (howbad, mail_recipients))
                sent_mail = True
        if not any([sent_mail, sent_sms]):
            self.logger.critical('Unable to send message!')
            return -4
        self.last_message_time = now
        return 0

def main(db):
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')
    logger = logging.getLogger()
    logger.setLevel(20)
    runmodes = db.Distinct('settings','runmodes','mode')
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    logger.info('Starting up')
    # START PARSING ARGUMENTS
    parser.add_argument("--version",
                       action="store_true",
                       help="Print version and exit")
    parser.add_argument('--refresh', action='store_true', default=False,
                        help='Refresh the ttyUSB mapping')
    opts = parser.parse_args()
    if db.getDefaultSettings(name='online'):
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
            logging.shutdown()
            return 2
    # Load and start script
    doberman = Doberman(db)
    try:
        if doberman.Start():
            logger.error('Something went wrong here...')
        else:
            doberman.watchBees()
            logger.debug('Dem bees got dun watched')
    except Exception as e:
        logger.error(type(e))
        logger.error(str(e))
    finally:
        doberman.close()
        logging.shutdown()
    return 0

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    main(db)
    db.close()
