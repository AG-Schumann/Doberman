#!/usr/bin/env python3
import logging
import datetime
import pymongo
import os.path
import utils


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    client = None

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Load database connection details
        try:
            with open(os.path.join('settings','Database_connectiondetails.txt'), 'r') as f:
                conn_details = eval(f.read())
        except Exception as e:
            print("Can not load database connection details. "
                                "Trying default details. Error %s" % e)
            conn_details = {'host' : 'localhost', 'port' : 13178,
                    'username' : 'doberman', 'password' : 'h5jlm42'}

        self._connect(**conn_details)

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
            if len(result.inserted_ids) != len(document):
                self.logger.error('Inserted %i entries instead of %i into %/%s' % (
                    len(result.inserted_ids), len(document), db_name, collection_name))
                return -1
            return 0
        elif isinstance(document, dict):
            result = collection.insert_one(document)
            if result.acknowledged:
                return 0
            else:
                return 1
        else:
            self.logger.error('Not sure what to do with %s type' % type(document))
            return -1

    def readFromDatabase(self, db_name, collection_name, cuts={}, projection={'_id' : 0}):
        """
        Finds one or more documents that pass the specified cuts
        """
        collection = self._check(db_name,collection_name)
        return collection.find(cuts, projection)

    def updateDatabase(self, db_name, collection_name, cuts, updates):
        """
        Updates documents that meet pass the specified cuts
        """
        collection = self._check(db_name, collection_name)
        ret = collection.update_many(cuts, updates)
        if ret['ok'] != 1:
            return 1
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

    def logAlarm(self, document):
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

    def ControllerSettings(self, name='all'):
        """
        Reads the settings in the database.
        """
        if name == 'all':
            cursor = self.readFromDatabase('settings', 'controllers')
        else:
            cursor = self.readFromDatabase('settings', 'controllers', cuts={'name' : name})

        if not cursor.count():  # FIXME count is deprecated
            if name == 'all':
                self.logger.info("Config table empty.")
                return 'EMPTY'
            else:
                self.logger.warning("No controller with name '%s' "
                                    "found in DB" % str(name))

        config_dict = {}
        if name=='all':
            config_dict = {row['name'] : row for row in cursor}
            return config_dict
        else:
            return cursor[0]

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
        for sentence in text:
            print("\n - " + sentence)

    def updateController(self):
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
        print('\n' + 60 * '-' + '\n Choose the controller you want to change. ')
        controllers = self.ControllerSettings()
        devices = list(controllers.keys())
        for number, controller in enumerate(devices):
            print("%s:\t%s" % (str(number), controller))
        # Enter name to find controller
        existing_names = devices
        existing_numbers = list(map(str, range(len(existing_names))))
        existing_devices = existing_names + existing_numbers
        text = "\nEnter controller number or alternatively its name:"
        name = utils.getUserInput(text, input_type=[str],
                                 be_in=existing_devices)
        try:
            controller = [name]
        except KeyError:
            name = devices[int(name)]
            controller = controllers[name]

        # Print current parameters and infos.
        print('\n' + 60 * '-' + '\n')
        print('The current parameters are:\n')
        for i,key in enumerate(controller.keys()):
            if i == int(len(controller)/2):
                print()
            print("{:>16}: {} ".format(key, controller[key]))
        print(60 * '-')
        print('Which parameter(s) do you want to change?')
        which = utils.getUserInput('Parameter:', input_type=[str],be_in=controller.keys(),exceptions=['n'])
        changes = []
        while which != 'n':
            if which == 'status':
                text = 'Controller %s: Status (ON/OFF):' % name
                status = utils.getUserInput(text, input_type=[str], be_in=['ON','OFF','n'])
                if status != 'n':
                    controller['status'] = status
                    changes.append(which)
            elif which == 'alarm_status':
                text = 'Controller %s: alarm status (ON/OFF, ON/OFF...):' % name
                val = utils.getUserInput(text, input_type=[str], be_in=['ON','OFF'],
                        be_array=True,exceptions=['n'])
                if val != 'n':
                    controller[which] = utils.adjustListLength(val, controller['number_of_data'], 'OFF', which)
                    changes.append(which)
            elif which in ['alarm_low', 'alarm_high', 'warning_low', 'warning_high']:
                text = 'Controller {name} {wh[1]} {wh[0]} level(s) (float(s)):'.format(
                        name=name,wh=which.split('_'))
                vals = utils.getUserInput(text, input_type=[int, float], be_array=True, exceptions=['n'])
                if vals != 'n':
                    controller[which] = utils.adjustListLength(vals, controller['number_of_data'], 0, which)
                    changes.append(which)
            elif which == 'readout_interval':
                text = 'Controller %s readout interval (int):' % name
                val = utils.getUserInput(text, input_type[int, float], limits=[1, 86400], exceptions=['n'])
                if val != 'n':
                    controller[which] = val
                    changes.append(which)
            elif which == 'alarm_recurrence':
                text = 'Controller %s alarm recurrence (# consecutive values past limits before issuing warning/alarm' % name
                val = utils.getUserInput(text, input_type[int], limits=[1,99], exceptions=['n'])
                if val != 'n':
                    controller[which] = utils.adjustListLength(val, controller['number_of_data'], 1, which)
                    changes.append(which)
            else:
                print('Can\'t change %s here' % which)
            which = utils.getUserInput('Parameter:', input_type=[str],be_in=controller.keys(),exceptions=['n'])

        if changes:
            updates = {'$set' : {key: controller[key] for key in changes}}
            if self.updateDatabase('settings','controllers',cuts={'name' : name}, updates=updates):
                self.logger.error('Could not update controller %s' % name)

        print(60 * '-')
        print('New controller settings:')
        for i, key in enumerate(controller.keys()):
            if i == int(len(controller)):
                print()
            print("{:>16}: {}".format(key, str(controller[key])))
        print(60 * '-')
        self.addSettingToConfigHistory(controller)

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
        if self.deleteFromDatabase('settings','controllers',{'name' : name}):
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
        self.deleteFromDatabase('settings', collection_name='defaults')
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
        if self.insertIntoDatabase('settings','defaults',default_settings):
            self.logger.error("Error recreating default_settings in database")
            return -1
        return 0
>>>>>>> ebefae6d8063fc7f9fb9e1a8881b76338116be55

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
            key = utils.getUserInput(text,
                                    input_type=[str],
                                    be_in=list(settings.keys()),
                                    exceptions = [q, Q])
            if key in [q, Q]:
                break
            if key == 'tty_update':
                print('Can\'t update that here!')
                continue
            text = ("Enter new value for %s:" % (user_input))
            if user_input == "loglevel":
                input_type = [int]
                be_in = [0, 10, 20, 30, 40, 50]
                be_array = False
            else:
                input_type = [int]
                be_in = None
                be_array = False
            value = utils.getUserInput(text,
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
        Returns a dict or the specified value
        """
        cursor = self.readFromDatabase('settings','defaults')
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

    def getContacts(self,status=None):
        """
        Reads contacts from database.
        """
        if not status:
            cursor = self.readFromDatabase('settings','contacts')
        else:
            cursor = self.readFromDatabase('settings','contacts', cuts={'status' : status})
        if cursor.count() == 0:
            self.logger.warning("No contacts found (with status %s)" % str(status))
            contacts = {}
        contacts = []
        for row in cursor:
            contacts.append(row)
        return contacts

    def updateContacts(self):
        """
        Update active contacts
        """
        contacts = self.getContacts()
        existing_numbers = list(map(str, range(len(contacts))))
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
        name = utils.getUserInput(text,
                                 input_type=[str],
                                 be_in=existing_numbers)
        original_contact = contacts[list(contacts.keys())[int(name)]]
        # Status
        text = ("Enter new status of contact '%s' (or n for no change). "
                    "It can be 'ON' (all notifications), "
                    "'OFF' (no notifications), 'MAIL' (only by email), "
                    "'TEL' (only by phone)." % name)
        status = utils.getUserInput(text,
                                       input_type=[str],
                                       be_in=['ON', 'OFF', 'MAIL', 'TEL', 'n'])
        if status != 'n':
            original_contact['status'] = status
            if self.updateDatabase('settings', 'contacts', cuts={'name' : original_contact['name']},
                    update={'$set' : {'status' : status}}):
                self.logger.error()
                return -1
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

        ret = self.insertIntoDatabase('data', name, {'when' : when, 'data' : data, 'status' : status})
        if ret:
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % name)
            return -1
        self.logger.debug('Wrote data from %s' % name)
        return 0

