#!/usr/bin/env python3
import time
import logging
import DobermanDB
import alarmDistribution
import datetime
from argparse import ArgumentParser
import DobermanLogging
import Plugin
import psutil
from subprocess import Popen, PIPE, TimeoutExpired
from threading import Thread
import utils
import signal
dtnow = datetime.datetime.now

__version__ = '2.1.1'

class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    Closes all processes in the end.
    '''

    def __init__(self, db, runmode):
        self.runmode = runmode
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_message_time = dtnow()

        self.db = db
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : True,
            'runmode' : runmode}})

        self.alarmDistr = alarmDistribution.alarmDistribution(db)

    def close(self):
        """
        Shuts down
        """
        if self.db is None:  # already shut down
            return
        self.logger.info('Shutting down')
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : False}})
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
        self.logger.debug('tty settings last set %s, boot time %s' % (
            last_tty_update_time, boot_time))
        if boot_time > last_tty_update_time:
            if not utils.refreshTTY(self.db):
                self.logger.fatal('Could not assign tty ports!')
                return -1
        else:
            self.logger.debug('Not updating tty settings')
        return 0

    def startController(self, name, runmode=self.runmode):
        """
        Starts the specified controller and releases it into the wild
        """
        self.logger.info('Starting %s' % name)
        cmd = '/usr/bin/env python Plugin.py --name %s --runmode %s' % (name, runmode)
        _ = Popen(cmd, shell=True, stdout=DEVNULL, stderr=DEVNULL, close_fds=False, cwd='/scratch/doberman')

    def watchBees(self):
        '''
        Watches all the bees
        '''
        self.running = True
        self.loop_time = 30
        self.logger.info('Watch ALL the bees!')
        sighandler = utils.SignalHandler()
        self.start_time = dtnow()
        try:
            while self.running and not sighandler.interrupted:
                self.logger.debug('Still watching the bees...')
                self.Heartbeat()
                loop_start_time = time.time()
                self.checkAlarms()
                self.checkCommands()
                while (time.time()-loop_start_time) < self.loop_time and self.running:
                    time.sleep(1)
                    self.checkCommands()
                    if sighandler.interrupted:
                        break
        except KeyboardInterrupt:
            self.logger.fatal("Program killed by ctrl-c")
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
            command = doc['command']
            self.logger.info(f"Found '{command}'")
            args = command.split(maxsplit=1)
            if len(args) > 1:
                command = args[0]
                args = args[1:]
            else:
                command = args[0]
            if command == 'stop':
                self.running = False
            elif command == 'restart':
                self.db.StoreCommand('all stop')
                time.sleep(10)
                self.startAllControllers()
            elif 'runmode' in command:
                try:
                    _, runmode = command.split()
                except ValueError:
                    self.logger.error("Could not understand command '%s'" % command)
                else:
                    self.db.updateDatabase('settings','defaults',{},{'$set' : {'runmode' : runmode}})
                    loglevel = self.db.getDefaultSettings(runmode=runmode,name=loglevel)
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
        while self.db.Count(doc_filter_alarms):
            alarm = self.db.FindOneAndUpdate('logging','alarm_history',doc_filter_alarms, updates)
            messages['alarms'].append(msg_format.format(**alarm))
        while self.db.Count(doc_filter_warns):
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

def main():
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')
    logger = logging.getLogger()
    logger.setLevel(20)
    db = DobermanDB.DobermanDB()
    runmodes = db._check('settings','runmodes').distinct('mode')
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    # START PARSING ARGUMENTS
    parser.add_argument('--runmode', default='default',type=str,
                        choices=runmodes,
                        help='Which operational mode to use')
    parser.add_argument("--version",
                       action="store_true",
                       help="Print version and exit")
    parser.add_argument('--refresh', action='store_true', default=False,
                        help='Refresh the ttyUSB mapping')
    opts = parser.parse_args()
    if db.getDefaultSettings(name='online'):
        print('Is there an instance of Doberman already running?')
        return 1
    if opts.version:
        print('Doberman version %s' % __version__)
        return 0
    loglevel = db.getDefaultSettings(runmode = opts.runmode, name='loglevel')
    logger.setLevel(int(loglevel))
    if opts.refresh:
        if not utils.refreshTTY(db):
            print('Failed!')
            db.close()
            return 2
    # Load and start script
    doberman = Doberman(db, opts.runmode)
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
        db.close()
    return 0

if __name__ == '__main__':
    return main()
