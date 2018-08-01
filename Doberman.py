#!/usr/bin/env python3
import time
import logging
import os
import DobermanDB
import alarmDistribution
import datetime
import sys
from argparse import ArgumentParser
import signal
import DobermanLogging
from Plugin import Plugin, FindPlugin
import psutil
from subprocess import Popen, PIPE, TimeoutExpired
import serial
import atexit

__version__ = '2.0.0'

class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    Closes all processes in the end.
    '''

    def __init__(self, runmode, standalone=False):
        self.runmode = runmode
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_message_time = datetime.datetime.now()
        self.standalone = standalone

        self.db = DobermanDB.DobermanDB()

        self.db.updateDatabase('settings','defaults',{},{'$set' : {'opmode' : runmode}})
        self.db.updateDatabase('settings','controllers',{},
                {'$set' : {'runmode' : runmode}})

        self.plugin_paths = ['.']
        self.alarmDistr = alarmDistribution.alarmDistribution()
        self.running_controllers = []

    def Start(self):
        if self.standalone:
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
        if self.importAllPlugins():
            self.logger.error('Could not import all plugins!')
            return -2
        self.startAllControllers()
        return 0

    def refreshTTY(self):
        """
        Brute-force matches sensors to ttyUSB assignments by trying
        all possible combinations, and updates the database
        """
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
            sensors[sensor] = FindPlugin(plugin_name, self.plugin_paths)(opts)

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
                time.sleep(0.5)  # devices are slow.....
            else:
                self.logger.error('Could not assign %s!' % tty)
            dev.close()

        if len(matched['sensors']) == len(sensors)-1: # n-1 case
            name = (set(sensors.keys())-set(matched['sensors'])).pop()
            tty = (set(ttyUSBs) - set(matched['ttys'])).pop()
            self.logger.debug('Matched %s to %s via n-1' % (name, tty))
            self.db.updateDatabase('settings','controllers',{'name' : name},
                    {'$set' : {'address.ttyUSB' : int(tty.split('USB')[-1])}})
            self.db.updateDatabase('settings','defaults', {},
                    {'$set' : {'tty_update' : datetime.datetime.now()}})
        elif len(matched['sensors']) != len(sensors):
            self.logger.error('Didn\'t find the expected number of sensors!')
            return False
        else:
            self.db.updateDatabase('settings','opmodes', {},
                    {'$set' : {'tty_update' : datetime.datetime.now()}})
        return True

    def importAllPlugins(self):
        '''
        This function tries to import all programs of the controllers
        which are saved in the database.
        '''
        self.failed_import = []
        imported_plugins = []
        devices = self.db.ControllerSettings()
        for name, controller in devices.items():
            try:
                self.logger.debug('Importing %s' % name)
                plugin = Plugin(name, self.plugin_paths)
            except Exception as e:
                self.logger.error('Could not import %s: %s' % (name, e))
                self.failed_import.append(name)
            else:
                self.logger.debug('Imported %s' % name)
                imported_plugins.append(plugin)

        self.logger.info("The following plugins were successfully imported "
                         "(%i/%i): %s" % (len(imported_plugins),
                                          len(devices),
                                          [p.name for p in imported_plugins]))
        self.imported_plugins = imported_plugins
        return 0

    def startAllControllers(self):
        """
        Function that starts the master programs of all devices
        with status = ON, in different threats.
        """
        running_controllers = []
        failed_controllers = []
        settings = self.db.ControllerSettings()
        while self.imported_plugins:
            plugin = self.imported_plugins.pop()
            # Try to start the plugin.
            self.logger.debug("Trying to start %s ..." % plugin.name)
            plugin.start()
            time.sleep(0.5)  # Makes sure the plugin has time to react.
            if plugin.running:
                running_controllers.append(plugin)
                self.logger.info("Successfully started %s" % plugin.name)
            else:
                failed_controllers.append(plugin.name)
                self.logger.info("Could not start %s" % plugin.name)
                plugin.close()

        # Summarize which plugins were started/imported/failed.
        # Also get alarm statuses and Testrun status.
        if running_controllers:
            print("\n--Alarm statuses:")
            for controller in running_controllers:
                name = controller.name
                alarm_status = settings[name]['alarm_status'][settings[name]['runmode']]
                print("  %s: %s" % (name, alarm_status))

            print("\n--Enabled contacts, status:")
            for contact in self.db.getContacts():
                print("  %s, %s" % (contact['name'], contact['status']))

            self.running_controllers = running_controllers
            return 0
        else:
            self.logger.critical("No controller was started (Failed to import: "
                                 "%s, Failed to start: %s)" %
                                 (str(len(self.failed_import)),
                                  str(len(failed_controllers))))
            self.running_controllers = []
            return -1

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
                if not self.standalone:
                    for i,plugin in enumerate(self.running_controllers):
                        if not (plugin.running and plugin.is_alive()):
                            self.logger.warning('%s died! Restarting...' % plugin.name)
                            try:
                                plugin.running = False
                                plugin.close()
                                plugin.join()
                                # can't restart threads, so remake the plugin
                                plugin = Plugin(plugin.name, self.plugin_paths)
                                plugin.start()
                                self.running_controllers[i] = plugin
                            except Exception as e:
                                self.logger.critical('Could not restart %s! %s' % (plugin.name, e))
                                plugin.running = False
                                plugin.close()
                                plugin.join()
                                self.running_controllers.pop(i)
                        else:
                            #self.logger.debug('%s is still live' % plugin.name)
                            pass
                self.checkCommands()
                while (time.time()-loop_start_time) < self.loop_time and self.running:
                    time.sleep(1)
                    self.checkCommands()
        except KeyboardInterrupt:
            self.logger.fatal("\n\n Program killed by ctrl-c \n\n")
        finally:
            self.close()

    def checkCommands(self):
        #self.logger.debug('Checking commands')
        collection = self.db._check('logging','commands')
        doc_filter = {'name' : 'doberman', 'acknowledged' : {'$exists' : 0}}
        while collection.count(doc_filter):
            updates = {'$set' : {'acknowledged' : datetime.datetime.now()}}
            command = collection.find_one_and_update(doc_filter, updates)['command']
            self.logger.debug(f"Found '{command}'")
            if command == 'stop':
                self.running = False
            elif command == 'restart':
                self.close()
                self.Start()
            elif 'runmode' in command:
                try:
                    _, runmode = command.split()
                except ValueError:
                    self.logger.error("Could not understand command '%s'" % command)
                else:
                    self.db.updateDatabase('settings','controllers',{},{'$set' : {'runmode' : runmode}})
            else:
                self.logger.error('Command %s not understood' % command)
        return

    def checkAlarms(self):
        self.logger.debug('Checking alarms')
        collection = self.db._check('logging','alarm_history')
        doc_filter_alarms = {'acknowledged' : {'$exists' : 0}, 'howbad' : 2}
        doc_filter_warns =  {'acknowledged' : {'$exists' : 0}, 'howbad' : 1}
        msg_format = '{name} : {when} : {msg}'
        messages = {'alarms' : [], 'warnings' : []}
        updates = {'$set' : {'acknowledged' : datetime.datetime.now()}}
        self.logger.debug('%i alarms' % collection.count(doc_filter_alarms))
        while collection.count(doc_filter_alarms):
            alarm = collection.find_one_and_update(doc_filter_alarms, updates)
            messages['alarms'].append(msg_format.format(**alarm))
        self.logger.debug('%i warnings' % collection.count(doc_filter_warns))
        while(collection.count(doc_filter_warns)):
            warn = collection.find_one_and_update(doc_filter_warns, updates)
            messages['warnings'].append(msg_format.format(**warn))
        if messages['alarms']:
            self.logger.warning('Found alarms! Sending message')
            self.sendMessage('\n'.join(messages['alarms']), 'alarm')
        if messages['warnings']:
            self.logger.warning('Found warnings! Sending message')
            self.sendMessage('\n'.join(messages['warnings']), 'warning')
        return

    def close(self):
        """
        Shuts down all plugins
        """
        self.logger.info('Shutting down')
        if self.standalone:
            return
        while self.running_controllers:
            plugin = self.running_controllers.pop()
            try:
                plugin.running = False
                #plugin.close() # plugin closes itself automatically
                plugin.join()
            except Exception as e:
                self.logger.warning("Can not close %s properly. "
                                    "Error: %s" % (plugin.name, e))
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def sendMessage(self, message, howbad):
        """
        Sends a warning/alarm to the appropriate contacts
        """
        # permanent testrun?
        runmode = self.db.readFromDatabase('settings','defaults',onlyone=True)['opmode']
        mode_doc = self.db.readFromDatabase('settings','opmodes',
                {'mode' : runmode}, onlyone=True)
        testrun = mode_doc['testrun']
        if testrun == -1:
            self.logger.warning('Testrun, no alarm sent. Message: %s' % msg)
            return -1
        now = datetime.datetime.now()
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
    DDB = DobermanDB.DobermanDB()
    #handler = DobermanLogging.DobermanLogger()
    logger.addHandler(DobermanLogging.DobermanLogger())
    # START PARSING ARGUMENTS
    parser.add_argument('--runmode', default='default',type=str,
                        choices=['testing','default','recovery'],
                        help='Which operational mode to use')
    parser.add_argument("--version",
                       action="store_true",
                       help="Print version and exit")
    parser.add_argument('--standalone', action='store_true', default=False,
                        help='Run Doberman in standalone mode (ie, don\'t load \
                        controllers here, just monitor the database)')
    opts = parser.parse_args()
    if opts.version:
        print('Doberman version %s' % __version__)
        return
    loglevel = DDB.getDefaultSettings(opmode = opts.runmode, name='loglevel')
    logger.setLevel(int(loglevel))

    lockfile = os.path.join(os.getcwd(), "doberman.lock")
    if os.path.exists(lockfile):
        print("The lockfile exists: is there an instance of Doberman already running?")
        return
    else:
        with open(lockfile, 'w') as f:
            f.write('\0')
        atexit.register(lambda x : os.remove(x), lockfile)

    # Load and start script
    doberman = Doberman(opts.runmode, opts.standalone)
    try:
        if doberman.Start():
            logger.error('Something went wrong here...')
        else:
            doberman.watchBees()
            logger.info('Dem bees got dun watched')
    except Exception as e:
        print(e)

    return

if __name__ == '__main__':
    main()
