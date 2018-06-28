#!/usr/bin/env python3
import time
import logging
import os
import DobermanDB
import alarmDistribution
import queue
import threading
import datetime
import _thread
from _thread import start_new_thread
import sys
from argparse import ArgumentParser
import importlib
import importlib.machinery
import signal
import atexit
import Plugin


class options(object):
    pass

def clip(val, low, high):
    return max(min(val, high), low)

class Doberman(object):
    '''
    Doberman short for
       "Detector OBservation and Error Reporting Multiadaptive ApplicatioN"
       is a slow control software.
    Main program that regulates the slow control.
    First starts all controllers.
    Then starts an observation thread,
        which handels all data which come over the queue.
    Closes all processes in the end.
    '''

    def __init__(self, opts):
        self.opts = opts
        self.logger = logging.getLogger(__name__)

        self.queue = queue.Queue(0)
        self.path = os.getcwd()  # Gets path to the folder of this file

        self.DDB = DobermanDB.DobermanDB(opts)

        self._config = self.DDB.getConfig()
        self.alarmDistr = alarmDistribution.alarmDistribution(self.opts)

        self.plugin_search_paths = ['./Plugins']
        self.imported_plugins = self.importAllPlugins()
        self._running_controllers = self.startAllControllers()
        if self._running_controllers == -1:  # No controller was started
            self.__exit__(stop_observationThread=False)
            return
        self.observationThread = observationThread(
            self.opts, self._config, self._running_controllers)

    def importAllPlugins(self):
        '''
        This function tries to import all programs of the controllers
            which are saved in the database.
        After a plugin is imported it can be started by:
            getattr(imported_plugins[0], '%s_start'%plugin)()
        '''
        if self._config in ['', -1, -2]:
            self.logger.warning("Plugin settings (config) not loaded, can not start devices")
            return ['', '']
        elif self._config == "EMPTY":
            self.logger.error("Plugin settings (config) empty. Add your controllers settings "
                              "to the database first with "
                              "'python Doberman.py -a'.")
            return ['', '']
        self.failed_import = []
        imported_plugins = {}
        for device in self._config:
            controller = self._config[device]
            name = controller['controller']
            status = controller['status']
            if status != 'ON':
                self.logger.debug("Plugin '%s' is not imported as its status"
                                    " is '%s'", name, status)
                continue
            else:
                plugin = self.importPlugin(device)
                if plugin not in [-1, -2]:
                    imported_plugins[device] = plugin
                else:
                    self.failed_import.append(name)

        self.logger.info("The following plugins were successfully imported "
                         "(%i/%i): %s" % (len(imported_plugins),
                                          len(self._config),
                                          list(imported_plugins.keys())))
        return imported_plugins

    def importPlugin(self, controller):
        '''
        Imports a plugin
        '''
        # converting config entries into opts. values

        opts = options()
        for key, value in controller.items():
            setattr(opts, key, value)

        opts.queue = self.queue
        opts.path = os.getcwd()
        opts.plugin_paths = self.plugin_paths

        # Try to import libraries
        try:
            plugin = Plugin(opts)
        except Exception as e:
            self.logger.error("Can not add '%s'. %s " % (name, e))
            return -1
        self.logger.debug("Imported plugin '%s'" % name)
        return plugin

    def startPlugin(self, plugin):
        '''
        Starts a plugin
        '''
        try:
            self.started = True
            getattr(plugin, 'Run')()
        except Exception as e:
            self.logger.error("Failed to start plugin '%s', "
                              "error: %s" % (plugin.name, str(e)))
            self.started = False
            return -1
        return 0

    def startAllControllers(self):
        """
        Function that starts the master programs of all devices
        with status = ON, in different threats.
        """
        running_controllers = []
        failed_controllers = []
        if self._config in ['', -1, -2]:
            self.logger.error("Plugin settings (config) not loaded, can not start devices")
            return -1
        if self._config == "EMPTY":
            return -1
        for name, plugin in self.imported_plugins.items()
            # Try to start the plugin.
            self.logger.debug("Trying to start  device '%s' ..." % name)
            started = False
            self.started = False
            start_new_thread(self.startPlugin, plugin)
            time.sleep(0.5)  # Makes sure the plugin has time to react.
            if self.started:
                running_controllers.append(name)
                self.logger.debug("Successfully started plugin '%s'" % name)
            else:
                failed_controllers.append(name)

        # Summarize which plugins were started/imported/failed.
        # Also get alarm statuses and Testrun status.
        if len(running_controllers) > 0:
            self.logger.info("The following controller were successfully "
                             "started: %s" % str(running_controllers))
            print("\n" + 60 * '-')
            print("--Successfully started: %s" % str(running_controllers))
            print("--Failed to start: %s" % str(failed_controllers))
            print("--Failed to import: %s" % str(self.failed_import))

            print("\n--Alarm statuses:")
            for controller in running_controllers:
                print("  %s: %s" %
                      (controller, self._config[controller]['alarm_status']))
            print("\n--Enabled contacts, status:")

            for contact in self.DDB.getContacts():
                if contact[1] in ['ON', 'TEL', 'MAIL']:
                    print("  %s, %s" % (str(contact[0]), str(contact[1])))

            print("\n--Loaded connection details for alarms:")
            if self.alarmDistr.mailconnection_details:
                print("  Mail: Successfull.")
                if self.alarmDistr.smsconnection_details:
                    print("  SMS: Successfull.")
                else:
                    print("  SMS: Not loaded!")
            else:
                print("  Mail: Not loaded!")
                print("  SMS: Mail required!")

            if self.opts.testrun == -1:
                print("\n--Testrun:\n  Activated.")
            elif self.opts.testrun == 0:
                print("\n--Testrun:\n  Deactivated.")
            else:
                print("\n--Testrun:\n  Active for the first %s minutes." %
                      str(self.opts.testrun))
            print(60 * '-')
            return running_controllers
        else:
            self.logger.critical("No controller was started (Failed to import: "
                                 "%s, Failed to start: %s controllers)" %
                                 (str(len(self.failed_import)),
                                  str(len(failed_controllers))))
            return -1

    def observation_master(self):
        '''
        Checks that observation thread is still alive, restarts it if not
        '''
        yesno = False
        try:
            self.observationThread.start()
            # Loop for working until stopped.
            while True:
                self.logger.info("Main program still alive...")
                if yesno:
                    if (self.observationThread.stopped or not self.observationThread.isAlive()):
                        text = ("Observation thread died, Reviving... "
                                "(observationThread.stopped = %s, "
                                "obervationThread.isAlive() = %s)" %
                                (str(self.observationThread.stopped),
                                 str(self.observationThread.isAlive())))
                        self.logger.fatal(text)
                        # Restart observation Thread
                        self.observationThread = observationThread(
                            self.opts, self._config, self._running_controllers)
                        self.observationThread.start()
                time.sleep(30)
                yesno = not yesno
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("\n\n Program killed by ctrl-c \n\n")
            self.close()

    def close(self, stop_observationThread=True):
        """
        If the observationThread hasn't started use True to suppress error messages.
        """
        try:
            for plugin in self.imported_plugins:
                try:
                    getattr(plugin, "close")()
                except Exception as e:
                    self.logger.warning("Can not close plugin '%s' properly. "
                                        "Error: %s" % (plugin, e))
            try:
                self.observationThread.stopped = True
                self.observationThread.Tevent.set()
            except Exception as e:
                if stop_observationThread:
                    self.logger.warning("Can not stop observationThread "
                                        "properly: %s" % e)
        except Exception as e:
            self.logger.debug("Closing Doberman with an error: %s." % e)
        finally:
            return

    def __del__(self):
        self.close()
        return

    def __exit__(self, stop_observationThread=True):
        self.close(stop_observationThread)
        return


class observationThread(threading.Thread):
    '''
    Does all incoming jobs from the controllers:
    - Collects data,
    - Writes data to database (or file if no connection to database),
    - Checks value limits,
    - raises warnings and alarms.
    '''

    def __init__(self, opts, _config, _running_controllers):
        self.opts = opts
        self.logger = logging.getLogger(__name__)
        self.queue = opts.queue
        self._config = _config
        self._running_controllers = _running_controllers

        self.__startTime = datetime.datetime.now()
        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()
        self.waitingTime = 5
        self.DDB = DobermanDB.DobermanDB(opts)
        self.alarmDistr = alarmDistribution.alarmDistribution(opts)
        self.lastMeasurementTime = {(name, datetime.datetime.now())
                                    for name in self._config}
        self.lastAlarmTime = {(name, datetime.datetime.now())
                               for name in self._config}
        self.lastWarningTime = {(name, datetime.datetime.now())
                                 for name in self._config}
        self.sentAlarms = []
        self.sentWarnings = []
        self.recurrence_counter = self.initializeRecurrenceCounter()
        self.critical_queue_size = DDB.getDefaultSettings(name="Queue_size")
        if self.critical_queue_size < 5:
            self.critical_queue_size = 150

    def run(self):
        while not self.stopped:
            while not self.queue.empty():
                # Makes sure that the processing doesn't get too much behind.
                #excpected minimal processing rate: 25 Hz
                if self.queue.qsize() > self.critical_queue_size:
                    message = ("Data queue too long (queue length = %s). "
                               "Data processing will lag behind and "
                               "data can be lost! Reduce "
                               "the amount and frequency of data sent "
                               "to the queue!" % str(self.critical_queue_size))
                    self.logger.error(message)
                    self.critical_queue_size = self.critical_queue_size * 1.5
                    self.waitingTime = self.waitingTime / 2
                    self.sendWarning(name="Doberman", message=message, index=None)
                # Do the work
                job = self.queue.get()
                if len(job) < 2:
                    self.logger.warning("Unknown job: %s" % str(job))
                    continue
                self.logger.info("Processing data from '%s': %s" %
                                 (str(job[0])))
                self.processData(job)
            self.checkTimeDifferences()
            if self.queue.empty():
                self.critical_queue_size = DDB.getDefaultSettings(name="Queue_size")
                if self.critical_queue_size < 5:
                    self.critical_queue_size = 150
                self.logger.debug("Queue empty. Updating Plugin settings (config)...")
                self.updateConfig()
            if self.queue.empty():
                self.logger.debug("Queue empty. Sleeping for %s s..." %
                                  str(self.waitingTime))
                self.Tevent.wait(self.waitingTime)

    def processData(self, chunk):
        """
        Checks the data format and then passes it to the database and
        the data check.
        """
        self.checkData(*chunk)
        self.writeData(*chunk)

    def updateConfig(self):
        """
        Calls the DobermanDB.updateConfig() function to update config
        Makes sure it works out, otherwise continues without updating.
        """
        new_config = self.DDB.updateConfig(self._config)
        if new_config == -1:
            self.logger.warning("Could not update settings. Plugin settings (config) "
                                "loading failed. Continue with old settings...")
            return
        self._config = new_config

    def writeData(self, name, logtime, data=[0], status=[-2]):
        """
        Writes data to a database/file
        Status:
         0 = OK,
         -1 = no connection,
          -2 = No error status available,
          1-9 = warning
          > 9 = alarm
        """
        self.log.debug('Writing data from %s to database...' % name)
        if self.DDB.writeDataToDatabase(name, logtime, data, status):
            self.logger.error('Could not write data from %s to database' % name)

    def checkData(self, name, when, data, status):
        """
        Checks if all data is within limits, and start warning if necessary.
        """
        try:
            device = self._config[name]
        except KeyError:
            self.logger.error("No controller called %s. "
                              "Can not check data." % name)
            return -1
        al_stat = device['alarm_status']
        wlow = device['warning_low']
        whigh = device['warning_high']
        alow = device['alarm_low']
        ahigh = device['alarm_high']
        desc = device['description']
        readout_interval = device['readout_interval']

        # Actual status and data check.
        try:
            self.logger.debug('Checking data from %s' % name)
            for i in range(len(data)):
                if al_stat[i] == 'ON':
                    if status[i] != 0:
                        msg = 'Lost connection to %s? Status %i is %i' % (name, i, status[i])
                        num_recip = self.sendMessage(name, when, msg, 'warning', i)
                        self.logger.warning(msg)
                        self.DDB.addAlarmToHistory({'name' : name, 'index' : i, 'when' : when,
                            'status' : status[i], 'data' : data[i], 'reason' : 'NC',
                            'howbad' : 1, 'num_recip' : num_recip})
                    elif clip(data[i], alow[i], ahigh[i]) in [alow[i], ahigh[i]]:
                        msg = 'Reading %i from %s (%s, %.2f) is outside the alarm range (%.2f,%.2f)' % (
                            i, name, desc[i], data[i], alow[i], ahigh[i])
                        num_recip = self.sendMessage(name, when, msg, 'alarm', i)
                        self.logger.critical(msg)
                        self.DDB.addAlarmToHistory({'name' : name, 'index' : i, 'when' : when,
                            'status' : status[i], 'data' : data[i], 'reason' : 'alarm',
                            'howbad' : 2, 'num_recip' : num_recip})
                    elif clip(data[i], wlow[i], whigh[i]) in [wlow[i], whigh[i]]:
                        msg = 'Reading %i from %s (%s, %.2f) is outside the warning range (%.2f,%.2f)' % (
                            i, name, desc[i], data[i], wlow[i], whigh[i])
                        num_recip = self.sendMessage(name, when, msg, 'warning', i)
                        self.logger.warning(msg)
                        self.DDB.addAlarmToHistory({'name' : name, 'index' : i, 'when' : when,
                            'status' : status[i], 'data' : data[i], 'reason' : 'warning',
                            'howbad' : 1, 'num_recip' : num_recip})
                    else:
                        self.logger.debug('Reading %i from %s nominal' % (i, name))
                else:
                    self.logger.debug('Alarm status %i from %s is off, skipping...' % (i, name))
            time_diff = (when - self.lastMeasurementTime[name]).total_seconds()
            if time_diff > 2*readout_interval:
                msg = '%s last sent data %.1f sec ago instead of %i' % (
                    name, time_diff, readout_interval)
                self.logger.warning(msg)
                num_recip = self.sendMessage(name, when, msg, 'warning')
                self.DDB.addAlarmToHistory({'name' : name, 'when' : when, 'status' : status,
                    'data' : data, 'reason' : 'TD', 'howbad' : 1, 'num_recip' : num_recip})
            self.lastMeasurementTime[name] = when  # when will then be now?
        except Exception as e:
            self.logger.critical("Can not check data values and status from %s. Error: %s" % (name, e))

    def sendMessage(self, name, when, msg, howbad, index=0):
        """
        Sends a warning/alarm to the appropriate contacts
        """
        # permanent testrun?
        if self.opts.testrun == -1:
            self.logger.warning('Testrun, no alarm sent. Message: %s' % msg)
            return [-1, -1]
        now = datetime.datetime.now()
        runtime = (now - self.__startTime).total_seconds()/60
        # still a testrun?
        if runtime < self.opts.testrun:
            self.logger.warning('Testrun still active (%.1f/%i min). Message (%s) not sent' % (runtime, self.opts.testrun, msg))
            return [-1, -1]
        # when was last message sent?
        mintime = self._config[name]['alarm_recurrence'][index]
        if howbad == 'alarm':
            time_since = (now - self.lastAlarmTime[name]).total_seconds()/60
            if time_since < mintime:
                self.logger.debug('Alarm for %s sent recently (%.1f/%i min)' % (
                    name, time_since, mintime))
                return [-2,-2]
        elif howbad == 'warning':
            time_since = (now - self.lastWarningTime[name]).total_seconds()/60
            if time_since < mintime:
                self.logger.debug('Warning for %s send recently (%.1f/%i min)' % (
                    name, time_since, mintime))
                return [-2,-2]
        # who to send to?
        sms_recipients = [contact[3] for contact in self.DDB.getContacts()
                          if contact[1] in ['ON','TEL']]
        mail_recipients = [contact[2] for contact in self.DDB.getContacts()
                           if contact[1] in ['ON','TEL']]
        sent_sms = False
        sent_mail = False
        if sms_recipients and howbad == 'alarm':
            if self.alarmDistr.sendSMS(sms_recipients, msg) == -1:
                self.logger.error('Could not send SMS, trying mail...')
                additional_mail_recipients = [contact[2] for contact
                                              in self.DDB.getContacts()
                                              if contact[3] in sms_recipients
                                              if len(contact[2]) > 5
                                              if contact[2] not in mail_recipients]
                mail_recipients = mail_recipients + additional_mail_recipients
                sms_recipients = []
                if not mail_recipients:
                    self.logger.error('No one to email :(')
            else:
                self.logger.error('Send SMS to %s' % sms_recipients)
                sent_sms = True
                self.lastAlarmTime[name] = now
        if mail_recipients:
            subject = "%s: %s" % (howbad.upper(), name)
            if self.alarmDistr.sendEmail(toaddr=mail_recipients, subject=subject,
                                         message=msg) == -1:
                self.logger.error('Could not send %s email!' % howbad)
                mail_recipients = []
            else:
                self.logger.info('Sent %s email to %s' % (howbad, mail_recipients))
                sent_mail = True
                self.lastWarningTime[name] = now
        if not any([sent_mail, sent_sms]):
            self.logger.critical('Unable to send message!')
        return [len(sms_recipients), len(mail_recipients)]

class timeout:
    '''
    Timeout class. Raises an error when timeout is reached.
    '''

    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = str(error_message) + ' (%s s) exceeded' % seconds

    def handle_timeout(self, signum, frame):
        raise OSError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


def deleteLockFile(lockfilePath):
    os.remove(lockfilePath)

if __name__ == '__main__':

    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')
    # READING DEFAULT VALUES (need a logger to do so)
    logger = logging.getLogger()
    logger.setLevel(20)
    chlog = logging.StreamHandler()
    chlog.setLevel(20)
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:'
                                  '%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    opts = logger
    DDB = DobermanDB.DobermanDB(opts, logger)
    defaults = DDB.getDefaultSettings()
    # START PARSING ARGUMENTS
    # RUN OPTIONS
    import_default = DDB.getDefaultSettings(name='Importtimeout')
    if import_default < 1:
        import_default = 1
    parser.add_argument("-i",
                        "--importtimeout",
                        dest="importtimeout",
                        type=int,
                        help="Set the timout for importing plugins.",
                        default=import_default)
    testrun_default = DDB.getDefaultSettings(name='Testrun')
    parser.add_argument("-t", "--testrun",
                        dest='testrun',
                        nargs='?',
                        const=-1,
                        default=testrun_default,
                        type=int,
                        help=("Testrun: No alarms or warnings will be sent "
                              "for the time value given "
                              "(in minutes. e.g. -t=5: first 5 min) "
                              "or forever if no value is given."))
    loglevel_default = DDB.getDefaultSettings(name='Loglevel')
    if loglevel_default%10 != 0:
        loglevel_default = 20
    parser.add_argument("-d", "--debug", dest="loglevel",
                        type=int, help="switch to loglevel debug",
                        default=loglevel_default)
    # default occupied ttyUSB ports needs to be transformed as stored as string
    default_ports = [d[1] for d in defaults if d[0] == 'Occupied_ttyUSB'][0]
    if default_ports == '[]':
        default_ports = []
    else:
        default_ports = [int(port) for port in default_ports.strip('[').strip(']').split(',')]
    parser.add_argument("-o", "--occupied_USB_ports",
                        dest="occupied_ttyUSB",
                        nargs='*',
                        type=int,
                        help="Force program to NOT search ttyUSBx (x=int).",
                        default=default_ports)
    parser.add_argument("-ar", "--alarm_recurrence_time",
                        dest="alarm_recurrence",
                        type=int,
                        help=("Time in minutes until the same Plugin can send "
                              "an alarm (SMS/Email) again. Default = 5 min."),
                        default=[int(d[1]) for d in defaults if d[0] == 'Alarm_Repetition'][0])
    parser.add_argument("-wr", "--warning_repetition_time",
                        dest="warning_repetition",
                        type=int,
                        help=("Time in minutes until the same Plugin can send "
                              "a warning (Email) again. Default = 10 min."),
                        default=[int(d[1]) for d in defaults if d[0] == 'Warning_Repetition'][0])
    # CHANGE OPTIONS
    parser.add_argument("-n", "--new",
                        action="store_true",
                        dest="new",
                        help="(Re)Create tables config (Plugin settings), "
                             "config_history and contacts.",
                        default=False)
    parser.add_argument("-a", "--add",
                        action="store_true",
                        dest="add",
                        help="Add controller",
                        default=False)
    parser.add_argument("-u", "--update",
                        action="store_true",
                        dest="update",
                        help="Update main settings of a controller.",
                        default=False)
    parser.add_argument("-uu", "--update_all",
                        action="store_true",
                        dest="update_all",
                        help="Update all settings of a controller.",
                        default=False)
    parser.add_argument("-r", "--remove",
                        action="store_true",
                        dest="remove",
                        help="Remove an existing controller from the config (settings).",
                        default=False)
    parser.add_argument("-c", "--contacts",
                        action="store_true",
                        dest="contacts",
                        help="Manage contacts "
                             "(add new contact, change or delete contact).",
                        default=False)
    parser.add_argument("-ud", "--update_defaults",
                        action="store_true",
                        dest="defaults",
                        help="Update default Doberman settings "
                             "(e.g. loglevel, importtimeout,...).",
                        default=False)
    parser.add_argument("-f", "--filereading",
                        nargs='?',
                        const="configBackup.txt",
                        type=str,
                        dest="filereading",
                        help="Reading the Plugin settings from the file "
                             "instead of database and store the file settings "
                             "to the database.")
    opts = parser.parse_args()
    opts.path = os.getcwd()
    Y, y, N, n = 'Y', 'y', 'N', 'n'
    # Loglevel option
    logger.removeHandler(chlog)
    logger = logging.getLogger()
    if opts.loglevel not in [0, 10, 20, 30, 40, 50]:
        print("ERROR: Given log level %i not allowed. "
              "Fall back to default value of " % loglevel_default)
        opts.loglevel = loglevel_default
    logger.setLevel(int(opts.loglevel))
    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:'
                                  '%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    opts.logger = logger
    # Databasing options -n, -a, -u, -uu, -r, -c
    try:
        if opts.add:
            DDB.addControllerByKeyboard()
        if opts.update or opts.update_all:
            DDB.changeControllerByKeyboard(opts.update_all)
        if opts.remove:
            DDB.removeControllerFromConfig()
        if opts.contacts:
            DDB.updateContactsByKeyboard()
        if opts.defaults:
            DDB.updateDefaultSettings()
    except KeyboardInterrupt:
        print("\nUser input aborted! Check if your input changed anything.")
        sys.exit(0)
    except Exception as e:
        print("\nError while user input! Check if your input changed anything."
              " Error: %s", e)
    if opts.new:
        DDB.recreateTableConfigHistory()
        DDB.recreateTableAlarmHistory()
        DDB.recreateTableConfig()
        DDB.recreateTableContact()
    if opts.add or opts.update or opts.update_all or opts.remove or opts.contacts or opts.new or opts.defaults:
        text = ("Database updated. "
                "Do you want to start the Doberman slow control now (Y/N)?")
        answer = DDB.getUserInput(text, input_type=[str], be_in=[Y, y, N, n])
        if answer not in [Y, y]:
            sys.exit(0)
        opts.add = False
        opts.update = False
        opts.contacts = False
        opts.new = False

    lockfile = os.path.join(os.getcwd(), "doberman.lock")
    if os.path.exists(lockfile):
        print("The lockfile exists: is there an instance of Doberman already running?")
        sys.exit(0)
    else:
        with open(lockfile, 'w') as f:
            f.write('\0')
        atexit.register(deleteLockFile, lockfile)

    # Testrun option -t
    if opts.testrun == -1:
        print("WARNING: Testrun activated: No alarm / warnings will be sent.")
    elif opts.testrun == testrun_default:
        print("WARNING: Testrun=%d (minutes) activated by default: "
              "No alarms/warnings will be sent for the first %d minutes." %
              (testrun_default, testrun_default))
    else:
        print("Testrun=%s (minutes) activated: "
              "No alarms/warnings will be sent for the first %s minutes." %
              (str(opts.testrun), str(opts.testrun)))
    # Import timeout option -i
    if opts.importtimeout < 1:
        print("ERROR: Importtimeout to small. "
              "Fall back to default value of %d s" % import_default)
        opts.importtimeout = import_default
    # Occupied ttyUSB option -o
    with open("ttyUSB_assignement.txt", "w") as f:
        # Note that this automatically overwrites the old file.
        f.write("# ttyUSB | Device\n")
        for occupied_tty in opts.occupied_ttyUSB:
            f.write("    %d    |'Predefined unknown device'\n" % occupied_tty)
    # Filereading option -f
    if opts.filereading:
        print("WARNING: opt -f enabled: Reading Plugin Config from file"
              " '%s' and storing new settings to database... "
              "Possible changes in the database will be overwritten...!" %
              opts.filereading)
        try:
            DDB.storeSettingsFromFile(opts.filereading)
        except Exception as e:
            print("ERROR: Reading plugin settings from file failed! "
                  "Error: %s. Check the settings in the database for any "
                  "unwanted or missed changes." % e)
            text = ("Do you want to start the Doberman slow control "
                    "anyway (Y/N)?")
            answer = DDB.getUserInput(text, input_type=[str], be_in=[Y, y, N, n])
            if answer not in [Y, y]:
                sys.exit(0)
    # Load and start script
    slCo = Doberman(opts)
    try:
        slCo.observation_master()
    except AttributeError:
        pass
    except Exception as e:
        print(e)

    sys.exit(0)
