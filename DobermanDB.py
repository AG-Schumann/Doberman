#!/usr/bin/env python3
import time
import logging
from argparse import ArgumentParser
import _thread
import psycopg2
import datetime
import time
from ast import literal_eval
import alarmDistribution  # for test mail sending when address was changed


class DobermanDB(object):

    def __init__(self, opts, logger):
        self.logger = logger
        self.opts = opts
        self.opts.logger = logger
        self.alarmDistr = alarmDistribution.alarmDistribution(self.opts)
        # Load database connection details
        try:
            f = open('Database_connectiondetails.txt', 'r')
            self._conn_string = f.read()
            f.close()
        except Exception as e:
            self.logger.warning("Can not load database connection details. "
                                "Trying default details. Error %s" % e)
            self._conn_string = ("host='localhost' dbname='Doberman' "
                                 "user='postgres' password='Doberman' "
                                 "options='-c statement_timeout=10000'")
        # load config details
        self._config = self.getConfig()

    def interactWithDatabase(self, action, additional_actions=[], readoutput=False):
        """
        Interacts with the database.
        Creates connection, executes at least one action
        and finally commits and closes connection.

        The action will be used with cur.execute(action).
        Returns 0 if ok, otherwise -1

        If readoutput = True it tries to read the curser (cur.fetchall)
        after all interactions an returns the values
        """
        output = ''
        if not isinstance(action, str):
            self.logger.debug("Can not interact with database. "
                              "Use an action with type string.")
            return -1
        try:
            # Connect and get a cursor
            conn = psycopg2.connect(self._conn_string)#, cursor_factory=psycopg2.extras.DictCursor)
            cur = conn.cursor()
            #self.logger.debug("Connected with Doberman database.")

            # Do the job
            cur.execute(action)

            # Do additionals actions/reads
            if additional_actions:
                for additional_action in additional_actions:
                    cur.execute(additional_action)
            if readoutput:
                output = cur.fetchall()
                #self.logger.debug("Read output from Database...")

            # Closing the connection correctly
            conn.commit()
            cur.close()
            conn.close()
        except psycopg2.DatabaseError as e:
            self.logger.warning("Can not interact with database "
                                "(action = %s, %s). Error: %s" %
                                (action, str(additional_actions), e))
            try:
                conn.rollback()  # The rollback prevents future complications.
            except Exception:
                pass
            return -1
        #self.logger.debug("Closed connection with Doberman database.")
        if readoutput:
            return output
        return 0

    def refreshConfigBackup(self):
        """
        Writes the current config from the Database to the file configBackup.txt
        """
        try:
            with open('configBackup.txt', 'w') as f:
                f.write("# Backup file of the config table in DobermanDB. "
                        "Updated: %s" % str(datetime.datetime.now()))
                self.logger.info("Writing new config to configBackup.txt...")
                for name in (self._config):
                    controller = self._config[name]
                    f.write("\ncontroller:%s\n" % controller['controller']) # needs to be first entry
                    for key in controller:
                        if key == "controller":
                            continue
                        f.write("%s:%s\n" % (key, controller[key]))
                    f.write(20 * "-")
        except Exception as e:
            self.logger.warning("Can not refresh configBackup.txt. %s." % e)
            return -1
        return 0

    def getConfigFromBackup(self, filename='configBackup.txt'):
        """
        Reads the config from the file configBackup.txt.
        Only use this if no connection to the database exists.
        """
        try:
            with open(filename, 'r') as f:
                self.logger.info("Reading config from configBackup.txt...")
                configBackup = f.read().splitlines()
        except Exception as e:
            self.logger.warning("Can not read from configBackup.txt. %s" % e)
            return -2
        if not configBackup:
            self.logger.warning("Can not read config from configBackup.txt. "
                                "File empty")
            return -2
        self.logger.info("Backup file dates from %s" %
                (configBackup[0].split(': ')[1]))
        # The following lines convert the text from the file back into
        # the backend dictionaries
        c_backup = {}
        index_string = '-' * 20
        num_entries = configBackup.count(index_string)
        entry_start, entry_end = 1, configBackup.index(index_string)
        for _ in range(num_entries):
            entry = configBackup[entry_start:entry_end]
            name = entry[0].split(':')[1]
            c_backup[name] = {}
            for row in entry:
                key, val = row.split(':')
                try:
                    c_backup[name][key] = eval(val)
                except NameError:
                    c_backup[name][key] = val
            entry_start = entry_end+1
            if entry_start == len(configBackup):
                break
            entry_end = configBackup.index(index_string, entry_start)
        return c_backup

    def refreshContactsBackup(self):
        """
        Refreshes or creates the file contactsBackup.txt with the contacts
        stored in the database.
        """
        self.logger.info("Writing new contacts to contactsBackup.txt...")
        try:
            self._contacts = self.readContacts()
            if not self._contacts or self._contacts == -1:
                self.logger.warning("Could not load contacts. Can not "
                                    "write contactsBackup.txt.")
                return -1
            with open('contactsBackup.txt', 'w') as f:
                f.write("# Backup file of the contacts table in DobermanDB. "
                        "Updated: %s" % str(datetime.datetime.now()))
                for row in (self._contacts):
                    for item in row:
                        f.write("\n")
                        f.write(str(item))
                    f.write("\n" + 20 * "-")
        except Exception as e:
            self.logger.warning("Can not refresh 'contactsBackup.txt'. %s." % e)
            return -1
        self.logger.info("Successfully refreshed 'contactsBackup.txt'.")
        return 0

    def getContactsFromBackup(self, status=None):
        """
        Reads the contacts from the file contactsBackup.txt.
        Only use this if no connection to the database exists.
        """
        try:
            with open('contactsBackup.txt', 'r') as f:
                self.logger.info("Reading config from contactsBackup.txt...")
                contactsBackup = f.read().splitlines()
        except Exception as e:
            self.logger.warning("Can not read from contactsBackup.txt. %s" % e)
            return -1
        if not contactsBackup:
            self.logger.warning("Can not read config from configBackup.txt. "
                                "File empty")
            return -1
        self.logger.info("Backup file dates from %s" %
                         (contactsBackup[0].replace("# Backup file of the "
                                                  "contacts table in Doberman "
                                                  "database. Updated:", "")))
        # The following lines are converting the text from the file back in
        # arrays to get the same format as if it would come from the database
        templist = []
        temp = contactsBackup[1:]
        c_backup = []
        for item in temp:
            if item == (20 * "-"):
                if status is None or templis[1] == status:
                    c_backup.append([str(templist[0]), str(templist[1]),
                                     str(templist[2]), str(templist[3])])
                templist = []
                continue
            templist.append(item)
        return c_backup

    def recreateTableConfig(self):
        """
        Clears and recreates table config. Only use for support maintenance:
        Config rows:
        (CONTROLLER TEXT, STATUS TEXT, ALARM_STATUS TEXT,
         WARNING_LOW REAL[], WARNING_HIGH REAL[], ALARM_LOW REAL[],
         ALARM_HIGH REAL[]
         READOUT_INTERVAL INT, ALARM_RECURRENCE INT[], DESCRIPTION TEXT[],
         NUMBER_OF_DATA INT, ADDRESSES TEXT[], ADDITIONAL_PARAMETERS TEXT[])
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        text = ("Are you sure you want to clear and recreate table 'config'? "
                "All plugin settings will be lost. (y/n)?")
        drop_config = self.getUserInput(text,
                                        input_type=[str],
                                        be_in=[y, Y, n, N])
        if drop_config not in ['Y', 'y']:
            return
        drop_str = "DROP TABLE IF EXISTS config"
        create_str = ("CREATE TABLE config ("
                      "CONTROLLER TEXT, STATUS TEXT, "
                      "ALARM_STATUS TEXT[], WARNING_LOW REAL[], "
                      "WARNING_HIGH REAL[], ALARM_LOW REAL[], "
                      "ALARM_HIGH REAL[], "
                      "READOUT_INTERVAL INT, ALARM_RECURRENCE INT[], "
                      "DESCRIPTION TEXT[], NUMBER_OF_DATA INT, "
                      "ADDRESSES TEXT[], ADDITIONAL_PARAMETERS TEXT[], "
                      "_id SERIAL PRIMARY KEY)")
        if self.interactWithDatabase(drop_str, additional_actions=[create_str]) == -1:
            self.logger.warning("Can not recreate config table in database. "
                                "Error while interacting with DB.")
            return -1
        else:
            self.logger.warning("Recreated table config.")
            return 0

    def recreateTableConfigHistory(self):
        """
        Clears and reacreates table config_history. Only use for support maintenance:
        Config hirstory rows:
        (DATETIME TIMESTAMP, config)
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        text = ("Are you sure you want to clear and recreate table "
                "'config_history'? The plugin settings history will be lost. (Y/N)?")
        drop_history = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=[y, Y, n, N])
        if drop_history not in ['Y', 'y']:
            return
        drop_str = "DROP TABLE IF EXISTS config_history"
        create_str = ("CREATE TABLE config_history ("
                      "DATETIME TIMESTAMP, "
                      "CONTROLLER TEXT, STATUS TEXT, "
                      "ALARM_STATUS TEXT[], WARNING_LOW REAL[], "
                      "WARNING_HIGH REAL[], ALARM_LOW REAL[], "
                      "ALARM_HIGH REAL[], "
                      "READOUT_INTERVAL INT, ALARM_RECURRENCE INT[], "
                      "DESCRIPTION TEXT[], NUMBER_OF_DATA INT, "
                      "ADDRESSES TEXT[], ADDITIONAL_PARAMETERS TEXT[], "
                      "_id SERIAL PRIMARY KEY)")
        if self.interactWithDatabase(drop_str, additional_actions=[create_str]) == -1:
            self.logger.warning("Can not recreate config_history table in the "
                                " database. Error while interacting with DB.")
            return -1
        else:
            self.logger.warning("Recreated table config_history.")
            return 0

    def recreateTableAlarmHistory(self):
        """
        Clears and recreates table alarm_history. Only use for support maintenance:
        Config hirstory rows:
        (Data_controller[i]), REASON TEXT, TYPE CHAR(1),
        NUMBER_OF_RECIPIENTS INT[], ACKNOWLEDGEMENT  CHAR(1)
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        text = ("Are you sure you want to clear and recreate table 'alarm_history'? "
                "The alarm/warning history will be lost. (Y/N)?")
        drop_history = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=[y, Y, n, N])
        if drop_history not in ['Y', 'y']:
            return
        drop_str = "DROP TABLE IF EXISTS alarm_history"
        create_str = ("CREATE TABLE alarm_history ("
                      "DATETIME TIMESTAMP, "
                      "CONTROLLER TEXT, INDEX CHAR(3), DATA REAL, STATUS INT, REASON CHAR(2), "
                      "TYPE CHAR(1), NUMBER_OF_RECIPIENTS INT[], "
                      "ACKNOWLEDGEMENT CHAR(1), "
                      "_id SERIAL PRIMARY KEY)")
        if self.interactWithDatabase(drop_str, additional_actions=[create_str]) == -1:
            self.logger.warning("Can not recreate alarm_history table in the "
                                " database. Error while interacting with DB.")
            return -1
        else:
            self.logger.warning("Recreated table alarm_history.")
            return 0

    def addAlarmToHistory(self, name, index, logtime, data, status, reason, alarm_type, number_of_recipients, acknowledgement='N'):
        """
        Adds the alarm to the history.
        CONTROLLER = controller name
        REASON = [AL (=Alarm low), AH (=Alarm high),
                  WL (Warning Low), WH (=Warning High)
                  -1 (=No connection)], 1-9 (=Warning Status),
                  >9 (= Alarm Status)]
        ALARM TYPE = W/A (warning/alarm), S  (=silent, no outgoing alarm)
        NUMBER_OF_RECIPIENTS = [# sms_recipients, # mail_recipients]
        ACKNOWLEDGEMENT = Y/N (yes/no), - (= not possible)
        """
        if isinstance(data, (list, tuple)):
            data = data[0]
        if isinstance(status, (list, tuple)):
            status = status[0]
        if number_of_recipients == [-1, -1]:
            acknowledgement = '-'
            alarm_type = 'S'
            number_of_recipients = [0, 0]
        elif number_of_recipients == [-2, -2]:
            acknowledgement = '-'
            alarm_type = 'S'
            number_of_recipients = [0, 0]
        try:
            add_str = ("INSERT INTO alarm_history (DATETIME, CONTROLLER, INDEX, DATA,"
                       "STATUS, REASON, TYPE, NUMBER_OF_RECIPIENTS, "
                       "ACKNOWLEDGEMENT) VALUES ('%s'::timestamp, '%s', '%s', %f, "
                       "%d, '%s', '%s', ARRAY%s, '%s')" %
                       (str(logtime), name, str(index), float(data),
                        int(status), str(reason), alarm_type,
                        str(number_of_recipients),
                        acknowledgement))
            if self.interactWithDatabase(add_str) == -1:
                self.logger.warning("Can not add settings of %s to "
                                    "config_history. "
                                    "Database interaction error." % name)
                return -1
            self.logger.info("Added alarm from %s to alarm history." % name)
            return 0
        except Exception as e:
            self.logger.warning("Can not add controller %s alarm to "
                                "alarm history. Error %s" % (name, e))
            return -1

    def getLatestAlarms(self, name=None, limit=1):  # TODO expand
        """
        Reads the latest alarms,
        from the controller called name, or from all if name=None
        Number of alarm returned = limit
        """
        if not name:
            select_str = ("SELECT * FROM alarm_history ORDER BY DATETIME DESC "
                          "LIMIT %s;" % str(limit))
        else:
            select_str = ("SELECT * FROM alarm_history WHERE CONTROLLER = '%s' "
                          "ORDER BY DATETIME DESC LIMIT %s;" %
                          (name, str(limit)))
        latest_alarms = self.interactWithDatabase(select_str, readoutput=True)
        if latest_alarms == -1:
            self.logger.error("Failed to get the latest alarms.")
            return []
        return latest_alarms

    def deleteDataTable(self, name):
        """
        Deletes the Data_name table. Only use for maintenance.
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        text = ("Are you sure you want to delete the data table 'Data_%s'? "
                "This can not be reverted. (Y/N)?" % name)
        drop_table = self.getUserInput(text,
                                       input_type=[str],
                                       be_in=[y, Y, n, N])
        if drop_table not in ['Y', 'y']:
            return
        drop_str = "DROP TABLE IF EXISTS Data_%s" % name
        if self.interactWithDatabase(drop_str) == -1:
            self.logger.warning("Can not delete data table 'Data_%s' from "
                                "database. Error while interacting with DB" % name)
            return -1
        else:
            self.logger.warning("Deleted table 'Data_%s'" % str(name))
            return 0

    def addSettingToConfigHistory(self, controller):
        """
        Adds the current setting of a controller to the config history
        (DATETIME TIMESTAMP,
         CONTROLLER TEXT, STATUS TEXT[], ALARM_STATUS TEXT,
         WARNING_LOW REAL[], WARNING_HIGH REAL[], ALARM_LOW REAL[],
         ALARM_HIGH REAL[])
         READOUT_INTERVAL INT, ALARM_RECURRENCE INT[], DESCRIPTION TEXT[],
         NUMBER_OF_DATA INT, ADDRESSES TEXT[], ADDITIONAL_PARAMETERS TEXT[])
        """
        now = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        addHistory_str = ("INSERT INTO config_history (DATETIME, CONTROLLER, "
                          "STATUS, ALARM_STATUS, WARNING_LOW, WARNING_HIGH, "
                          "ALARM_LOW, ALARM_HIGH, READOUT_INTERVAL, "
                          "ALARM_RECURRENCE, DESCRIPTION, NUMBER_OF_DATA, "
                          "ADDRESSES, ADDITIONAL_PARAMETERS) VALUES "
                          "('%s'::timestamp, '%s', '%s', "
                          "ARRAY%s, ARRAY%s, ARRAY%s, ARRAY%s, ARRAY%s, "
                          "%d, ARRAY%s, ARRAY%s, %d, ARRAY%s, ARRAY%s)" %
                          (now, controller['controller'], controller['status'],
                              str(controller['alarm_status']), str(controller['warning_low']),
                              str(controller['warning_high']), str(controller['alarm_low']),
                              str(controller['alarm_high']), controller['readout_interval'],
                              str(controller['alarm_recurrence']), str(controller['description']),
                              controller['number_of_data'], str(controller['addresses']),
                              str(controller['additional_parameters'])))
        if self.interactWithDatabase(addHistory_str) == -1:
            self.logger.warning("Can not add settings of %s to config_history. "
                                "Database interaction error." % controller['controller'])
            return -1
        return 0

    def readConfig(self, name='all'):
        """
        Reads the table config in the database. The format is:
        (CONTROLLER TEXT, STATUS TEXT, ALARM_STATUS TEXT,
         WARNING_LOW REAL[], WARNING_HIGH REAL[], ALARM_LOW REAL[],
         ALARM_HIGH REAL[])
         READOUT_INTERVAL INT, ALARM_RECURRENCE INT[], DESCRIPTION TEXT[],
         NUMBER_OF_DATA INT, ADDRESSES TEXT[], ADDITIONAL_PARAMETERS TEXT[])
        """
        if name == 'all':
            select_str = "SELECT * FROM config"
        else:
            select_str = "SELECT * FROM config WHERE CONTROLLER = '%s'" % str(
                name)
        controller_config = self.interactWithDatabase(select_str,
                                                      readoutput=True)
        if not controller_config:
            if name == 'all':
                self.logger.info("Config table empty.")
                return 'EMPTY'
            else:
                self.logger.warning("No controller with name '%s' "
                                    "found in DB" % str(name))
        elif controller_config == -1:
            self.logger.warning("Can not read from config table in DobermanDB. "
                                "Database interaction error.")
            return -1

        column_names = self.getConfigColumnNames()
        config_dict = {}
        if name=='all':
            # dict of dicts
            for controller in controller_config:
                controller_name = controller[0]
                config_dict[controller_name] = {}
                for col,val in zip(column_names, controller):
                    config_dict[controller_name][col] = val
        else:
            for col,val in zip(column_names, controller_config[0]):
                config_dict[col] = val
        return config_dict

    def printParameterDescription(self):
        """
        This function prints all information for each parameter
        which should be entered in the config database table.
        """
        text = []
        text.append("Name: -- Name of your device. "
                    "Make sure your Plugin code is named the correct way.")
        text.append("Status: -- ON/OFF: is your instrument (or plugin) turned on or not. Resp."
                    " should it collect data over the Doberman slow control.")
        text.append("Alarm Status: -- ON/OFF,...: "
                    "Should your device send warnings and alarms if your data "
                    "is out of the limits\n "
                    "   or your device reports an error or sends no data.\n "
                    "   This can be individual for each value in one readout. "
                    "E.g: ON,OFF,ON")
        text.append("Lower Warning Level -- : Float,...: "
                    "Enter the lower warning level for your data values.\n "
                    "   If the values are below this limit a warning (email) "
                    "will be sent if the alarm status is ON.\n "
                    "   This can be set individually for each value in one "
                    "readout. E.g: 1.25,54,0.")
        text.append("Higher Warning Level: -- Float,...: "
                    "Enter the higher warning level for your data values. "
                    "Analog Lower Warning Level.")
        text.append("Lower Alarm Level: --  Float,...: "
                    "Enter the higher warning level for your data values.\n "
                    "   If the values are below this limit a alarm (SMS) will "
                    "be sent if the alarm status is ON.\n "
                    "   This can be set individual for each value in one "
                    "readout. E.g: 1.25,54,0.")
        text.append("Higher Alarm Level: -- Float,...: "
                    "Enter the higher warning level for your data values. "
                    "Analog Lower Alarm Level.")
        text.append("Readout interval: -- How often (in seconds) should your "
                    "device read the data and send it to the Doberman "
                    "slow control. Default = 5 seconds")
        text.append("Alarm recurrence: -- How many times in a row has the "
                    "data to be out of the warning/alarm limits before an "
                    "alarm/warning is sent.")
        text.append("Description: -- Text,...: Describe your data and units. "
                    "E.g. what is transmitted, what is the unit,...\n "
                    "   Add a description for all your values transmitted "
                    "in one readout.")
        text.append("Number of data: -- Integer (1-100): How many individual "
                    "data values are returned in 1 readout.")
        text.append("Addresses: -- List(Text): Where to find your Plugin.\n"
                    "    [0]: Connection type (LAN/SER/0) how is it connected. "
                    "(Asked at a separate input)\n"
                    "    [1]: First Address: (IP Address/Product ID/0): What is "
                    "the IP Address (LAN) or Product ID (Serial).\n"
                    "    [2]: Second Address: (Port/Vendor ID/0): What is the "
                    "Port (LAN) or Product ID (serial)")
        text.append("Additional parameters: -- List: Enter all additional "
                    "Parameters which the plugin needs and are not mentioned "
                    "in any of the other points.")
        for sentence in text:
            print("\n - " + sentence)

    def getUserInput(self, text, input_type=None, be_in=None, be_not_in=None, be_array=False, limits=None, string_length=None, exceptions=None):
        """
        Ask for an input bye displaying the 'text'.
        It is asked until:
          the input has the 'input_type(s)' specified,
          the input is in the list 'be_in' (if not None),
          not in the list 'be_not_in' (if not None),
          the input is between the limits (if not None).
          has the right length if it is a string (if not None)
        'input_type', 'be_in' and 'be_not_in' must be lists or None.
        'limits' must be a list of type [lower_limit, higher_limit].
        ' lower_limit' or 'higher_limit' can be None. The limit is <=/>=.
        'string_length' must be a list of [lower_length, higher_length]
        ' lower_length' or 'higher_length' can be None. The limit is <=/>=.
        'be_array' can be True or False, it returns the input as array or not.
        If the input is in the exceptions it is returned without checks.
        """
        while True:
            # Ensure the right evaluation format for inputs.
            if input_type == [str]:
                literaleval = False
            else:
                literaleval = True
            # Read input.
            try:
                user_input = self.__input_eval__(input(text), literaleval)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print("Error: %s. Try again." % e)
                continue
            # Check for input exceptions
            if exceptions:
                if user_input in exceptions:
                    return user_input
            # Remove string signs
            if input_type == [str] and isinstance(user_input, str):
                user_input = ''.join(c for c in user_input if c not in ['"',"'"])
            # Transform input to list
            if not be_array:
                user_input = [user_input]
            else:
                if isinstance(user_input, tuple):
                    user_input = list(user_input)
                elif isinstance(user_input, str):
                    user_input = user_input.split(",")
                elif isinstance(user_input, (int, float)):
                    user_input = [user_input]
            # Remove spaces after comma for input lists
            if be_array and input_type == [str]:
                user_input = [item.strip() for item in user_input]
            # Check input for type, be_in, be_not_in, limits.
            if input_type:
                if not all(isinstance(item, tuple(input_type)) for item in user_input):
                    print("Wrong input format. Must be in %s. "
                          "Try again." %
                          str(tuple(input_type)))
                    continue
            if be_in:
                if any(item not in be_in for item in user_input):
                    print("Input must be in: %s. Try again." % str(be_in))
                    continue
            if be_not_in:
                if any(item in be_not_in for item in user_input):
                    print("Input is not allowed to be in: %s. "
                          "Try again." % str(be_not_in))
                    continue
            if limits:
                if limits[0] or limits[0] == 0:  # Allows also 0.0 as lower limit
                    if any(item < limits[0] for item in user_input):
                        print("Input must be between: %s. "
                              "Try again." % str(limits))
                        continue
                if limits[1]:
                    if any(item > limits[1] for item in user_input):
                        print("Input must be between: %s. "
                              "Try again." % str(limits))
                        continue
            # Check for string length
            if string_length:
                if string_length[0] != None:
                    if any(len(item) < string_length[0] for item in user_input):
                        print("Input string must have more than %s characters."
                              " Try again." % str(string_length[0]))
                        continue
                if string_length[1] != None:
                    if any(len(item) > string_length[1] for item in user_input):
                        print("Input string must have less than %s characters."
                              " Try again." % str(string_length[1]))
                        continue
            break
        if not be_array:
            return user_input[0]
        return user_input

    def adjustListLength(self, input_list, length, append_item, input_name=None):
        """
        Appending 'append_item' to the 'input_list'
        untill 'length' is reached.
        """
        while len(input_list) < length:
            if input_name:
                print("Warning: Lenght of list '%s' too small, "
                      "appending '%s'." % (input_name, str(append_item)))
            else:
                print("Warning: Lenght of list too small, "
                      "appending '%s'." % str(append_item))
            input_list.append(append_item)
        if len(input_list) > length:
            if input_name:
                print("Warning: Lenght of list '%s' larger than expected "
                      "(%s > %s)." % (input_name, str(len(input_list)),
                                      str(length)))
            else:
                print("Warning: Lenght of list larger than expected.")
        return input_list

    def addControllerByKeyboard(self):
        """
        With this function you can add a controller to the database
        over the terminal.
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        # Print informations
        print('\n' + 60 * '-' + '\nNew controller. ' +
              'Please enter the following parameters below:\n')
        self.printParameterDescription()
        print('\n' + 60 * '-' + '\n')
        print('  - No string signs (") needed.\n  '
              '- Split arrays with comma (no spaces after it), '
              'no brackets needed!  \n  '
              '- Enter 0 for no or default value  \n' + 60 * '-')
        name = None
        # Enter all parameters:
        # Name
        while not name:
            name = self.getUserInput("Controller name:", input_type=[str],
                                     be_not_in=[list(map(str, list(range(100))))])
            # Check if name exists already
            if self._config == "EMPTY":  # First device
                pass
            elif name in self._config:
                #elif [dev[0] for dev in self._config if dev[0] == name]:
                print("There is already a controller with the name '%s'." %
                      str(name))
                text = "Do you want to change '%s' (y/n)?" % str(name)
                if self.getUserInput(text, input_type=[str]) in ['y', 'Y', y, Y]:
                    self.changeControllerByKeyboard()
                    return
                else:
                    name = None
        # Status:
        text = "Controller '%s': Status (ON/OFF):" % name
        status = self.getUserInput(text, be_in=['ON', 'OFF'])
        # Number of Data:  # Pulled here because it needs to know list length.
        text = ("Controller '%s': Number of data values "
                "per transmission (integer):" % name)
        number_of_data = self.getUserInput(text, input_type=[int],
                                           limits=[1, 100])
        # Alarm status:
        text = ("Controller '%s': Alarm status(es) "
                "(ON/OFF,... e.g. ON,OFF,ON):" % name)
        alarm_status = self.getUserInput(text, input_type=[str],
                                         be_in=['ON', 'OFF'], be_array=True)
        alarm_status = self.adjustListLength(alarm_status, number_of_data,
                                             "OFF", "Alarm status")
        # Lower warning levels:
        text = ("Controller '%s': Lower WARNING level(s): (float(s)):" % name)
        warning_low = self.getUserInput(text, input_type=[int, float],
                                        be_array=True)
        warning_low = self.adjustListLength(warning_low, number_of_data,
                                            0, "Lower warning levels")
        # Higher warning levels:
        text = ("Controller '%s': Higher WARNING level(s): (float(s)):" % name)
        warning_high = self.getUserInput(text, input_type=[int, float],
                                         be_array=True)
        warning_high = self.adjustListLength(warning_high, number_of_data,
                                             0, "Higher warning levels")
        # Lower alarm levels:
        text = ("Controller '%s': Lower ALARM level(s): (float(s)):" % name)
        alarm_low = self.getUserInput(text, input_type=[int, float],
                                      be_array=True)
        alarm_low = self.adjustListLength(alarm_low, number_of_data,
                                          0, "Lower alarm levels")
        # Higher alarm levels:
        text = ("Controller '%s': Higher ALARM level(s): (float(s)):" % name)
        alarm_high = self.getUserInput(text, input_type=[int, float],
                                       be_array=True)
        alarm_high = self.adjustListLength(alarm_high, number_of_data,
                                           0, "Higher alarm levels")
        # Readout interval:
        text = ("Controller '%s': Readout Interval "
                "(in seconds, integer):" % name)
        readout_interval = self.getUserInput(text, input_type=[int],
                                             limits=[1, 86400])
        # Alarm recurrence:
        text = ("Controller '%s': Recurrence (# of times in a row that data "
                "needs to exceed the alarm/warning limit before alarm/warning "
                "is sent, integer):" % name)
        recurrence = self.getUserInput(text, input_type=[int],
                                       be_array=True, limits=[1, 99])
        recurrence = self.adjustListLength(recurrence, number_of_data,
                                           1, "Recurrence")
        # Description:
        text = ("Controller '%s': Description of data value(s)/"
                "Info(s)/Unit(s)/ect.:" % name)
        description = self.getUserInput(text, input_type=[str],
                                        be_array=True,
                                        string_length=[None, 50])
        description = self.adjustListLength(description, number_of_data,
                                            '', "Description")
        # Addresses:
        text = "Controller '%s': Connection type (LAN/SER/0)" % name
        connection_type = self.getUserInput(text,
                                            input_type=[str],
                                            be_in=['LAN', 'SER', 0, '0'])
        text = ("Controller '%s': Addresses (["
                "First address((IP Address/Product ID/0),"
                "Second address(Port/Vendor ID/0)]):" % name)
        addresses = self.getUserInput(text,
                                      input_type=[str],
                                      string_length=[None, 20],
                                      be_array=True)
        addresses = self.adjustListLength(addresses, 2, '',
                                          "Addresses ([""Address1,Address2])")
        addresses = [connection_type] + addresses
        # Additional parameters:
        text = "Controller '%s': Additional parameters:" % name
        additional_parameters = self.getUserInput(text, input_type=[str],
                                                  be_array=True)
        # Check alarm/warning levels.
        for ii, al_stat in enumerate(alarm_status):
            try:
                if al_stat == 'ON' and not (alarm_low[ii] <= warning_low[ii] < warning_high[ii] <= alarm_high[ii]):
                    print("Warning: Invalid alarm/warning levels %d. "
                          "Set alarm status %d to 'OFF' by default" % (ii, ii))
                    alarm_status[ii] = 'OFF'
            except Exception as e:
                print("Warning: Can not compare alarm/warning levels %d. "
                      "Error %s. Set alarm status %d to 'OFF' by default" %
                      (ii, e, ii))
                alarm_status[ii] = 'OFF'
        # Make changes at database.
        add_str = ("INSERT INTO config (CONTROLLER, STATUS, ALARM_STATUS, "
                   "WARNING_LOW, WARNING_HIGH, ALARM_LOW, ALARM_HIGH, "
                   "READOUT_INTERVAL, ALARM_RECURRENCE, DESCRIPTION, "
                   "NUMBER_OF_DATA, ADDRESSES , ADDITIONAL_PARAMETERS) "
                   "VALUES ('%s', '%s', ARRAY%s, ARRAY%s, ARRAY%s, ARRAY%s, "
                   "ARRAY%s, %d, ARRAY%s, ARRAY%s, %d, ARRAY%s, ARRAY%s)" %
                   (name, status, str(alarm_status), str(warning_low),
                    str(warning_high), str(alarm_low), str(alarm_high),
                    readout_interval, str(recurrence), str(description),
                    number_of_data, str(addresses),
                    str(additional_parameters)))
        counter = 0
        while self.interactWithDatabase(add_str) == -1:
            if counter >= 2:
                print("Can not add controller %s." % name)
                return -1
            print("Trying again in 1 s...")
            time.sleep(1)
            counter += 1
        print("Successfully entered %s to the database." % name)
        self.logger.debug("Creating Data Table...")
        if self.createDataTable(name) == -1:
            self.logger.fatal("Could not create a data table for "
                              "controller %s" % name)
        #settings = [name, status, alarm_status, warning_low,
        #            warning_high, alarm_low, alarm_high,
        #            readout_interval, recurrence, description,
        #            number_of_data, str(addresses),
        #            additional_parameters]
        settings = {'controller' : name, 'status' : status, 'alarm_status' : alarm_status,
                    'warning_low' : warning_low, 'warning_high' : warning_high,
                    'alarm_low' : alarm_low, 'alarm_high' : alarm_high,
                    'readout_interval' : readout_interval, 'alarm_recurrence' : recurrence,
                    'description' : description, 'number_of_data' : number_of_data,
                    'addresses' : addresses, 'additional_parameters' : additional_parameters}
        parameters = ['           Name', '         Status', '   Alarm status',
                      '    Warning low', '   Warning high', '      Alarm low',
                      '     Alarm high', 'ReadoutInterval', '     Recurrence',
                      '    Description', ' Number of data', '      Addresses',
                      'Additional par.']
        print("The stored parameters are:\n")
        for ii, entry in enumerate(settings.keys()):
            if parameters[ii] == 'ReadoutInterval':
                print(" ")
            print(" %s: %s " % (parameters[ii], settings[entry]))
        print(60 * '-')
        self.addSettingToConfigHistory(settings)
        self.refreshConfigBackup()

    def changeControllerByKeyboard(self, change_all=True):
        if self._config == "EMPTY":
            print("Config empty. Can not change plugin settings. "
                  "Add it first with 'python Doberman.py -a'.")
            return
        n = 'n'
        print('\n' + 60 * '-' + '\nUpdate plugin settings. '
              'The following parameters can be changed:\n')
        self.printParameterDescription()
        print('\n' + 60 * '-')
        print('  - No string signs (") needed.\n  '
              '- Split arrays with comma (no spaces after it), '
              'no brackets needed!  \n  '
              '- Enter 0 for no or default value,  \n  '
              '- Enter n for no change.')
        print('\n' + 60 * '-' + '\n Choose the controller you want to change. '
              '(If you would like to add a new controller use option -a instead)\n')
        devices = list(self._config.keys())
        for number, controller in enumerate(devices):
            print("%s:\t%s" % (str(number), controller))
        # Enter name to find controller
        existing_names = devices #[dev[0] for dev in self._config]
        existing_numbers = list(map(str, list(range(len(existing_names)))))
        existing_devices = existing_names + existing_numbers
        text = "\nEnter controller number or alternatively its name:"
        name = self.getUserInput(text, input_type=[str],
                                 be_in=existing_devices)
        try:
            controller = self._config[name]
        except KeyError:
            name = devices[int(name)]
            controller = self._config[name]
        #if controller:
        #    controller = controller[0]
        #else:
        #    controller = self._config[int(name)]
        #    name = controller[0]
        # Print current parameters and infos.
        print('\n' + 60 * '-' + '\n')
        print('The current parameters are:\n')
        parameters = ['           Name', '         Status', '   Alarm status',
                      '    Warning low', '   Warning high', '      Alarm low',
                      '     Alarm high', 'ReadoutInterval', '     Recurrence',
                      '    Description', ' Number of data', '      Addresses',
                      'Additional par.']
        for key in controller.keys():
            if key == 'readout_interval':
                print(" ")
            print("{:>16}: {} ".format(key, controller[key]))
        print(60 * '-')
        # Status
        text = ("Controller '%s': Status (ON/OFF):" % name)
        status = self.getUserInput(text, input_type=[str],
                                   be_in=['ON', 'OFF', 'n'])
        if status != 'n':  # Continue with old status if no change
            controller['status'] = status
        # Number of Data: # Pull here because it needs to know n_o_d for others
        if change_all:
            text = ("Controller '%s': Number of data values "
                    "per transmission (integer):" % name)
            number_of_data = self.getUserInput(text,
                                               input_type=[int],
                                               limits=[1, 100],
                                               exceptions=['n'])
            if number_of_data != 'n':
                controller['number_of_data'] = number_of_data
            else:
                number_of_data = controller['number_of_data']
        # Alarm status:
        text = ("Controller '%s': Alarm status(es) "
                "(ON/OFF,... e.g. ON,OFF,ON):" % name)
        alarm_status = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=['ON', 'OFF'],
                                         be_array=True,
                                         exceptions=['n'])
        if alarm_status != 'n':
            controller['alarm_status'] = self.adjustListLength(
                    alarm_status, number_of_data, "OFF", "Alarm status")
        # Lower warning levels:
        text = ("Controller '%s': Lower WARNING level(s): (float(s)):" % name)
        warning_low = self.getUserInput(text,
                                        input_type=[int, float],
                                        be_array=True,
                                        exceptions=['n'])
        if warning_low != 'n':
            controller['warning_low'] = self.adjustListLength(
                    warning_low, number_of_data, 0, "Lower warning levels")
        # Higher warning levels:
        text = ("Controller '%s': Higher WARNING level(s): (float(s)):" % name)
        warning_high = self.getUserInput(text,
                                         input_type=[int, float],
                                         be_array=True,
                                         exceptions=['n'])
        if warning_high != 'n':
            controller['warning_high'] = self.adjustListLength(
                    warning_high, number_of_data, 0, "Higher warning levels")
        # Lower alarm levels:
        text = ("Controller '%s': Lower ALARM level(s): (float(s)):" % name)
        alarm_low = self.getUserInput(text,
                                      input_type=[int, float],
                                      be_array=True,
                                      exceptions=['n'])
        if alarm_low != 'n':
            controller['alarm_low'] = self.adjustListLength(
                    alarm_low, number_of_data, 0, "Lower alarm levels")
        # Higher alarm levels:
        text = ("Controller '%s': Higher ALARM level(s): (float(s)):" % name)
        alarm_high = self.getUserInput(text,
                                       input_type=[int, float],
                                       be_array=True,
                                       exceptions=['n'])
        if alarm_high != 'n':
            controller['alarm_high'] = self.adjustListLength(
                    alarm_high, number_of_data, 0, "Higher alarm levels")

        for ii, al_stat in enumerate(controller['alarm_status']):
            try:
                if al_stat == 'ON' and not (alarm_low[ii] <= warning_low[ii] < warning_high[ii] <= alarm_high[ii]):
                    print("Warning: Invalid alarm/warning levels %d. "
                          "Set alarm status %d to 'OFF' by default" % (ii, ii))
                    controller['alarm_status'][ii] = 'OFF'
            except Exception as e:
                print("Warning: Can not compare alarm/warning levels %d. "
                      "Error %s. Set alarm status %d to 'OFF' by default" %
                      (ii, e, ii))
                controller['alarm_status'][ii] = 'OFF'
        # Update first half
        print("Updating inputs...")
        alarm_low = controller['alarm_low']
        alarm_high = controller['alarm_high']
        alarm_status = controller['alarm_status']
        warning_low = controller['warning_low']
        warning_high = controller['warning_high']
        status = controller['status']

        update_str1 = ("UPDATE config SET STATUS = '%s', "
                       "ALARM_STATUS = ARRAY%s, WARNING_LOW = ARRAY%s, "
                       "WARNING_HIGH = ARRAY%s, ALARM_LOW = ARRAY%s, "
                       "ALARM_HIGH = ARRAY%s WHERE CONTROLLER = '%s'" %
                       (status, str(alarm_status), str(warning_low),
                        str(warning_high), str(alarm_low), str(alarm_high),
                        name))
        if self.interactWithDatabase(update_str1) == -1:
            print("Could not update first half. Database interaction error.")
        else:
            print("Successfully updated first half.")
        # Jump over second half if not change_all = True
        if not change_all:
            print("The new parameters are:\n")
            for key in controller.keys():
                print("{:>16}: {} ".format(key, str(controller[key])))
            print(60 * '-')
            self.addSettingToConfigHistory(controller)
            self.refreshConfigBackup()
            return
        # Second half -uu only
        # Readout interval:
        text = ("Controller '%s': Readout Interval "
                "(in seconds, integer):" % name)
        readout_interval = self.getUserInput(text,
                                             input_type=[int],
                                             limits=[1, 86400],
                                             exceptions=['n'])
        if readout_interval != 'n':
            controller['readout_interval'] = readout_interval
        # Alarm recurrence:
        text = ("Controller '%s': Recurrence (# of times in a row that data "
                "needs to exceed the alarm/warning limit before alarm/warning "
                "is sent, integer):" % name)
        recurrence = self.getUserInput(text,
                                       input_type=[int],
                                       be_array=True,
                                       limits=[1, 99],
                                       exceptions=['n'])
        if recurrence != 'n':
            controller['recurrence'] = self.adjustListLength(
                    recurrence, number_of_data, 1, "Recurrence")
        # Description:
        text = ("Controller '%s': Description of data value(s)/"
                "Info(s)/Unit(s)/ect.:" % name)
        description = self.getUserInput(text,
                                        input_type=[str],
                                        be_array=True,
                                        string_length=[None, 50],
                                        exceptions=['n'])
        if description != 'n':
            controller['description'] = self.adjustListLength(
                    description, number_of_data, '', "Description")
        # Addresses:
        text = "Controller '%s': Connection type (LAN/SER/0))" % name
        connection_type = self.getUserInput(text,
                                            input_type=[str],
                                            be_in=['LAN', 'SER', 0, '0'],
                                            exceptions=['n'])
        if connection_type != 'n':
            controller['addresses'][0] = connection_type
        text = ("Controller '%s': Addresses (["
                "First address((IP Address/Product ID/0),"
                "Second address(Port/Vendor ID/0)]):" % name)
        addresses = self.getUserInput(text,
                                      input_type=[str],
                                      string_length=[None, 20],
                                      be_array=True,
                                      exceptions=['n'])
        if addresses != 'n':
            controller['addresses'][1:] = self.adjustListLength(
                    addresses, 2, '', "Addresses ([Address1,Address2])")

        # Additional paramters:
        text = "Controller '%s': Additional parameters:" % name
        additional_parameters = self.getUserInput(text,
                                                  input_type=[str],
                                                  be_array=True,
                                                  exceptions=['n'])
        if additional_parameters != 'n':
            controller['additional_parameters'] = additional_parameters
        # Update second part:
        readout_interval = controller['readout_interval']
        recurrence = controller['recurrence']
        description = controller['description']
        number_of_data = controller['number_of_data']
        addresses = controller['addresses']
        additional_parameters = controller['additional_parameters']
        print("Updating second half of input...")
        update_str2 = ("UPDATE config SET READOUT_INTERVAL = %d, "
                       "ALARM_RECURRENCE = ARRAY%s, DESCRIPTION = ARRAY%s, "
                       "NUMBER_OF_DATA = %d, ADDRESSES = ARRAY%s, "
                       "ADDITIONAL_PARAMETERS = ARRAY%s "
                       "WHERE CONTROLLER = '%s'" %
                       (readout_interval, str(recurrence), str(description),
                        number_of_data, str(addresses),
                        str(additional_parameters), name))
        if self.interactWithDatabase(update_str2) == -1:
            print("Could not update second half. Database interaction error.")
            return
        # Summarize new settings
        print("Successfully updated second half.\n\n"
              "The new parameters are:\n")
        for key in controller:
            print("{:>16}: {}".format(key, str(controller[key])))
        print(60 * '-')
        self.addSettingToConfigHistory(controller)
        self.refreshConfigBackup()

    def removeControllerFromConfig(self):
        '''
        Deletes a controller from the config table.
        Asks if Data table should be deleted as well.
        '''
        if self._config == "EMPTY":
            print("Config empty. Can not remove a controller.")
            return
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        existing_names = list(self._config.keys()) #[dev[0] for dev in self._config]
        # Ask for controller to delete and confirmation.
        text = ("\nEnter the name of the controller you would like to remove "
                "from config:")
        name = self.getUserInput(text,
                                 input_type=[str],
                                 be_in=existing_names)
        text = ("Do you really want to remove %s from the config table? (y/n) "
                "This can not be reverted." % name)
        confirmation = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=[y, Y, n, N])
        if confirmation not in [y, Y]:
            return 0
        # Delete from the database
        delete_str = ("DELETE FROM config WHERE CONTROLLER = '%s'" % name)
        if self.interactWithDatabase(delete_str) == -1:
            self.logger.warning("Can not remove '%s' from config. Database "
                                "interaction error." % name)
            return -1
        self.logger.info(
            "Successfully removed '%s' from the config table." % name)
        # Ask for deleting data table as well.
        text = ("\nDo you also want to delete the data table of '%s'? (y/n)? "
                "All stored data in 'Data_%s' will be lost." % (name, name))
        drop_table = self.getUserInput(text,
                                       input_type=[str],
                                       be_in=[y, Y, n, N])
        if drop_table not in [y, Y]:
            return 0
        # Delete data table in the database.
        delete_str = "TRUNCATE Data_%s" % name
        if self.interactWithDatabase(delete_str) == -1:
            self.logger.warning(
                "Can not delete Data_%s. Database interaction error." % name)
            return -1
        self.logger.info("Successfully deleted all data from Data_%s." % name)

    def getConfigColumnNames(self):
        '''
        Returns a list of the column names in the config table
        '''
        return self.getColumnNames('config')

    def getColumnNames(self, table):
        '''
        Returns a list of column names from the specified table
        '''
        if table not in self.getAllTableNames():
            print('Table %s doesn\'t exist?' % table)
            print('Tables: %s' % self.getAllTableNames())
            return -1
        column_str = ("SELECT column_name FROM information_schema.columns "
                      "WHERE table_name='%s';" % table)
        output = self.interactWithDatabase(column_str, readoutput=True)
        if output in [0, '']:
            return []
        columns = [row[0] for row in output]
        return columns

    def recreateTableDefaultSettings(self, force_to=False):
        """
        (Re)Creates the Doberman general (default) settings
        """
        if not force_to:
            y, Y = 'y', 'Y'
            n, N = 'n', 'N'
            text = ("Are you sure you want to (clear and) recreate table "
                "'default_settings'? All saved defaults will be lost. (y/n)?")
            user_input = self.getUserInput(text,
                                           input_type=[str],
                                           be_in=[y, Y, n, N])
            if user_input not in ['Y', 'y']:
                return
        drop_str = "DROP TABLE IF EXISTS default_settings"
        create_str = ("CREATE TABLE IF NOT EXISTS default_settings "
                      "(_id SERIAL PRIMARY KEY, "
                      "PARAMETER TEXT, VALUE TEXT, DESCRIPTION TEXT)")
        if self.interactWithDatabase(drop_str, additional_actions=[create_str]) == -1:
            self.logger.warning("Can not crate 'default_settings' "
                                "table in database.")
            return -1
        # Fill with standard defaults:
        # load from file?
        default_list = [["Warning_Repetition", "10", "Min. time [min] between two warnings."],
                        ["Alarm_Repetition", "5", "Min. time [min] between two alarms."],
                        ["Testrun", "2", "Time [min] after start until a alarm/warning can be sent."],
                        ["Loglevel", "20", "Logging output level (10=Default, 20=Info,...)."],
                        ["Importtimeout", "10", "Max. time [s] to import a plugin."],
                        ["Occupied_ttyUSB", "[]", "Predefined Occupied ttyUSB ports."],
                        ["Queue_size", "150", "Critical queue size to report error."]]
        for item in default_list:
            add_str = ("INSERT INTO default_settings (PARAMETER, VALUE, DESCRIPTION) "
                       " VALUES ('%s', '%s', '%s')" % (item[0], item[1], item[2]))
            if self.interactWithDatabase(add_str) == -1:
                self.logger.error("Can not add '%s' to "
                                  "'default_settings' table." % item[0])

    def updateDefaultSettings(self):
        """
        Updates the default Doberman settings
        """
        settings = self.getDefaultSettings()
        if settings == -1:
            return -1
        q, Q = 'q', 'q'
        print("\nThe following Doberman settings are stored:")
        for ii, item in enumerate(settings):
            print(ii, ": ", item)
        while True:
            text= ("\nEnter number of entry you would like to change or 'q' "
                   "to quit.")
            user_input = self.getUserInput(text,
                                           input_type=[int],
                                           be_in=list(range(len(settings))),
                                           exceptions = [q, Q])
            if user_input == q:
                break
            ii = user_input
            text = ("Enter new value for %s (%s)." % (settings[ii][0], settings[ii][2]))
            if settings[ii][0] == "Occupied_ttyUSB":
                be_array = True
                input_type = [int]
                be_in = None
            elif settings[ii][0] == "Loglevel":
                input_type = [int]
                be_in = [0, 10, 20, 30, 40, 50]
                be_array = False
            else:
                input_type = [int]
                be_in = None
                be_array = False
            user_input = self.getUserInput(text,
                                           input_type=input_type,
                                           be_in=be_in,
                                           be_array=be_array)
            update_str = ("UPDATE default_settings SET VALUE = '%s' WHERE "
                          "PARAMETER = '%s'" % (str(user_input),
                                                settings[ii][0]))
            if self.interactWithDatabase(update_str) != -1:
                self.logger.info("Updated %s." % settings[ii][0])
        print("Quitting... New settings are:")
        newsettings = self.getDefaultSettings()
        for ii, item in enumerate(list(newsettings)):
            print(ii, ": ", item)
        return

    def getAllTableNames(self):
        """
        Returns a list of all tables in the database.
        """
        check_str = ("select relname from pg_class where relkind='r' "
                     "and relname !~ '^(pg_|sql_)'")
        table_list = self.interactWithDatabase(check_str, readoutput=True)
        tables = [t[0] for t in table_list]
        return tables

    def getDefaultSettings(self, name=None):
        """
        Reads default Doberman settings from database.
        Returns as list with [Parameter, Value] both as strings
        Reading with name only works for int!
        """
        if "default_settings" not in str(self.getAllTableNames()):
            print("Default settings do not exist. "
                  "Trying to crate...")
            self.recreateTableDefaultSettings()
        get_str = "SELECT * from default_settings"
        settings = self.interactWithDatabase(get_str, readoutput=True)
        if settings == -1:
            self.logger.warning("Unable to read default settings.")
            return -1
        if not name:
            return settings
        else:
            try:
                settings = [int(s[1]) for s in settings if s[0] == name][0]
            except IndexError as e:
                self.logger.error("Can not read default settings. %s "
                                  "Refreshing default settings... "
                                  "All values are set back to default." %e)
                self.recreateTableDefaultSettings(force_to=True)
            except Exception as e:
                self.logger.error("Can not read defaut settings. %s" % e)
                return -1
        return settings

    def recreateTableContact(self):
        """
        (Re)Creates the contact table
          which is used for alarm/warning distribution
        """
        y, Y = 'y', 'Y'
        n, N = 'n', 'N'
        text = ("Are you sure you want to clear and recreate table 'contact'? "
                "All saved contacts will be lost. (y/n)?")
        drop_contacts = self.getUserInput(text,
                                          input_type=[str],
                                          be_in=[y, Y, n, N])
        if drop_contacts not in ['Y', 'y']:
            return
        drop_str = "DROP TABLE IF EXISTS contact"
        create_str = ("CREATE TABLE contact (_id SERIAL PRIMARY KEY, "
                      "NAME TEXT, STATUS TEXT, "
                      "MAILADDRESS TEXT, PHONE TEXT)")
        if self.interactWithDatabase(drop_str, additional_actions=[create_str]) == -1:
            self.logger.warning("Can not crate 'contact' table in database.")
            return -1
        else:
            self.logger.info("Successfully (re)crated table contact")
            return 0

    def readContacts(self,status=None):
        """
        Reads contacts from database.
        """
        if not status:
            select_str = "SELECT * FROM contact"
        else:
            select_str = "SELECT * FROM contact WHERE STATUS = '%s'" % str(
                status)
        contacts = self.interactWithDatabase(select_str, readoutput=True)
        if contacts == '':
            self.logger.warning(
                "No contacts found (with status %s)" % str(status))
            contacts = []
        elif contacts == -1:
            self.logger.warning("Can not read from contact table in database. "
                                "Database interaction error.")
            return -1
        return contacts

    def getContacts(self, status=None):
        """
        Reads contacts. If status=None, all contacts are returned,
        otherwise only the ones with given status.
        If no connection to database, it reads from the backup.
        """
        contacts = self.readContacts(status)
        if contacts == -1:
            contacts = self.getContactsFromBackup(status)
            if contacts == -1:
                return -1
        return contacts

    def updateContactsByKeyboard(self):
        """
        Add, update and delete contacts
        """
        a, u, d = 'a', 'u', 'd'
        n, N, y, Y = 'n', 'N', 'y', 'Y'
        mail_changed = False
        contacts = self.getContacts()
        existing_names = [contact[0] for contact in contacts]
        existing_numbers = list(map(str, list(range(len(existing_names)))))
        existing_contacts = existing_names + existing_numbers
        # Print informations
        print('\n' + 60 * '-' + '\n')
        print('  - No string signs (") needed.\n  '
              '- Split arrays with comma (no spaces after it), '
              'no brackets needed!\n  '
              '- Enter 0 for no or default value\n  '
              '- Enter n for no change (in update mode only)')
        print('\n' + 60 * '-' +
              '\n  Saved contacts are:\n  (Name, Status, Email, Phone)\n')
        if contacts == -1:
            self.logger.error("Could not load contacts.")
            return -1
        for ii, contact in enumerate(contacts):
            print(ii, ': ', contact)
        print('\n' + 60 * '-' + '\n')
        # Get job selection
        text = "Would you like to add (a), update (u) or delete (d) contact?"
        job = self.getUserInput(text, input_type=[str], be_in=[a, u, d])
        # Delete contact
        if job == 'd':
            text = ("Enter the name of the contact you would like to delete. "
                    "This can not be reverted.")
            name = self.getUserInput(text,
                                     input_type=[str],
                                     be_in=existing_names)
            contact_string = "DELETE FROM contact WHERE NAME = '%s'" % name
        # Add new contact
        elif job == 'a':
            # Name
            text = ("Enter the name of the contact")
            be_not_in_names = existing_names + list(map(str, list(range(100))))
            name = self.getUserInput(text,
                                     input_type=[str],
                                     be_not_in=be_not_in_names)
            # Status
            text = ("Enter the status (No ' ' needed) of contact '%s'. "
                    "It can be "
                    "'ON' (all notifications), "
                    "'OFF' (no notifications), "
                    "'MAIL' (only by email), "
                    "'TEL' (only by phone)." % name)
            status = self.getUserInput(text,
                                       input_type=[str],
                                       be_in=['ON', 'OFF', 'MAIL', 'TEL'])
            # Mail address
            text = ("Enter the email address of contact '%s'." % name)
            mailadd = self.getUserInput(text, input_type=[str])
            mail_changed = True  # For test mail sending.
            # Phone number
            text = ("Enter the phone number (or - if none) of contact '%s' "
                    "(must be able to read SMS. Ensure correct prefix "
                    "depending on your SMS sending system.)" % name)
            phone = self.getUserInput(text,
                                      input_type=[str],
                                      exceptions=[0, '-'])
            contact_string = ("INSERT INTO contact (NAME, STATUS, "
                              "MAILADDRESS, PHONE) VALUES "
                              "('%s', '%s', '%s', '%s')" %
                              (name, status, mailadd, str(phone)))
        # Change contact
        elif job == 'u':
            # Name
            text = ("Enter the number of the contact you would like to update "
                    "or alternatively the name: ")
            name = self.getUserInput(text,
                                     input_type=[str],
                                     be_in=existing_contacts)
            original_contact = [
                contact for contact in contacts if contact[0] == name]
            if not original_contact:
                original_contact = list(contacts[int(name)])
                name = original_contact[0]
            else:
                original_contact = list(original_contact[0])
            # Status
            text = ("Enter new status of contact '%s' (or n for no change). "
                    "It can be 'ON' (all notifications), "
                    "'OFF' (no notifications), 'MAIL' (only by email), "
                    "'TEL' (only by phone)." % name)
            status = self.getUserInput(text,
                                       input_type=[str],
                                       be_in=['ON', 'OFF', 'MAIL', 'TEL', 'n'])
            if status == 'n':
                status = original_contact[1]
            # Mail address
            text = ("Enter new email address of contact '%s' "
                    "(or n for no change)." % name)
            mailadd = self.getUserInput(text, input_type=[str])
            if mailadd == 'n':
                mailadd = original_contact[2]
            else:
                mail_changed = True  # For test mail sending.
            # Phone
            text = ("Enter the new phone number (or - if none) of contact "
                    "'%s' (must be able to read SMS. Ensure correct prefix "
                    "depending on your SMS sending system.)" % name)
            phone = self.getUserInput(text,
                                      input_type=[str],
                                      exceptions=['n', 0, '-'])
            if phone == 'n':
                phone = original_contact[3]
            contact_string = ("UPDATE contact SET STATUS = '%s', "
                              "MAILADDRESS = '%s', PHONE = '%s' WHERE "
                              "NAME = '%s'" % (status, mailadd, phone, name))
        # Execute job at the database:
        if self.interactWithDatabase(contact_string) == -1:
            self.logger.warning("Could not make changes at contact table. "
                                "Database interaction error.")
            return -1
        self.logger.info("contacts updated successfully.")
        # Make mail check if changed:
        self.refreshContactsBackup()
        if not mail_changed:
            return 0
        text = ("\nA testmail will be sent to %s (%s) in order to make sure "
                "that the connection really works and to avoid typos in the "
                "address. Press enter to confirm. If you don't wand to send a "
                "testmail enter 'n' (not recommended)." % (name, mailadd))
        confirmation = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=['', y, Y, n, N])
        if confirmation in [n, N]:
            print("No confirmation mail sent.")
        else:
            self.sendMailTest(name=name, address=mailadd, status=status)
        return 0

    def sendMailTest(self, name, address, status):
        """
        Sends a test message to the address given.
        Use to make sure,
        the connection 'Doberman: Slowcontrol - contact person' is working.
        """
        print("\nSending a test mail to '%s'..." % address)
        subject = "Test mail for Doberman: slow control system."
        message = ("Hello %s.\nThis is a test message confirming that: \n"
                   "1. Your mail address was added (or changed) at the "
                   "contacts of the Doberman slow control.\n"
                   "2. The communication for alarm and warning distribution "
                   "is working.\n\nYour current status is '%s'.\n"
                   "Note that you only recive warnings and alarms if your "
                   "status is  'ON' or 'MAIL'." % (name, status))
        if self.alarmDistr.sendEmail(toaddr=address,
                                     subject=subject,
                                     message=message,
                                     Cc=None,
                                     Bcc=None,
                                     add_signature=True) != 0:
            print("An error occured. No test mail was sent!")
            return -1
        print("Successfully sent test mail. Please check if it arrived at the "
              "given address (Also check the Spam folder).")
        return 0

    def createDataTable(self, name):
        """
        Creates a data tabel for a controller.
        Name: Data_PluginName.
        Format: DATETIME, DATA, Status (as lists)
        """
        create_str = ("CREATE TABLE IF NOT EXISTS Data_%s "
                      "(_id INTEGER NOT NULL AUTO INCREMENT PRIMARY KEY, "
                      "DATETIME TIMESTAMP, DATA REAL[], STATUS INT[])" % str(
                          name))
        if self.interactWithDatabase(create_str) == -1:
            self.logger.warning("Can not add 'Data_%s' to database."
                                "Database interaction error." % name)
            return -1
        self.logger.info("Created table Data_%s in the database" % str(name))
        return 0

    def checkDataTable(self, name):
        """
        Test whether table exists or not
        """
        check_str = ("select exists(select relname from pg_class where "
                     "relname='data_%s' or relname='Data_%s')" %
                     (str(name), str(name)))
        result = self.interactWithDatabase(check_str, readoutput=True)
        if result == -1:
            self.logger.warning(
                "Cannot check existence of table Data_%s." % name)
            return -1
        elif True in result[0]:
            self.logger.info("Table with name Data_%s exists in the "
                             "database." % str(name))
            return True
        else:
            return False

    def writeDataToDatabase(self, name, mes_time, data, status):
        """
`       Writes data to the database
        Status:
          0 = OK,
          -1 = no connection,
          -2 = No error status aviable (ok)
          1-9 = Warning
          >9 = Alarm
        """
        try:
            if type(data) not in [list, tuple]:
                data = [data]
            if not all(isinstance(item, (int, float)) for item in data):
                data = [float(item) for item in data]
        except Exception as e:
            self.logger.error(
                "Data of %s has invalid format type. Error: %s" % (name, e))
        try:
            if type(status) not in [list, tuple]:
                status = [status]
            if not all(isinstance(item, (int, float)) for item in status):
                status = [float(item) for item in status]
        except Exception as e:
            self.logger.error(
                "Status of %s has invalid format type. Error: %s" % (name, e))

        if not mes_time:
            mes_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writeData_str = ("INSERT INTO Data_%s  (DATETIME, DATA, STATUS) "
                         "VALUES ('%s'::timestamp, ARRAY%s, ARRAY%s)" % (
                             name, str(mes_time), str(data), str(status)))
        if self.interactWithDatabase(writeData_str) == -1:
            if not self.checkDataTable(name):
                if self.createDataTable(name) == -1:
                    self.logger.fatal("No table existed and can not create a "
                                      "data table for controller %s" % name)
                else:
                    self.logger.info("Automatically generated data table "
                                     "for controller %s." % name)
                    return self.writeDataToDatabase(name, mes_time,
                                                    data, status)
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % name)
            return -1
        self.logger.info("Successfully wrote in to Data_%s VALUES (%s, %s, %s)" %
                         (name, mes_time, data, status))
        return 0

    def getConfig(self, name=None):
        """
        This function retruns the config data.
        """
        config = self.readConfig()
        if config in ['', -1, -2]:
            config = self.getConfigFromBackup()
            if config == -2:
                self.logger.warning("Can not read plugin settings properly.")
                return -1
        if config == {}:  # If config is empty (No controllers)
            return -2
        if not name:
            return config
        else:
            try:
                return config[name]
            except KeyError:
                return -3

    def updateConfig(self, old_config):
        """
        Updates the config variable.
        Takes deleted settings from the old config,
        so that the running software is not running out of informations
        for a certain Plugin.
        """
        new_config = self.getConfig()
        if new_config in [-1, -2, -3]:
            return -1
        new_names = list(new_config.keys()) #[entry[0] for entry in new_config]
        old_names = list(old_config.keys()) #[entry[0] for entry in old_config]
        for name in old_names:
            if name not in new_names:
                new_config[name] = old_config[name].copy()
                #new_config.append([entry for entry in old_config if entry[0] == name][0])
        return new_config

    def getData(self, name, limit=1, datetimestamp=None):
        '''
        Gets the latest data entry(es). Limit gives the number of entries.
        '''
        limit = self.__limitMapper__(limit)
        if datetimestamp is None:
            getData_str = ("SELECT * FROM Data_%s ORDER BY DATETIME DESC "
                           "LIMIT %s;" % (str(name), str(limit)))
        else:
            datetimestamp = self.__datetime2tuple__(datetimestamp)
            getData_str = ("SELECT * FROM Data_%s WHERE WHERE time_stamp "
                           "BETWEEN %s and %s ORDER BY DATETIME DESC LIMIT "
                           "%s;" % (str(name), datetimestamp[0],
                                    datetimestamp[1], str(limit)))

        latestData = self.interactWithDatabase(getData_str, readoutput=True)

        if latestData == -1:
            self.logger.warning("Can not get latest data of '%s'. "
                                "Database interaction error." % str(name))
            return -1
        return latestData

    def getLatestChanges(self, time_before, limit=10, multichanges=False):
        '''
        This function returns all changes in config
          (by searching in config_history)
          which came after the 'time_before'
          but not more changes than the limit given.
        If multichanges is 'False' only the latest change per device
          is returned, otherwise all.
        '''
        # TODO 20180619 - update to use dicts
        if True:
            return -1
        # Check formats of limit, and time_before
        limit = self.__limitMapper__(limit)
        if not isinstance(time_before, datetime.datetime):
            self.logger.error("Wrong format for time_before (Type of %s = %s),"
                              " can not get latest changes" %
                              (str(time_before), str(type(time_before))))
            return -1
        # Read form the database
        gLC_string = ("SELECT * FROM config_history ORDER BY DATETIME DESC "
                      "LIMIT %d" % limit)
        output = self.interactWithDatabase(gLC_string, readoutput=True)
        if output == -1:
            self.logger.warning("Can not get latest changes. "
                                "Database interaction error.")
            return -1
        elif output == '':
            output = []
        # Check conditions
        changes = [item for item in output if item[0] > time_before]
        if multichanges:
            return changes
        filtered_changes = []
        filtered_changes_name = []
        for selected in changes:
            if selected[1] not in filtered_changes_name:
                filtered_changes.append(selected)
                filtered_changes_name.append(selected[1])
        return filtered_changes

    def __limitMapper__(self, limit):
        if not isinstance(limit, int) or limit == -1:
            return "ALL"
        return limit

    def __datetime2tuple__(self, datetimestamp):
        if not isinstance(datetimestamp, list) and not isinstance(datetimestamp, tuple):
            if not isinstance(datetimestamp, datetime.datetime):
                self.logger.error("Wrong format for datetime "
                                  "(Type of %s = %s)" %
                                  (str(datetimestamp),
                                   str(type(datetimestamp))))
                return -1
            return (datetimestamp, datetime.datetime.now())
        return -1

    def __input_eval__(self, inputstr, literaleval=True):
        if not isinstance(inputstr, str):
            self.logger.error("Input is no string. Expected string!")
            return -1
        inputstr = inputstr.lstrip(' \t\r\n\'"').rstrip(
            ' \t\r\n"\'').expandtabs(4)
        if literaleval:
            try:
                return literal_eval(inputstr)
            except:
                return str(inputstr)#.decode('utf_8', 'replace'))
        else:
            return str(inputstr)#.decode('utf_8', 'replace'))

    def storeSettingsFromFile(self, filename):
        """
        Stores Plugin settings from a file to the database
        Caution: May overwrite other settings
        """
        all_settings = self.getConfigFromBackup(filename)
        if not all_settings or all_settings in [-1, -2]:
            print("Error: Can not load settings from file '%s'" % filename)
            raise IOError("File '%s' not found!" % filename)
        existing_names = list(self.getConfig().keys()) #[config[0] for config in self.getConfig()]
        for key in all_settings:
            if key in existing_names:
                settings = all_settings[key]
                job = ("UPDATE config SET STATUS = '%s', "
                       "ALARM_STATUS = ARRAY%s, WARNING_LOW = ARRAY%s, "
                       "WARNING_HIGH = ARRAY%s, ALARM_LOW = ARRAY%s, "
                       "ALARM_HIGH = ARRAY%s, READOUT_INTERVAL = %d, "
                       "ALARM_RECURRENCE = ARRAY%s, DESCRIPTION = ARRAY%s, "
                       "NUMBER_OF_DATA = %d, ADDRESSES = ARRAY%s, "
                       "ADDITIONAL_PARAMETERS = ARRAY%s "
                       "WHERE CONTROLLER = '%s'" %
                       (settings['status'], settings['alarm_status'], settings['warning_low'],
                           settings['warning_high'], settings['alarm_low'], settings['alarm_high'],
                           settings['readout_interval'], settings['alarm_recurrence'],
                        settings['description'], settings['number_of_data'], settings['addresses'],
                        settings['additional_parameters'], settings['controller']))
            else:
                job = ("INSERT INTO config (CONTROLLER, STATUS, ALARM_STATUS, "
                       "WARNING_LOW, WARNING_HIGH, ALARM_LOW, ALARM_HIGH, "
                       "READOUT_INTERVAL, ALARM_RECURRENCE, DESCRIPTION, "
                       "NUMBER_OF_DATA, ADDRESSES , ADDITIONAL_PARAMETERS) "
                       "VALUES ('%s', '%s', ARRAY%s, ARRAY%s, ARRAY%s, ARRAY%s"
                       ", ARRAY%s, %d, ARRAY%s, ARRAY%s, %d, ARRAY%s, ARRAY%s)"
                       % (settings['controller'], settings['status'], settings['alarm_status'],
                           settings['warning_low'],
                          settings['warning_high'], settings['alarm_low'], settings['alarm_high'],
                          settings['readout_interval'],
                          settings['alarm_recurrence'], settings['description'], settings['number_of_data'],
                          settings['addresses'], settings['additional_parameters']))
            if self.interactWithDatabase(job) == -1:
                self.logger.warning("Can not update config from file '%s'." %
                                    filename)
                raise IOError("Dababase interaction error!" % filename)
        return


if __name__ == '__main__':
    parser = ArgumentParser(
        usage='%(prog)s [options] \n\n Program to access Doberman database.')
    parser.add_argument("-d", "--debug",
                        dest="loglevel",
                        type=int,
                        help="Switch to loglevel debug.",
                        default=20)
    parser.add_argument("-n", "--new",
                        action="store_true",
                        dest="new",
                        help="(Re)Create table config (plugin settings), "
                             "config_history and contact.",
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
                        help="Remove an existing controller from the settings.",
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
    opts = parser.parse_args()

    logger = logging.getLogger()
    if opts.loglevel not in [0, 10, 20, 30, 40, 50]:
        print("ERROR: Given log level %i not allowed. "
              "Fall back to default value of 10" % opts.loglevel)
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:'
                                  '%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    opts.logger = logger

    DDB = DobermanDB(opts, logger)
    try:
        if opts.add:
            DDB.addControllerByKeyboard()
        opts.add = False

        if opts.update or opts.update_all:
            DDB.changeControllerByKeyboard(opts.update_all)
        opts.update = False

        if opts.remove:
            DDB.removeControllerFromConfig()
        opts.update = False

        if opts.contacts:
            DDB.updateContactsByKeyboard()
        opts.contacts = False

        if opts.defaults:
            DDB.updateDefaultSettings()

    except KeyboardInterrupt:
        print("\nUser input aborted! Check if your input changed anything.")

    if opts.new:
        DDB.recreateTableConfigHistory()
        DDB.recreateTableAlarmHistory()
        DDB.recreateTableConfig()
        DDB.recreateTableContact()
        DDB.recreateTableDefaultSettings()
    opts.new = False
