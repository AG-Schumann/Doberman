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
import serial
dtnow = datetime.datetime.now

__version__ = '2.0.0'

class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    Closes all processes in the end.
    '''

    def __init__(self, runmode, overlord, force):
        self.runmode = runmode
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_message_time = dtnow()
        self.overlord = overlord
        self.force=force

        self.db = DobermanDB.DobermanDB()
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : True,
            'runmode' : runmode}})
        self.db.updateDatabase('settings','controllers',{'online' : False},
                {'$set' : {'runmode' : runmode}})

        self.plugin_paths = ['.']
        self.alarmDistr = alarmDistribution.alarmDistribution()

    def close(self):
        """
        Shuts down all plugins (if it started them)
        """
        self.logger.info('Shutting down')
        self.db.updateDatabase('settings','defaults',{},{'$set' : {'online' : False}})
        if self.overlord:
            self.db.StoreCommand('all stop')
        self.db.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def Start(self):
        if not self.overlord:
            return 0
        last_tty_update_time = self.db.getDefaultSettings(name='tty_update')
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        self.logger.debug('tty settings last set %s, boot time %s' % (
            last_tty_update_time, boot_time))
        if boot_time > last_tty_update_time:
            if not self.refreshTTY():
                self.logger.fatal('Could not assign tty ports!')
                return -1
        else:
            self.logger.debug('Not updating tty settings')
        self.startAllControllers()
        return 0

    def refreshTTY(self):
        """
        Brute-force matches sensors to ttyUSB assignments by trying
        all possible combinations, and updates the database
        """
        collection = self.db._check('settings','controllers')
        if collection.count({'online' : True, 'address.ttyUSB' : {'$exists' : 1}}):
            self.logger.error('Some USB controllers are running! Can\'t refresh TTY settings')
            return False
        self.db.updateDatabase('settings','controllers',cuts={'address.ttyUSB' : {'$exists' : 1}}, updates={'$set' : {'address.ttyUSB' : -1}})
        self.logger.info('Refreshing ttyUSB mapping...')
        proc = Popen('ls /dev/ttyUSB*', shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=5)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if not len(out) or len(err):
            raise OSError('Could not check ttyUSB! stdout: %s, stderr %s' % (out.decode(), err.decode()))
        ttyUSBs = out.decode().splitlines()
        cursor = self.db.readFromDatabase('settings','controllers', {'address.ttyUSB' : {'$exists' : 1}}) # only need to do this for serial devices
        sensor_config = {}
        for row in cursor:
            sensor_config[row['name']] = row
        sensor_names = list(sensor_config.keys())
        sensors = {name: None for name in sensor_names}
        matched = {'sensors' : [], 'ttys' : []}
        for sensor in sensor_names:
            opts = {}
            opts['name'] = sensor
            opts['initialize'] = False
            opts.update(sensor_config[sensor]['address'])
            if 'additional_params' in sensor_config[sensor]:
                opts.update(sensor_config[sensor]['additional_params'])
            if sensor == 'RAD7': # I dislike edge cases
                plugin_name = sensor
            else:
                plugin_name = sensor.rstrip('0123456789')
            sensors[sensor] = Plugin.FindPlugin(plugin_name, self.plugin_paths)(opts)

        dev = serial.Serial()
        for tty in ttyUSBs:
            tty_num = int(tty.split('USB')[-1])
            self.logger.debug('Checking %s' % tty)
            dev.port = tty
            try:
                dev.open()
            except serial.SerialException as e:
                self.logger.error('Could not connect to %s: %s' % (tty, e))
                continue
            for name, sensor in sensors.items():
                if name in matched['sensors']:
                    continue
                if sensor.isThisMe(dev):
                    self.logger.debug('Matched %s to %s' % (tty_num, name))
                    matched['sensors'].append(name)
                    matched['ttys'].append(tty_num)
                    self.db.updateDatabase('settings','controllers',
                            {'name' : name}, {'$set' : {'address.ttyUSB' : tty_num}})
                    dev.close()
                    break
                self.logger.debug('Not %s' % name)
                time.sleep(0.5)  # devices are slow
            else:
                self.logger.error('Could not assign %s!' % tty)
            dev.close()

        if len(matched['sensors']) == len(sensors)-1: # n-1 case
            name = (set(sensors.keys())-set(matched['sensors'])).pop()
            tty = (set(ttyUSBs) - set(matched['ttys'])).pop()
            self.logger.debug('Matched %s to %s via n-1' % (name, tty))
            self.db.updateDatabase('settings','controllers',{'name' : name},
                    {'$set' : {'address.ttyUSB' : int(tty.split('USB')[-1])}})
        elif len(matched['sensors']) != len(sensors):
            self.logger.error('Didn\'t find the expected number of sensors!')
            return False
        self.db.updateDatabase('settings','defaults', {},
                {'$set' : {'tty_update' : dtnow()}})
        return True

    def startAllControllers(self):
        """
        Starts all not-running controllers and release them into the wild
        """
        self.logger.info('Starting all offline controllers')
        coll = self.db._check('settings','controllers')
        for name in coll.distinct('name', {'online' : False}):
            self.logger.info('Starting %s' % name)
            args = '--name %s --runmode %s' % (name, self.runmode)
            if self.force:
                args += ' --force'
            Thread(target=plugin.main, daemon=True, args=args.split()).start()
        time.sleep(5)

        print('\n--Alarm status:')
        for name,config in self.db.ControllerSettings().items():
            if not config['online']:
                continue
            alarm_status = config['alarm_status'][config[name]['runmode']]
            print('  %s: %s' % (name, alarm_status))

        print("\n--Contacts, status:")
        for contact in self.db.getContacts():
            print("  %s, %s" % (contact['name'], contact['status']))

    def watchBees(self):
        '''
        Watches all the bees
        '''
        self.running = True
        self.loop_time = 30
        self.logger.info('Watch ALL the bees!')
        try:
            while self.running:
                self.logger.info('Still watching the bees...')
                loop_start_time = time.time()
                self.checkAlarms()
                self.checkCommands()
                while (time.time()-loop_start_time) < self.loop_time and self.running:
                    time.sleep(1)
                    self.checkCommands()
        except KeyboardInterrupt:
            self.logger.fatal("\n\n Program killed by ctrl-c \n\n")
        finally:
            self.close()

    def checkCommands(self):
        collection = self.db._check('logging','commands')
        select = lambda : {'name' : 'doberman', 'acknowledged' : {'$exists' : 0},
                'logged' : {'$lte' : dtnow()}}
        updates = lambda : {'$set' : {'acknowledged' : dtnow()}}
        while collection.count(select()):
            updates = {'$set' : {'acknowledged' : dtnow()}}
            command = collection.find_one_and_update(doc_filter, updates())['command']
            self.logger.debug(f"Found '{command}'")
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
            else:
                self.logger.error("Command '%s' not understood" % command)
        return

    def checkAlarms(self):
        collection = self.db._check('logging','alarm_history')
        doc_filter_alarms = {'acknowledged' : {'$exists' : 0}, 'howbad' : 2}
        doc_filter_warns =  {'acknowledged' : {'$exists' : 0}, 'howbad' : 1}
        msg_format = '{name} : {when} : {msg}'
        messages = {'alarms' : [], 'warnings' : []}
        updates = {'$set' : {'acknowledged' : dtnow()}}
        self.logger.debug('%i alarms' % collection.count(doc_filter_alarms))
        while collection.count(doc_filter_alarms):
            alarm = collection.find_one_and_update(doc_filter_alarms, updates)
            messages['alarms'].append(msg_format.format(**alarm))
        self.logger.debug('%i warnings' % collection.count(doc_filter_warns))
        while(collection.count(doc_filter_warns)):
            warn = collection.find_one_and_update(doc_filter_warns, updates)
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
            self.logger.warning('Testrun, no alarm sent. Message: %s' % msg)
            return -1
        now = dtnow()
        runtime = (now - self.__startTime).total_seconds()/60
        # still a testrun?
        if runtime < testrun:
            self.logger.warning('Testrun still active (%.1f/%i min). Message (%s) not sent' % (runtime, testrun, msg))
            return -2
        if (now - self.last_message_time).total_seconds()/60 < mode_doc['message_time']:
            self.logger.warning('Sent a message too recently (%i minutes), '
                'message timer at %i' % ((now - self.last_message_time).total_seconds()/60, mode_doc['message_time']))
            return -3
        # who to send to?
        sms_recipients = [c.sms for c in self.db.getContacts('sms')]
        mail_recipients = [c.email for c in self.db.getContacts('email')]
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
                sms_recipients = []
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
                mail_recipients = []
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
    #handler = DobermanLogging.DobermanLogger()
    logger.addHandler(DobermanLogging.DobermanLogger())
    # START PARSING ARGUMENTS
    parser.add_argument('--runmode', default='default',type=str,
                        choices=['testing','default','recovery'],
                        help='Which operational mode to use')
    parser.add_argument("--version",
                       action="store_true",
                       help="Print version and exit")
    parser.add_argument('--start-all', action='store_true', default=False,
                        help='Starts all (not running) controllers, otherwise'
                        ' just monitor the alarms', dest='overlord')
    parser.add_argument('--force', action='store_true', default=False,
                        help='Ignore online status in database')
    opts = parser.parse_args()
    if db.getDefaultSettings(name='online') and not parser.force:
        print('Is there an instance of Doberman already running?')
        return
    if opts.version:
        print('Doberman version %s' % __version__)
        return
    loglevel = db.getDefaultSettings(runmode = opts.runmode, name='loglevel')
    logger.setLevel(int(loglevel))

    # Load and start script
    doberman = Doberman(opts.runmode, opts.overlord, opts.force)
    try:
        if doberman.Start():
            logger.error('Something went wrong here...')
        else:
            doberman.watchBees()
            logger.info('Dem bees got dun watched')
    except Exception as e:
        print(e)
    db.close()
    return

if __name__ == '__main__':
    main()
