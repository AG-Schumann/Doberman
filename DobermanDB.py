#!/usr/bin/env python3
import time
import logging
from argparse import ArgumentParser
import _thread
import datetime
import pymongo
import os.path
import time
from ast import literal_eval
import alarmDistribution  # for test mail sending when address was changed


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    client = None

    def __init__(self, opts):
        self.logger = logging.getLogger(__name__)
        self.opts = opts
        #self.alarmDistr = alarmDistribution.alarmDistribution(self.opts)
        # Load database connection details
        try:
            with open(os.path.join('settings','Database_connectiondetails.txt'), 'r') as f:
                conn_details = eval(f.read())
        except Exception as e:
            self.logger.warning("Can not load database connection details. "
                                "Trying default details. Error %s" % e)
            conn_details = {'host' : 'localhost', 'port' : 13178,
                    'username' : 'doberman', 'password' : 'h5jlm42'}

        self._connect(**conn_details)
        # load config details
        self._config = self.getConfig()

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    @classmethod
    def _connect(cls, host, port, username, password):
        if cls.client:
            return
        cls.client = pymongo.MongoClient(host=host, port=port, username=username, password=password)

    def _check(self, db_name, collection_name):
        """
        Returns the requested collection and logs if the database/collection don't yet exist
        """
        if db_name not in self.client.list_database_names():
            self.logger.debug('Database %s doesn\'t exist yet, creating it...' % db_name)
        elif collection_name not in self.client[db_name].collection_names(False):
            self.logger.debug('Collection %s not in database %s, creating it...' % (collection_name, db_name))
            self.client[db_name].create_collection(collection_name)
        return self.client[db_name][collection_name]

    def insertIntoDatabase(self, db_name, collection_name, document):
        """
        Inserts document(s) into the specified database/collection
        """
        collection = self._check(db_name, collection_name)
        if isinstance(document, (list, tuple)):
            result = collection.insert_many(document)
            self.logger.debug('Inserted %i entries into %s/%s' % (len(result.inserted_ids), db_name,
                collection_name))
            return 0
        elif isinstance(document, dict):
            collection.insert_one(document)
            self.logger.debug('Inserted 1 entry into %s/%s' % (db_name, collection_name))
            return 0
        else:
            self.logger.error('Not sure what to do with %s type' % type(document))
            return -1

    def readFromDatabase(self, db_name, collection_name, cuts=None, onlyone=False, projection={'_id' : 0}):
        """
        Finds one or more documents that pass the specified cuts
        """
        collection = self._check(db_name,collection_name)
        if onlyone:
            return collection.find_one(cuts, projection)
        else:
            return collection.find(cuts, projection)

    def updateDatabase(self, db_name, collection_name, cuts={}, updates={}, onlyone=True):
        """
        Updates documents that meet pass the specified cuts
        """
        collection = self._check(db_name, collection_name)
        if onlyone:
            ret = collection.update_one(cuts, updates)
        else:
            ret = collection.update_many(cuts, updates)
        self.logger.debug('Updated %i documents in %s/%s' % (ret.modified_count, db_name, collection_name))
        return 0

    def deleteFromDatabase(self, db_name, collection_name=None, which_document=None):
        """
        Deletes a document, collection, or database
        """
        if collection_name:
            collection = self._check(db_name, collection_name)
            if which_document:  # remove document
                self.logger.debug('Removing document %s from %s/%s' % (
                    which_document, db_name, collection_name))
                ret = collection.remove(which_document)
                if ret['ok'] != 1:
                    self.logger.error('Document removal failed!')
                    return 1
            else:  # remove collection
                self.logger.info('Dropping collection %s from %s' % (collection_name, db_name))
                if not collection.drop():
                    self.logger.error('Collection removal failed!')
                    return 1
        else:  # remove database
            if which_document:
                self.logger.error('Do you know what you\'re doing?')
                return 2
            db = self.client[db_name]
            self.logger.info('Dropping database %s' % db_name)
            ret = db.dropDatabase()
            if ret['ok'] != 1:
                self.logger.error('Database removal failed!')
                return 1
        return 0

    def StoreCommand(self, command):
        controller, cmd = command.split(maxsplit=1)
        if self.insertIntoDatabase('logging', 'commands',
                {'name' : controller, 'command' : cmd}):
            self.logger.error('Could not store command %s!')
        return 0

    def refreshConfigBackup(self):
        """
        Writes the current config from the Database to the file configBackup.txt
        """
        try:
            with open(os.path.join('settings','configBackup.txt'), 'w') as f:
                f.write("# Backup file of the config table in DobermanDB. "
                        "Updated: %s\n" % str(datetime.datetime.now()))
                self.logger.info("Writing new config to configBackup.txt...")
                for _,controller in self._config.items():
                    f.write('%s\n#\n' % controller)
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
            with open(os.path.join('settings',filename), 'r') as f:
                self.logger.info("Reading config from %s..." % filename)
                configBackup = f.read()
        except Exception as e:
            self.logger.warning("Can not read from configBackup.txt. %s" % e)
            return -2
        if not configBackup:
            self.logger.warning("Can not read config from configBackup.txt. "
                                "File empty")
            return -2
        self.logger.info("Backup file dates from %s" %
                (configBackup.splitlines()[0].split(': ')[1]))
        configBackup = configBackup[1:]  # strips first line with date
        c_backup = {}
        for blob in configBackup.split('#')[:-1]:
            try:
                d = eval(blob)
            except Exception as e:
                self.logger.error('Error parsing config backup: %s' % e)
                return -1
            else:
                c_backup[d['name']] = d
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
            with open(os.path.join('settings','contactsBackup.txt'), 'w') as f:
                f.write("# Backup file of the contacts table in DobermanDB. "
                        "Updated: %s" % str(datetime.datetime.now()))
                for _,contact in self._contacts.items():
                        f.write("%s\n#\n" % contact)
        except Exception as e:
            self.logger.warning("Can not refresh contactsBackup.txt. Error %s." % e)
            return -1
        self.logger.info("Successfully refreshed contactsBackup.txt.")
        return 0

    def getContactsFromBackup(self, status=None):
        """
        Reads the contacts from the file contactsBackup.txt.
        Only use this if no connection to the database exists.
        """
        try:
            with open(os.path.join('settings','contactsBackup.txt'), 'r') as f:
                self.logger.info("Reading config from contactsBackup.txt...")
                contactsBackup = f.read()
        except Exception as e:
            self.logger.warning("Can not read from contactsBackup.txt. %s" % e)
            return -1
        if not contactsBackup:
            self.logger.warning("Can not read config from configBackup.txt. "
                                "File empty")
            return -1
        self.logger.info("Contacts backup file dates from %s" %
                (contactsBackup.splitlines()[0].split(": ")[1]))
        c_backup = {}
        contactsBackup = contactsBackup[1:]  # strips first line with date
        for blob in contactsBackup.split('#')[:-1]:
            try:
                c = eval(blob)
            except Exception as e:
                self.logger.error('Error parsing config backup: %s' % e)
                return -1
            else:
                c_backup[c['name']] = c
        return c_backup

    def addAlarmToHistory(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging','alarm_history',document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def addSettingToConfigHistory(self, controller):
        """
        Adds the current setting of a controller to the config history
        """
        if self.insertIntoDatabase("logging","config_hist",
                controller.update({'when' : datetime.datetime.now()})):
            self.logger.warning('Could not add %s to config history' % controller['name'])
            return 1
        return 0

    def readConfig(self, name='all'):
        """
        Reads the table config in the database.
        """
        if name == 'all':
            controller = self.readFromDatabase('config', 'controllers', onlyone=False)
        else:
            controller = self.readFromDatabase('config', 'controllers', cuts={'name' : name}, onlyone=True)

        if not controller:
            if name == 'all':
                self.logger.info("Config table empty.")
                return 'EMPTY'
            else:
                self.logger.warning("No controller with name '%s' "
                                    "found in DB" % str(name))
        elif controller == -1:
            self.logger.warning("Can not read from config table in DobermanDB. "
                                "Database interaction error.")
            return -1

        config_dict = {}
        if name=='all':
            # list of dicts
            for row in controller:
                controller_name = row['name']
                config_dict[controller_name] = row
            return config_dict
        else:
            return controller
        return config_dict

    def printParameterDescription(self):
        """
        This function prints all information for each parameter
        which should be entered in the config database table.
        """
        text = []
        text.append("Name: -- Name of your device. "
                    "Make sure your Plugin class is named the same.")
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
                    "device read the data and send it to Doberman. "
                    "Default = 5 seconds")
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
        existing_names = devices
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

        # Print current parameters and infos.
        print('\n' + 60 * '-' + '\n')
        print('The current parameters are:\n')
        for i,key in enumerate(controller.keys()):
            if i == int(len(controller)):
                print()
            print("{:>16}: {} ".format(key, controller[key]))
        print(60 * '-')
        print('Which parameter(s) do you want to change?')
        which = self.getUserInput('Parameter:', input_type=[str],be_in=controller.keys(),exceptions=['n'])
        changes = []
        while which != 'n':
            if which == 'status':
                text = 'Controller %s: Status (ON/OFF):' % name
                status = self.getUserInput(text, input_type=[str], be_in=['ON','OFF','n'])
                if status != 'n':
                    controller['status'] = status
                    changes.append(which)
            elif which == 'alarm_status':
                text = 'Controller %s: alarm status (ON/OFF, ON/OFF...):' % name
                val = self.getUserInput(text, input_type=[str], be_in=['ON','OFF'],
                        be_array=True,exceptions=['n'])
                if val != 'n':
                    controller[which] = self.adjustListLength(val, controller['number_of_data'], 'OFF', which)
                    changes.append(which)
            elif which in ['alarm_low', 'alarm_high', 'warning_low', 'warning_high']:
                text = 'Controller {name} {wh[1]} {wh[0]} level(s) (float(s)):'.format(
                        name=name,wh=which.split('_'))
                vals = self.getUserInput(text, input_type=[int, float], be_array=True, exceptions=['n'])
                if vals != 'n':
                    controller[which] = self.adjustListLength(vals, controller['number_of_data'], 0, which)
                    changes.append(which)
            elif which == 'readout_interval':
                text = 'Controller %s readout interval (int):' % name
                val = self.getUserInput(text, input_type=[int, float], limits=[1, 86400], exceptions=['n'])
                if val != 'n':
                    controller[which] = val
                    changes.append(which)
            elif which == 'alarm_recurrence':
                text = 'Controller %s alarm recurrence (# consecutive values past limits before issuing warning/alarm' % name
                val = self.getUserInput(text, input_type=[int], limits=[1,99], exceptions=['n'])
                if val != 'n':
                    controller[which] = self.adjustListLength(val, controller['number_of_data'], 1, which)
                    changes.append(which)
            else:
                print('Can\'t change %s here' % which)
            which = self.getUserInput('Parameter:', input_type=[str],be_in=list(controller.keys()),exceptions=['n'])

        if changes:
            updates = {'$set' : {key, controller[key]} for key in changes}
            if self.updateDatabase('config','controllers',cuts={'name' : name}, updates=updates):
                self.logger.error('Could not update controller %s' % name)

        print(60 * '-')
        print('New controller settings:')
        for i, key in enumerate(controller.keys()):
            if i == int(len(controller)):
                print()
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
        existing_names = list(self._config.keys())
        # Ask for controller to delete and confirmation.
        text = ("\nEnter the name of the controller you would like to remove "
                "from config:")
        name = self.getUserInput(text,
                                 input_type=[str],
                                 be_in=existing_names)
        text = ("Do you really want to remove %s from the config table? (y/n) "
                "THIS CANNOT BE UNDONE." % name)
        confirmation = self.getUserInput(text,
                                         input_type=[str],
                                         be_in=[y, Y, n, N])
        if confirmation not in [y, Y]:
            return 0
        # Delete from the database
        if self.deleteFromDatabase('config','controllers',{'name' : name}):
            self.logger.warning("Can not remove %s from config. Database "
                                "interaction error." % name)
            return -1
        self.logger.info(
            "Successfully removed %s from the config table." % name)
        # Ask for deleting data table as well.
        text = ("\nDo you also want to delete the data table of %s? (y/n)? "
                "All stored data will be lost." % (name))
        drop_table = self.getUserInput(text,
                                       input_type=[str],
                                       be_in=[y, Y, n, N])
        if drop_table not in [y, Y]:
            return 0
        # Delete data table in the database.
        if self.deleteFromDatabase('data', name):
            self.logger.warning(
                "Can not delete data from %s. Database interaction error." % name)
            return -1
        self.logger.info("Successfully deleted all data from %s." % name)

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
        self.deleteFromDatabase('config', collection_name='default_settings')
        default_settings = None
        # Fill with standard defaults:
        with open(os.path.join('settings','default_settings.txt'),'r') as f:
            default_settings = f.read()
        if not default_settings:
            self.logger.error('Could not read default settings from file!')
            return -1
        try:
            default_settings = eval(default_settings)
        except Exception as e:
            self.logger.error('Could not parse default settings: %s' % e)
            return -1
        if self.insertIntoDatabase('config','default_settings',default_settings):
            self.logger.error("Error recreating default_settings in database")
            return -1
        return 0

    def updateDefaultSettings(self):
        """
        Updates the default Doberman settings
        """
        settings = self.getDefaultSettings()
        if settings == -1:
            return -1
        q, Q = 'q', 'q'
        print("\nThe following Doberman settings are stored:")
        for k, v in settings.items():
            print('%s: %s' % (k, v))
        while True:
            text= ("\nEnter name of entry you would like to change or 'q' "
                   "to quit.")
            key = self.getUserInput(text,
                                    input_type=[str],
                                    be_in=list(settings.keys()),
                                    exceptions = [q, Q])
            if key in [q, Q]:
                break
            text = ("Enter new value for %s (%s)." % (user_input))
            if user_input == "loglevel":
                input_type = [int]
                be_in = [0, 10, 20, 30, 40, 50]
                be_array = False
            else:
                input_type = [int]
                be_in = None
                be_array = False
            value = self.getUserInput(text,
                                      input_type=input_type,
                                      be_in=be_in,
                                      be_array=be_array)
            if self.updateDatabase('config','default_settings',cuts={'parameter' : key},
                    update = {'$set' : {'value' : value}}):
                self.logger.error('Could not update %s' % key)
            else:
                self.logger.info("Updated %s." % key)
        print("New settings are:")
        newsettings = self.getDefaultSettings()
        for k,v in newsettings.items():
            print('%s: %s' % (k,v))
        return

    def getDefaultSettings(self, name=None):
        """
        Reads default Doberman settings from database.
        Returns a dict
        """
        cursor = self.readFromDatabase('config','default_settings')
        if cursor.count() == 0:
            self.logger.warning('Unable to read default settings')
            return -1
        settings = {}
        for row in cursor:
            if row['parameter'] == 'tty_update':
                settings[row['parameter']] = row['value']
            else:
                settings[row['parameter']] = int(row['value'])
        if not name:
            return settings
        else:
            try:
                settings = settings[name]
            except KeyError as e:
                self.logger.error("Can not read default setting %s: %s" % (name, e))
            except Exception as e:
                self.logger.error("Can not read defaut settings. %s" % e)
                return -1
        return settings

    def readContacts(self,status=None):
        """
        Reads contacts from database.
        """
        if not status:
            cursor = self.readFromDatabase('config','contacts')
        else:
            cursor = self.readFromDatabase('config','contacts', cuts={'status' : status})
        if cursor.count() == 0:
            self.logger.warning("No contacts found (with status %s)" % str(status))
            contacts = {}
        elif cursor == -1:
            self.logger.warning("Can not read from contact table in database. "
                                "Database interaction error.")
            return -1
        contacts = []
        for row in cursor:
            contacts.append(row)
        return contacts

    def getContacts(self, status=None):
        """
        Reads contacts. If status=None, all contacts are returned,
        otherwise only the ones with given status.
        If no connection to database, it reads from the backup.
        """
        contacts = self.readContacts(status)
        if not contacts or contacts == -1:
            contacts = self.getContactsFromBackup(status)
            if contacts == -1:
                return -1
        return contacts

    def updateContactsByKeyboard(self):
        """
        Update active contacts
        """
        contacts = self.getContacts()
        existing_numbers = list(map(str, list(range(len(contacts)))))
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
        for key in contacts:
            for f in contacts[key]:
                print('%s: %s' % f, contacts[key][f])
            print()
        print('\n' + 60 * '-' + '\n')

        # Change contact
        text = "Enter the number of the contact you would like to update"
        name = self.getUserInput(text,
                                 input_type=[str],
                                 be_in=existing_numbers)
        original_contact = contacts[list(contacts.keys())[int(name)]]
        # Status
        text = ("Enter new status of contact '%s' (or n for no change). "
                    "It can be 'ON' (all notifications), "
                    "'OFF' (no notifications), 'MAIL' (only by email), "
                    "'TEL' (only by phone)." % name)
        status = self.getUserInput(text,
                                    input_type=[str],
                                    be_in=['ON', 'OFF', 'MAIL', 'TEL', 'n'])
        if status != 'n':
            original_contact['status'] = status
            if self.updateDatabase('config', 'contacts', cuts={'name' : original_contact['name']},
                    update={'$set' : {'status' : status}}):
                self.logger.error()
                return -1
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

    def writeDataToDatabase(self, name, when, data, status):
        """
        Writes data to the database
        Status:
          0 = OK,
          -1 = no connection,
          -2 = No error status aviable (ok)
          1-9 = Warning
          >9 = Alarm
        """

        if self.insertIntoDatabase('data', name, {'when' : when, 'data' : data, 'status' : status}):
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % name)
            return -1
        if self.logger.getEffectiveLevel() > 15:
            self.logger.info("Stored %i values from %s" % (len(data), name))
        else:
            self.logger.debug("Stored values from %s: %s" % (name, data))
        return 0

    def getConfig(self, name=None):
        """
        This function retruns the config data.
        Controller format:
        {'name' : controller_name,
         'status' : 'ON'/'OFF',
         'alarm_status' : ['ON','OFF'],
         'warning_low' : [0.0, 0.0],
         'warning_high' : [1.0, 1.0],
         'alarm_low' : [0.0, 0.0],
         'alarm_high' : [1.0, 1.0],
         'readout_interval' : 5,
         'alarm_recurrence' : 10,
         'description' : ['one sensor', 'different sensor'],
         'number_of_data' : 2,
         'addresses' : {'serialID' : '2303',
                        'ttyUSB' : '-1'
                       },
         'additional_parameters' : ''
        }
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
        new_names = list(new_config.keys())
        old_names = list(old_config.keys())
        for name in old_names:
            if name not in new_names:
                new_config[name] = old_config[name].copy()
        return new_config

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
        existing_names = list(self.getConfig().keys())
        for key in all_settings:
            if key in existing_names:
                settings = all_settings[key]
                ret = self.updateDatabase('config','controllers', update={'$set' : settings},
                        cuts={'name' : key})
            else:
                ret = self.insertIntoDatabase('config','controllers', settings)
            if ret:
                self.logger.warning("Can not update config from file %s." % filename)
                raise IOError("Dababase interaction error!")
        return

