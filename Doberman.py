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
import signal


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
        self.logger = self.opts.logger

        self.queue = queue.Queue(0)
        self.path = os.getcwd()  # Gets path to the folder of this file

        self.DDB = DobermanDB.DobermanDB(opts, logger)

        self._config = self.DDB.getConfig()
        self.alarmDistr = alarmDistribution.alarmDistribution(self.opts)

        self.imported_plugins, self.imported_plugins_name = self.importAllPlugins()
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
        imported_plugins = []
        imported_plugins_name = []
        all_plugins = []
        for device in self._config:
            name = str(device[0])
            status = str(device[1])
            all_plugins.append(name)
            if status != 'ON':
                self.logger.warning("Plugin '%s' is not imported as its status"
                                    " is '%s'", name, status)
                continue
            else:
                imp_plugin = self.importPlugin(device)
                if imp_plugin not in [-1, -2]:
                    imported_plugins_name.append(name)
                    imported_plugins.append(imp_plugin)
                else:
                    self.failed_import.append(name)

        self.logger.info("The following plugins were successfully imported "
                         "(%s/%s): %s" % (str(len(imported_plugins_name)),
                                          str(len(all_plugins)),
                                          imported_plugins_name))
        return [imported_plugins, imported_plugins_name]

    def importPlugin(self, plugin):
        '''
        Adds the path to the plugin and imports it.
        '''
        # converting config entries into opts. values
        #
        print("*******************")
        print(plugin)
        print("*******************")
        #

        name = plugin[0]
        opts.loginterval = plugin[7]
        opts.addresses = plugin[11]
        # for backwards compatibility
        if plugin[11][0] == 'LAN':
            opts.lan = True  # Use opts.connectiontype instead
            opts.serial = False  # Use opts.connectiontype instead
            opts.ipaddress = plugin[11][1]
            opts.port = plugin[11][2]
        elif plugin[11][0] == 'SER':
            opts.lan = False  # Use opts.connectiontype instead
            opts.serial = True  # Use opts.connectiontype instead
            opts.productID = plugin[11][1]
            opts.vendorID = plugin[11][2]
        else:
            opts.lan = False
            opts.ser = False
        opts.additional_parameters = plugin[12]
        opts.logger = self.logger
        opts.queue = self.queue
        opts.log_path = name
        try:  # Reading which ports are already occupied.
            with open(os.path.join(opts.path, 'ttyUSB_assignement.txt'), "r") as f:
                occupied_ttyUSB = []
                for line in f:
                    ttyUSB_line = line.split()[0]
                    if ttyUSB_line == '#':
                        continue
                    else:
                        occupied_ttyUSB.append(int(ttyUSB_line))
                opts.occupied_ttyUSB = occupied_ttyUSB
        except Exception as e:
            text = ("Can not read 'ttyUSB_assignement.txt'. Error %s. "
                    "Continue with only the predifined occupied ports "
                    "(%s). This might disturb an other controller." %
                    (e, str(opts.occupied_ttyUSB)))
            self.logger.warning(text)
        # Adds the paths
        try:
            sys.path.insert(0, '%s/Plugins/%s/' % (self.path, name))
        except Exception as e:
            self.logger.warning("Can not add path '%s/Plugins/%s/',  %s " %
                                (self.path, name, e))
            return -1
        self.logger.debug("Added path '%s/Plugins/%s/'" %
                          (self.path, name))
        # Try to import libraries
        try:
            with timeout(self.opts.importtimeout):
                __import__("%sControl" % name)
                temp_plugin = imp.load_module('%sControl' % name,
                                              '%s/Plugins/%s' %
                                              (self.path, name))
                imp_plugin = (getattr(temp_plugin,
                                      '%sControl' % name)(self.opts))
        except Exception as e:
            self.logger.error("Can not add '%s'. %s " % (name, e))
            return -1
        self.logger.debug("Imported plugin '%s'" % name)
        return imp_plugin

    def startPlugin(self, plugin, pluginname):
        '''
        Starts a plugin
        '''
        try:
            self.started = True
            getattr(plugin, '%scontrol' % pluginname)()
        except Exception as e:
            self.logger.error("Failed to start plugin '%s', "
                              "error: %s" % (pluginname, str(e)))
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
        for device in self._config:
            name = device[0]
            status = device[1]
            if status != 'ON':
                self.logger.warning("Controller '%s' is not started as its "
                                    "status is '%s'" %
                                    (name, status))
                continue
            # Compare if there is a imported plugin with this name.
            try:
                index = self.imported_plugins_name.index(name)
            except:
                self.logger.debug("Plugin '%s' is not started as was not "
                                  "imported successfully." % name)
                continue
            # Try to start the plugin.
            self.logger.debug("Trying to start  device '%s' ..." % name)
            started = False
            self.started = False
            start_new_thread(self.startPlugin,
                             (self.imported_plugins[index], name))
            time.sleep(0.1)  # Makes sure the plugin has time to react.
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
            print(("\n" + 60 * '-'))
            print(("--Successfully started: %s" % str(running_controllers)))
            print(("--Failed to start: %s" % str(failed_controllers)))
            print(("--Failed to import: %s" % str(self.failed_import)))

            print("\n--Alarm statuses:")
            for controller in running_controllers:
                print(("  %s: %s" %
                      (controller,
                       str([dev[2] for dev in self._config
                            if dev[0] == controller][0]))))
            print("\n--Enabled contacts, status:")

            for contact in self.DDB.getContacts():
                if contact[1] in ['ON', 'TEL', 'MAIL']:
                    print(("  %s, %s" % (str(contact[0]), str(contact[1]))))

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
                print(("\n--Testrun:\n  Active for the first %s minutes." %
                      str(self.opts.testrun)))
            print((60 * '-'))
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
        runner = 1
        try:
            self.observationThread.start()
            # Loop for working until stopped.
            while True:
                runner += 1
                self.logger.info("Main program still alive...")
                if runner % 2 == 0:
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
                    getattr(plugin, "__exit__")()
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
        self.logger = opts.logger
        self.queue = opts.queue
        self._config = _config
        self._running_controllers = _running_controllers

        self.__startTime = datetime.datetime.now()
        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()
        self.waitingTime = 5
        self.DDB = DobermanDB.DobermanDB(opts, logger)
        self.alarmDistr = alarmDistribution.alarmDistribution(opts)
        self.logFile_writer = logFileWriter(logger)
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
                elif len(job) in [2, 3]:
                    while len(job) < 4:
                        job.append('')
                self.logger.info("Processing data from '%s': %s" %
                                 (str(job[0]), str(job[1:])))
                self.processData(job[0], job[1], job[2], job[3])
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

    def processData(self, name, logtime, data=0, status=-2):
        """
        Checks the data format and then passes it to the database and
        the data check.
        """
        if status in ['', None]:
            status = [-2]
        data, status, logtime = self.checkDataFormat(
            name, data, status, logtime)
        self.writeData(name, logtime, data, status)
        self.checkData(name, logtime, data, status)

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

    def writeData(self, name, logtime, data=0, status=-2):
        """
        Writes data to a database/file
        Status:
         0 = OK,
         -1 = no connection,
          -2 = No error status available,
          1-9 = warning
          > 9 = alarm
        """
        if self.DDB.writeDataToDatabase(name, logtime, data, status) == -1:
            self.logger.debug("Reading data for log...")
            readout = str("| %s | %s | %s | %s |" % (
                logtime.strftime('%Y-%m-%d | %H:%M:%S'), name, data, status))
            self.logFile_writer.write(readout)

    def checkData(self, name, logtime, data, status):
        """
        Checks if all data is within limits, and start warning if necessary.
        """
        device = [dev for dev in self._config if name == dev[0]]
        if len(device) != 1:
            self.logger.error("No or several controller with name '%s' found. "
                              "Can not check data." % name)
            return -1
        device = device[0]
        alarm_status = device[2]
        lowerwarning = device[3]
        higherwarning = device[4]
        loweralarm = device[5]
        higheralarm = device[6]
        description = device[9]
        # Check if the right amount of data arrived as given in the config.
        if len(alarm_status) > len(data):
            self.logger.warning("Received less data then expected for '%s'. "
                                "Check data and continue..." % name)
        elif len(alarm_status) < len(data):
            text = ("Receved more data than expected for '%s' "
                    "(description: %s, logtime: %s), can not check all data "
                    "for alarm limits!" % (name, description, logtime))
            self.logger.warning(text + " Raising warning and continue...")
            index='All'
            n_o_r = self.sendWarning(name, text, index)
            self.DDB.addAlarmToHistory(name, index, logtime, data,
                                       status,
                                       reason="DL",
                                       alarm_type="W",
                                       number_of_recipients=n_o_r)
        if len(status) < len(data):
            self.logger.warning("Less status entries than data entries. "
                                "Appending -2 (no status) until correct.")
            while len(status) < len(data):
                status.append(-2)
        elif len(status) > len(data):
            self.logger.warning("More status entries than data entries. "
                                "Ignoring the rest.")
        # Actual status and data check.
        try:
            for ii, al_status in enumerate(alarm_status):
                status_tested_positive = False
                if al_status != 'ON':
                    self.logger.debug("Data from '%s[%d]' not checked as "
                                      "alarm status is %s." %
                                      (name, ii, al_status))
                    continue
                data_string = "%.2f" % data[ii]
                # Check the status
                if status[ii] in [0, -2]:  # Status OK (0) or 'No status' (-2)
                    self.logger.info("Status[%d] from '%s' ok." % (ii, name))
                    status_tested_positive = True
                elif status[ii] in range(1, 10):  # Warning status (1-9)
                    self.logger.warning("Status[%d] from '%s' not ok (status "
                                        "= %d, data = %s, description = %s). "
                                        "Sending warning..." %
                                        (ii, name, status[ii],
                                         data_string, description[ii]))
                    text = ("'%s[%d]' got a warning: Status '%d' "
                            "(Data: %s, Description: %s)" %
                            (name, ii, status[ii],
                             data_string, description[ii]))
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendWarning(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason=str(status[ii]),
                                                   alarm_type="W",
                                                   number_of_recipients=n_o_r)
                elif status[ii] == -1:  # No connection status (-1)
                    text = "No connection to '%s' (%s)" % (name, logtime)
                    self.logger.warning(text)
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendWarning(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason="-1",
                                                   alarm_type="W",
                                                   number_of_recipients=n_o_r)
                else:  # Alarm status (all the other)
                    self.logger.warning("Status from '%s[%d]' not ok (status "
                                        "= %d, data = %s, description = %s). "
                                        "Sending alarm..." %
                                        (name, ii, status[ii],
                                         data_string, description[ii]))
                    text = ("'%s[%d]' got an error: Status '%d' (Data: %s, "
                            "Description: %s)" % (name, ii, status[ii],
                                                  data_string,
                                                  description[ii]))
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendAlarm(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason=str(status[ii]),
                                                   alarm_type="A",
                                                   number_of_recipients=n_o_r)
                # Check the data
                if data[ii] > higheralarm[ii]:
                    text = ("Data from '%s[%d]' above upper ALARM level "
                            "(Data: %s, Upper alarm: %s, Description: %s)." %
                            (name, ii, data_string, str(higheralarm[ii]),
                             description[ii]))
                    self.logger.error(text + " Raising alarm...")
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendAlarm(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason="AH",
                                                   alarm_type="A",
                                                   number_of_recipients=n_o_r)
                elif data[ii] < loweralarm[ii]:
                    text = ("Data from '%s[%d]' below lower ALARM level "
                            "(Data: %s, Lower alarm: %s, Description: %s)." %
                            (name, ii, data_string, str(loweralarm[ii]),
                             description[ii]))
                    self.logger.error(text + " Raising alarm...")
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendAlarm(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason="AL",
                                                   alarm_type="A",
                                                   number_of_recipients=n_o_r)
                elif data[ii] > higherwarning[ii]:
                    text = ("Data from '%s[%d]' above upper WARNING level "
                            "(Data: %s, Upper warning: %s, Description: %s)." %
                            (name, ii, data_string, str(higherwarning[ii]),
                             description[ii]))
                    self.logger.warning(text + " Raising warning...")
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendWarning(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii,
                                                   logtime, data, status,
                                                   reason="WH",
                                                   alarm_type="W",
                                                   number_of_recipients=n_o_r)
                elif data[ii] < lowerwarning[ii]:
                    text = ("Data from '%s[%d]' below lower WARNING level "
                            "(Data: %s, Lower warning: %s, Description: %s)." %
                            (name, ii, data_string, str(lowerwarning[ii]),
                             description[ii]))
                    self.logger.warning(text + " Raising warning...")
                    if self.editRecurrenceCounter(name, index=ii) == 1:
                        n_o_r = self.sendWarning(name, text, index=ii)
                        self.DDB.addAlarmToHistory(name, ii, logtime, data,
                                                   status,
                                                   reason="WL",
                                                   alarm_type="W",
                                                   number_of_recipients=n_o_r)
                else:
                    self.logger.info("Data from '%s[%d]' ok." % (name, ii))
                    if status_tested_positive:
                        self.editRecurrenceCounter(name, index=ii, backwards=True)
        except Exception as e:
            self.logger.critical("Can not check data values and status! "
                                 "Device: %s. Error: %s" % (name, e))

    def checkDataFormat(self, name, data, status, logtime):
        """
        Checks if the data and status have the right format
        Data: Float or int
        Status: Int
        Logtime: datetime.datetime
        """
        # Checking logtime format.
        try:
            logtime = str(logtime.strftime('%Y-%m-%d | %H:%M:%S'))
        except:
            self.logger.warning("Logtime of %s has a worg format. "
                                "Replaced by current time." % name)
            logtime = str(datetime.datetime.now().strftime(
                '%Y-%m-%d | %H:%M:%S'))
        # Check that data is an array
        if not isinstance(data, list):
            data = self.makeTypeList(data)
            if data == -1:
                self.logger.error("Wrong data format from device '%s'! "
                                  "Data can not be analyzed and is replaced "
                                  "by [0] and status [9] (warning). "
                                  "Check your Plugins data transfer." % name)
                return [0], [9], logtime
        # Check that status is an array
        if not isinstance(status, list):
            status = self.makeTypeList(status)
            if status == -1:
                self.logger.error("Wrong status format from device '%s'. "
                                  "Statuses are replaced by 9 (warning)! "
                                  "Check your Plugins status transfer." % name)
                status = [9 for i in len(data)]
                self.logger.info("Replaced statuses from '%s' to %s" % (
                                 name, str(status)))
        # Check that data entries are floats/ints
        data_length = len(data)
        if not all(isinstance(entry, (float, int)) for entry in data):
            for ii, d in enumerate(data):
                try:
                    data[ii] = float(d)
                except Exception as e:
                    self.logger.error("Data from '%s[%d]' has a wrong "
                                      "format (Must be type int or float and "
                                      "can not be changed to type float. "
                                      "Error: %s. "
                                      "Replaced by 0, status 9 (warning). "
                                      "Check your Plugins data transfer! "
                                      % (name, ii, e))
                    data[ii] = 0
                    status[ii] = 9
        # Check that status entries are ints
        if not all(isinstance(entry, int) for entry in status):
            for ii, stat in enumerate(status):
                try:
                    status[ii] = int(stat)
                except Exception as e:
                    self.logger.error("Status[%d] from '%s' has a wrong format "
                                      "(Must be type int) and can "
                                      "not be changed to it. "
                                      "Error: %s. Check your Plugins status "
                                      "transfer. Changing status to 9 "
                                      "(warning)!" % (ii, name, e))
                    status[ii] = 9
        return data, status, logtime

    def makeTypeList(self, data):
        """
        Returns the data as type list
        """
        try:
            if not isinstance(data, list):
                if isinstance(data, tuple):
                    data = list(data)
                else:
                    data = [data]
        except Exception as e:
            self.logger.warning("Data is not of type list and can not be "
                                "changed to this type. Error: %s. "
                                "Data: %s.") % (e, str(data))
            return -1
        return data

    def checkTimeDifferences(self):
        """
        Checks time between latest two measurements and between the
        last and the expected next one.
        """
        self.logger.debug("Checking time differences for all controllers.")
        for controller in self._running_controllers:
            device = [dev for dev in self._config if dev[0] == controller]
            if len(device) != 1:
                self.logger.warning("Error in loading the correct config. "
                                    "Can not check time differences for "
                                    "'%s'." % controller)
                continue
            device = device[0]  # undo double list [[name, status, ...]]
            alarm_status = device[2]
            readout_interval = device[7]
            now = datetime.datetime.now()
            # Compare if program was running longer long enough to get two
            # data point. *1.5 to make sure.
            if (now - self.__startTime).total_seconds() < readout_interval * 1.5:
                self.logger.debug("'%s' has not been running long enough "
                                  "to get data." % controller)
                continue
            # Reading logtime of the last two points from the database.
            self.logger.debug("Checking times for '%s'..." % controller)
            latestData = self.DDB.getData(controller, limit=2)
            if latestData == -1:
                self.logger.error("Can not copmare data. "
                                  "Could not get the two latest data entries.")
                continue
            try:  # Testing if latest Data is accessable
                a = latestData[0][0]
            except IndexError:
                self.logger.warning("Can not copmare data. Latest data not "
                                    "loaded. Probabely no data stored.")
                continue
            # Defining tolerances in time checking.
            ttolerance0, ttolerance1 = 0, 0
            if readout_interval < 5:
                ttolerance0 = 4
                ttolerance1 = 2.5
            elif readout_interval >= 5 and readout_interval <= 20:
                ttolerance0 = 10
                ttolerance1 = 4
            else:
                ttolerance0 = 20
                ttolerance1 = 10
            # Check if time since last measurements is not bigger than expected
            # (+ttolerance for savety, e.g. if queue is too slow)
            timediff = (now - latestData[0][0]).total_seconds()
            if timediff > (readout_interval + ttolerance0):
                text = ("Time inteval since latest measurements for '%s' "
                        "too big: diff = %.1f s, requested interval = %s s." %
                        (controller, float(timediff), str(readout_interval)))
                self.logger.error(text)
                if self.editRecurrenceCounter(controller) == 1:
                    if any(al_status == 'ON' for al_status in alarm_status):
                        n_o_r = self.sendAlarm(controller, text, index='All')
                        self.DDB.addAlarmToHistory(name=controller,
                                                   index='All',
                                                   logtime=now,
                                                   data=latestData[0][1],
                                                   status=latestData[0][2],
                                                   reason="TD",
                                                   alarm_type="A",
                                                   number_of_recipients=n_o_r)
                    else:
                        self.logger.warning("No alarm is sent as none of the "
                                            "alarm statuses is 'ON' for '%s'." %
                                            controller)
                continue
            # Check if time difference between latest two measurements is not
            # bigger than expected (+ttolreance, e.g. slow serial connection)
            timediff = (latestData[0][0] -
                        latestData[1][0]).total_seconds()
            if timediff > (readout_interval + ttolerance1):
                text = ("Time interval between two measurements for '%s' "
                        "too big: diff = %.1f s, requested interval = %s s." %
                        (controller, float(timediff), str(readout_interval)))
                self.logger.warning(text)
                if self.editRecurrenceCounter(controller) == 1:
                    if any(al_status == 'ON' for al_status in alarm_status):
                        n_o_r = self.sendWarning(controller, text, index='All')
                        self.DDB.addAlarmToHistory(name=controller,
                                                   index='All',
                                                   logtime=now,
                                                   data=latestData[0][1],
                                                   status=latestData[0][2],
                                                   reason="TD",
                                                   alarm_type="W",
                                                   number_of_recipients=n_o_r)
                    else:
                        self.logger.warning("No alarm is sent as none of the "
                                            "alarm statuses is 'ON' for '%s'." %
                                            controller)
            else:
                self.logger.debug(
                    "Time differences for '%s' ok." % controller)

    def sendAlarm(self, name, message, index=None):
        """
        Sends a alarm to the address(es) from the database.
        This will send an SMS for the contact with status "ON" or "TEL"
        or a Email with status "MAIL" or if the SMS sending failed.
        """
        now = datetime.datetime.now()
        # Check if the testrun is still active
        if self.opts.testrun == -1:
            self.logger.warning(
                "Testrun: No alarm sent. Alarm message: %s" % message)
            return [-1, -1]
        runtime = (now - self.__startTime).total_seconds() / 60.
        if runtime < self.opts.testrun:
            self.logger.warning("Testrun still active (%.1f/%s minutes). "
                                "No alarm sent. Alarm message: %s" %
                                (runtime, str(self.opts.testrun), message))
            return [-1, -1]
        # Check if already an ALARM was out for this device
        if not self.repetitionAllowed(name, now, self.sentAlarms,
                                      self.opts.alarm_repetition):
            self.logger.warning("An alarm for '%s' was already sent. "
                                "Alarm message: %s" % (name, message))
            return [-2, -2]
        # Gets enabled alarm contacts
        sms_recipients = [contact[3] for contact in self.DDB.getContacts()
                          if contact[1] in ['ON', 'TEL']]
        mail_recipients = [contact[2] for contact in self.DDB.getContacts()
                           if contact[1] in ['ON', 'MAIL']]
        sms_sent = False
        mail_sent = False
        if sms_recipients:
            if self.alarmDistr.sendSMS(sms_recipients, message) == -1:
                self.logger.error("SMS sending not successful. Trying mail...")
                additional_mail_recipients = [contact[2] for contact
                                              in self.DDB.getContacts()
                                              if contact[3] in sms_recipients
                                              if len(contact[2]) > 5
                                              if contact[2] not in mail_recipients]
                mail_recipients = mail_recipients + additional_mail_recipients
                sms_recipients = []
                if not mail_recipients:
                    self.logger.error("Can not send alarm to email, "
                                      "no contacts.")
            else:
                self.logger.info("Sent SMS with alarm to %s" %
                                 str(sms_recipients))
                sms_sent = True
        if mail_recipients:
            subject = "ALARM: '%s'" % name
            message = message + self.getAdditionalInfos(name, index)
            if self.alarmDistr.sendEmail(toaddr=mail_recipients, subject=subject, message=message) == -1:
                self.logger.error("Could not send alarm: %s" % message)
                mail_recipients = []
            else:
                self.logger.info("Successfully sent email with alarm to %s" %
                                 str(mail_recipients))
                mail_sent = True
        if any([mail_sent, sms_sent]):
            now = datetime.datetime.now()
            self.sentAlarms = self.updateSentList(self.sentAlarms, name, now)
        else:
            self.logger.critical("Unable to send alarm! "
                                 "Alarm message %s." % message)
        return [len(sms_recipients), len(mail_recipients)]

    def sendWarning(self, name, message, subject=None, toaddr=None, index=None):
        """
        Sends a warning to the adress(es) from the database
        or to the 'toaddr' if given.
        """
        now = datetime.datetime.now()
        # Check if the testrun is still active
        if self.opts.testrun == -1:
            self.logger.warning(
                "Testrun: No warning sent. Warning message: %s" % message)
            return [-1, -1]
        runtime = (now - self.__startTime).total_seconds() / 60.
        if runtime < self.opts.testrun:
            self.logger.warning("Testrun still active (%.1f/%s minutes). "
                                "No alarm warning. Waring message: %s" %
                                (float(runtime), str(self.opts.testrun), message))
            return [-1, -1]
        # Check if already an ALARM was out for this device
        if not self.repetitionAllowed(name, now, self.sentAlarms,
                                      self.opts.warning_repetition):
            self.logger.warning("An alarm for '%s' was already sent. "
                                "Warning message: %s" % (name, message))
            return [-2, -2]
        # Check if already a WARNING was out for this device
        elif not self.repetitionAllowed(name, now, self.sentWarnings,
                                        self.opts.warning_repetition):
            self.logger.warning("A warning for '%s' was already sent. "
                                "Warning message: %s" % (name, message))
            return [-2, -2]
        # Create autosubject if not given
        if not subject:
            subject = 'Warning: "%s"' % name
        # Getting contact addresses from the database if not given
        if not toaddr:
            # Choose contacts with status on or mail.
            recipients = [contact[2] for contact in self.DDB.getContacts()
                          if contact[1] in ['ON', 'MAIL']]
        else:
            recipients = toaddr
        if recipients:
            message = message + self.getAdditionalInfos(name, index)
            if self.alarmDistr.sendEmail(toaddr=recipients,
                                         subject=subject,
                                         message=message) != -1:
                self.sentWarnings = self.updateSentList(self.sentWarnings,
                                                        name, now)
            else:
                self.logger.critical("Sending of warning failed.")
                return [0, 0]
            return [0, len(recipients)]

    def getAdditionalInfos(self, name, index=None):
        """
        Reads for a device if aviable:
        - Latest 10 Data entries
        - Alarm/Warning Levels
        - Readout interval
        """
        # General parameters
        add_infos = ("\n\n\n----------\n"
                     "General Doberman slow control settings:\n"
                     " - Minimum time between to messages:\n"
                     "     - Warnings: %s min.\n"
                     "     - Alarms:   %s min."
                     % (str(self.opts.warning_repetition),
                        str(self.opts.alarm_repetition)))
        # Doberman has no Data stored, so return.
        if name == "Doberman":
            return add_infos
        # Important config parameters
        add_infos += ("\n\n----------")
        if not isinstance(index, int):
            index = 'All'
        if index != 'All':
            try:
                config = [dev[index] for dev in self._config if dev[0] == name]
            except Exception as e:
                index = 'All'
                self.logger.warning("Can not get settings (config) of '%s[%s]'. "
                                    "Error: %s. Trying to read all config from"
                                    " this device..." % (name, str(index, e)))
        try:
            if index == 'All':
                config = [dev for dev in self._config if dev[0] == name]
            config = [dev for dev in self._config if dev[0] == name]
            if config:
                config = config[0]
                if index != 'All':
                    add_infos += ("\nSettings for '%s[%s]':\n"
                                  " - Warning Low:   %9.4f\n"
                                  " - Warning High:  %9.4f\n"
                                  " - Alarm Low:     %9.4f\n"
                                  " - Alarm High:    %9.4f\n"
                                  " - Recurrence param.: %2d\n"
                                  " - Readout Interval: %d s\n"
                                  " - Additional param.: %s"
                                  % (name, str(index),
                                     config[3][index], config[4][index],
                                     config[5][index], config[6][index],
                                     config[8][index], config[7],
                                     str(config[12])))
                else:
                    add_infos += ("\nSettings for '%s[%s]':\n"
                                  " - Warning Low:   %s\n"
                                  " - Warning High:  %s\n"
                                  " - Alarm Low:     %s\n"
                                  " - Alarm High:    %s\n"
                                  " - Recurrence param.: %s\n"
                                  " - Readout Interval: %d s\n"
                                  " - Additional param.: %s"
                                  % (name, str(index),
                                     str(config[3]), str(config[4]),
                                     str(config[5]), str(config[6]),
                                     str(config[8]), config[7],
                                     str(config[12])))
        except Exception as e:
            self.logger.warning("Can not get additional Infos for '%s[%s]'. "
                                "Error %s." % (name, str(index), e))
        try:
            # Latest Data
            latest_data = self.DDB.getData(name, limit=10, datetimestamp=None)
            if latest_data != -1:
                add_infos += ("\n\n----------\n"
                              "Data evolution of the last 10 measurements "
                              "for '%s[%s]'." % (name, str(index)))
                for jj in range(len(latest_data[0][1])):
                    if index == "All":
                        add_infos += "\n\n   ---- Channel %d ----  " % jj
                    else:
                        if index != jj:
                            continue
                    add_infos += "\n   Value  (Status) | Datetime"
                    for ii, ldata in enumerate(latest_data):
                        add_infos += "\n  %9.4f   (%2d) |   %s" % (
                            ldata[1][jj], ldata[2][jj],
                            str(ldata[0].strftime('%Y-%m-%d %H-%M-%S')))
        except Exception as e:
            self.logger.warning("Can not get latest data for '%s[%s]'. "
                                "Error %s." % (name, str(index), e))
        try:
            # Latest Alarms
            latest_alarms = self.DDB.getLatestAlarms(name=name, limit=20)
            if latest_alarms and latest_alarms != -1:
                explanation = [["TD", "Time diff."], ["AH", "Alarm high"],
                               ["AL", "Alarm low"], ["WH", "Warning high"],
                               ["WL", "Warning low"], ["W", "Warning"],
                               ["A", "Alarm"], ["S", "Silent"],
                               ["-1", "No connection"]]
                if index == 'All':
                    add_infos += ("\n\n----------\n"
                                  "Latest alarms for '%s':" % name)
                else:
                    add_infos += ("\n\n----------\n"
                                  "Latest alarms for '%s[%s]' "
                                  "(incl. some important alarms from other "
                                  "channels):" % (name, str(index)))
                add_infos += ("\n Channel |      Datetime        |"
                              "  Data  (Status)  "
                              "|    Reason    |   Type    | "
                              "Number of recipients [SMS, Mail]")
                for ii, lalarm in enumerate(latest_alarms):
                    if lalarm[0] < self.__startTime or lalarm[8] == "Y":
                        if ii == 0:
                            add_infos += "\n   None"
                        break
                    if lalarm[2].rstrip() not in ["All", str(index)]:
                        if lalarm[5] not in ["TD", "-1"]:
                            continue
                    reason = [expl[1] for expl in explanation if expl[0] == lalarm[5]]
                    if not reason:
                        reason = "Status %2d" % int(lalarm[4])
                    else:
                        reason = reason[0]
                    time_str = str(lalarm[0].strftime('%Y-%m-%d %H-%M-%S'))
                    al_type = [expl[1] for expl in explanation if expl[0] == lalarm[6]][0]
                    add_infos += ("\n    %s  |  %s  | %8.4f   (%s)    |  %s  |   %s   "
                                  "|       %s  " % (lalarm[2], time_str,
                                                  lalarm[3], str(lalarm[4]),
                                                  reason, al_type,
                                                  str(lalarm[7])))
            else:
                self.logger.warning("Can not get latest alarms for '%s[%s]'. "
                                    "Reading Error." % (name, str(index)))
        except Exception as e:
            self.logger.warning("Can not get latest alarms for '%s[%s]'. "
                                "Error %s." % (name, str(index), e))
        return add_infos

    def repetitionAllowed(self, name, time, array, repetition_time):
        """
        Function designed for sentWarnings and sentAlarms check
        Returns False if the name is not in the array or the
        time between the time in the array and given time is bigger than
        the repetition_time.
        Otherwise returns True
        """
        array_names = [item[0] for item in array]
        if name not in array_names:
            return True
        latest_entry = max([item[1] for item in array if item[0] == name])
        if (time - latest_entry).total_seconds()/60. > repetition_time:
            self.logger.debug("Repetition allowed because time since last "
                              "entry bigger than repetition time. (%.2f > %s)" %
                              ((time - latest_entry).total_seconds()/60.,
                               str(repetition_time)))
            return True
        else:
            self.logger.info("Repetition not allowed because time since last "
                             "entry is smaller than repetition time. (%.2f < %s)" %
                             ((time - latest_entry).total_seconds()/60.,
                              str(repetition_time)))
            return False

    def updateSentList(self, array, name, time):
        """
        Updates the sentWanring and sentAlarm list properly.
        Removes old entries. Append latest one. Returns the new array
        """
        array = [item for item in array if item[0] != name]
        array.append([name, time])
        return array

    def initializeRecurrenceCounter(self):
        """
        Initializing recurrence counter (self.reccurence_counter) by
        setting [[name, limits, conuter], ... ]
        where limits = [limit0, limit1, ...] are read from config
        and counter = [conunter1, counter2,..] are all set to 0
        """
        try:
            recurrence = []
            for controller in self._running_controllers:
                number_of_data = [dev[10] for dev in self._config if dev[0] == controller][0]
                limits = [dev[8] for dev in self._config if dev[0] == controller][0]
                counter = [0]*number_of_data
                recurrence.append([controller, counter, limits])
            return recurrence
        except Exception as e:
            self.logger.error("Could not initialize recurrence counter properly! "
                              "Will continue without recurrence counting!...")
            return []

    def editRecurrenceCounter(self, name, index=False, backwards=False):
        """
        Adds one to the recurrence counter of name[index]
          (to all if index=None)
        And if above limit sets back to 0 and returns 1, otherways returns 0
        If backwards it reduces the index (all if index=False) by 1
          (as long as >0)
        """
        all_names = [item[0] for item in self.recurrence_counter]
        name_index = all_names.index(name)
        limits = self.recurrence_counter[name_index][2]
        values = self.recurrence_counter[name_index][1]
        limit_exceeded = False
        # Backwards
        if backwards:
            for ii, value in enumerate(values):
                if value > 0 and (not index or ii == index):
                    self.recurrence_counter[name_index][1][ii] -= 1
            return 0
        # Adding and check limits
        if index is False:  # For all
            for ii, value in enumerate(values):
                if value + 1 >= limits[ii]:
                    limit_exceeded = True
                    break
                else:
                    self.recurrence_counter[name_index][1][ii] += 1
            if limit_exceeded:
                self.logger.debug("Recurrence counter from '%s[%d]' above "
                                  "recurrence limit. Setting back counters and"
                                  " continuing with alarm/warning..." %
                                  (name, ii))
                for ii, value in enumerate(values):
                    self.recurrence_counter[name_index][1][ii] = 0
                return 1
            else:
                self.logger.warning("Recurrence counters from '%s' all below "
                                    "recurrence limit. No alarm/warning "
                                    "will be sent." % name)
                return 0
        else:  # Only for 1 index
            if values[index] + 1 >= limits[index]:
                self.recurrence_counter[name_index][1][index] = 0
                self.logger.debug("Recurrence counter from '%s[%d]' above "
                                  "recurrence limit. Setting back counter and"
                                  " continuing with alarm/warning..." %
                                  (name, index))
                return 1
            else:
                self.recurrence_counter[name_index][1][index] += 1
                self.logger.warning("Recurrence counter from '%s[%d]' below "
                                    "recurrence limit (%d<%d). No "
                                    "alarm/warning will be sent." %
                                    (name, index, values[index],
                                     limits[index]))
                return 0


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


class logFileWriter(object):
    """
    Class that holds the logFile logging and debugging.
    This is only used, if there is no connection to the database.
    Creates a new file with the name:
        %Y-%m-%d_%H-%M-%S_%Keyword.log in the folder that was set.
    If the file already exists it tries to write the informations
        in the existing file.
    """

    def __init__(self, logger, keyword=None, **kwds):
        self.logger = logger

        self._logpath = 'log'
        self.__keyword = keyword
        if self.__keyword is None:
            self.__keyword = 'Doberman'

        if not os.path.isdir(self._logpath):
            rights = 0o751
            # PYTHON 2 compatibility:
            # rights = 0751
            os.mkdir(self._logpath, rights)

        self.now = datetime.datetime.now()
        self.filename = os.path.join(self._logpath, "%s_%s.log" % (
            self.now.strftime('%Y-%m-%d_%H-%M-%S'), self.__keyword))

        ifn = 0
        while ifn < 10:
            ifn += 1
            if os.path.isfile(self.filename):
                newname = os.path.join(self._logpath, "%s_%s_%i.log" %
                                       (self.now.strftime('%Y-%m-%d_%H-%M-%S'),
                                        self.__keyword, ifn))
                self.logger.warning("File: %s exists already. "
                                    "Trying to write to %s..." %
                                    (self.filename, newname))
                self.filename = newname
            else:
                break
        self.__file = open(self.filename, 'w')
        self.__file_queue = []

        self.write(("# Doberman: Slow control logging file - generated %s. "
                    "Logging mode is %s" %
                    (self.now.strftime('%Y-%m-%d %H:%M:%S'), self.__keyword)))

    def write(self, message=None):
        """
        Writes a message to the file
        """
        towrite = []
        if len(self.__file_queue) != 0:
            towrite = self.__file_queue
        if message is not None:
            if not isinstance(message, str):
                self.logger.warning("Invalid format for the logging file.")
                return -1
            else:
                towrite = towrite + [message]
        for elem in towrite:
            self.__file.write(elem.rstrip() + '\n')
        self.__file.flush()
        return 0

    def close(self):
        """
        Call this to properly close the file of the writer.
        """
        if not self.__file.closed:
            self.__file.flush()
            self.__file.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')
    # READING DEFAULT VALUES (need a logger to do so)
    logger = logger = logging.getLogger()
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
    parser.add_argument("-ar", "--alarm_repetition_time",
                        dest="alarm_repetition",
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
        print(("ERROR: Given log level %i not allowed. "
              "Fall back to default value of " % loglevel_default))
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
        print(("\nError while user input! Check if your input changed anything."
              " Error: %s", e))
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
    # Testrun option -t
    if opts.testrun == -1:
        print("WARNING: Testrun activated: No alarm / warnings will be sent.")
    elif opts.testrun == testrun_default:
        print(("WARNING: Testrun=%d (minutes) activated by default: "
              "No alarms/warnings will be sent for the first %d minutes." %
              (testrun_default, testrun_default)))
    else:
        print(("Testrun=%s (minutes) activated: "
              "No alarms/warnings will be sent for the first %s minutes." %
              (str(opts.testrun), str(opts.testrun))))
    # Import timeout option -i
    if opts.importtimeout < 1:
        print(("ERROR: Importtimeout to small. "
              "Fall back to default value of %d s" % import_default))
        opts.importtimeout = import_default
    # Occupied ttyUSB option -o
    with open("ttyUSB_assignement.txt", "w") as f:
        # Note that this automatically overwrites the old file.
        f.write("# ttyUSB | Device\n")
        for occupied_tty in opts.occupied_ttyUSB:
            f.write("    %d    |'Predefined unknown device'\n" % occupied_tty)
    # Filereading option -f
    if opts.filereading:
        print(("WARNING: opt -f enabled: Reading Plugin Config from file"
              " '%s' and storing new settings to database... "
              "Possible changes in the database will be overwritten...!" %
              opts.filereading))
        try:
            DDB.storeSettingsFromFile(opts.filereading)
        except Exception as e:
            print(("ERROR: Reading plugin settings from file failed! "
                  "Error: %s. Check the settings in the database for any "
                  "unwanted or missed changes." % e))
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
