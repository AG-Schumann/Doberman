#!/usr/bin/env python3
import logging
import datetime
import pymongo
import os.path
import utils
import argparse


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    client = None
    _access_counter = 0

    def __init__(self):
        DobermanDB._access_counter += 1
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
        DobermanDB._access_counter -= 1
        if DobermanDB._access_counter == 0:
            DobermanDB.client.close()
            DobermanDB.client = None

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    @classmethod
    def _connect(cls, **kwargs):
        if cls.client:
            return
        cls.client = pymongo.MongoClient(**kwargs)

    def _check(self, db_name, collection_name):
        """
        Returns the requested collection and logs if the database/collection don't yet exist
        """
        if db_name not in DobermanDB.client.list_database_names():
            self.logger.debug('Database %s doesn\'t exist yet, creating it...' % db_name)
        elif collection_name not in DobermanDB.client[db_name].collection_names(False):
            self.logger.debug('Collection %s not in database %s, creating it...' % (collection_name, db_name))
            DobermanDB.client[db_name].create_collection(collection_name)
        return DobermanDB.client[db_name][collection_name]

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

    def readFromDatabase(self, db_name, collection_name, cuts={}, projection={'_id' : 0}, onlyone = False):
        """
        Finds one or more documents that pass the specified cuts
        """
        collection = self._check(db_name,collection_name)
        if onlyone:
            return collection.find_one(cuts, projection)
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
            db = DobermanDB.client[db_name]
            self.logger.info('Dropping database %s' % db_name)
            ret = db.dropDatabase()
            if ret['ok'] != 1:
                self.logger.error('Database removal failed!')
                return 1
        return 0

    def StoreCommand(self, command):
        controller, cmd = command.split(maxsplit=1)
        if self.insertIntoDatabase('logging', 'commands',
                {'name' : controller, 'command' : cmd,
                    'logged' : datetime.datetime.now()}):
            self.logger.error('Could not store command for %s!' % controller)
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
            return self.readFromDatabase('settings', 'controllers', cuts={'name' : name}, onlyone=True)

        return {row['name'] : row for row in cursor}

    def printParameterDescription(self):
        """
        This function prints all information for each parameter
        which should be entered in the config database table.
        """
        print("Name: -- Name of your device. ")
        print("Status: -- ON/OFF: is your instrument (or plugin) turned on or not.")
        print("Alarm Status: -- ON/OFF,...: ")
        print("Lower Warning Level -- : Float,...: ")
        print("Higher Warning Level: -- Float,...: ")
        print("Lower Alarm Level: --  Float,...: ")
        print("Higher Alarm Level: -- Float,...: ")
        print("Readout interval: -- How often (in seconds) should your "
                    "device read the data and send it to Doberman. ")
        print("Alarm recurrence: -- How many times in a row has the "
                    "data to be out of the warning/alarm limits before an "
                    "alarm/warning is sent.")
        print("Run mode: which settings to use")

    def updateController(self):
        n = 'n'
        print('\n' + 60 * '-' + '\nUpdate plugin settings. '
              'The following parameters can be changed:\n')
        self.printParameterDescription()
        print('\n' + 60 * '-')
        print('  - No string signs (") needed.\n  '
              '- Split arrays with comma (no spaces after it), '
              'no brackets needed!  \n  '
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
        keys1 = ['runmode','readout_interval']
        keys2 = ['status','alarm_status','alarm_low','alarm_high','warning_low','warning_high']
        for k in keys1:
            print('{:>16}: {}'.format(k, controller[k]))
        print()
        for key in keys2:
            print("{:>16}: {} ".format(k, controller[k][controller['runmode']]))
        print(60 * '-')
        print('Which parameter(s) do you want to change?')
        which = utils.getUserInput('Parameter:', input_type=[str],be_in=key1+keys2,exceptions=['n'])
        while which != 'n':
            if which == 'status':
                text = 'Controller %s: Status (ON/OFF):' % name
                status = utils.getUserInput(text, input_type=[str], be_in=['ON','OFF','n'])
                if status != 'n':
                    self.updateDatabase('settings','controllers', {'name' : name},
                            {'$set' : {'%s.%s' % (which,controller['runmode']) : status}})
            elif which == 'alarm_status':
                text = 'Controller %s: alarm status (ON/OFF, ON/OFF...):' % name
                val = utils.getUserInput(text, input_type=[str], be_in=['ON','OFF'],
                        be_array=True,exceptions=['n'])
                if val != 'n':
                    val = utils.adjustListLength(val, controller['number_of_data'], 'OFF', which)
                    self.updateDatabase('settings','controllers', {'name' : name},
                            {'$set' : {'%s.%s' % (which,controller['runmode']) : val}})
            elif which in ['alarm_low', 'alarm_high', 'warning_low', 'warning_high']:
                text = 'Controller {name} {wh[1]} {wh[0]} level(s) (float(s)):'.format(
                        name=name,wh=which.split('_'))
                vals = utils.getUserInput(text, input_type=[int, float], be_array=True, exceptions=['n'])
                if vals != 'n':
                    vals = utils.adjustListLength(vals, controller['number_of_data'], 0, which)
                    self.updateDatabase('settings','controllers', {'name' : name},
                            {'$set' : {'%s.%s' % (which, controller['runmode']) : vals}})
            elif which == 'readout_interval':
                text = 'Controller %s readout interval (int):' % name
                val = utils.getUserInput(text, input_type=[int, float], limits=[1, 86400], exceptions=['n'])
                if val != 'n':
                    self.updateDatabase('settings','controller',{'name' : name},
                            {'$set' : {which : val}})
                    controller[which] = val
                    changes.append(which)
            elif which == 'alarm_recurrence':
                text = 'Controller %s alarm recurrence (# consecutive values past limits before issuing warning/alarm):' % name
                val = utils.getUserInput(text, input_type=[int], limits=[1,99], exceptions=['n'])
                if val != 'n':
                    val = utils.adjustListLength(val, controller['number_of_data'], 1, which)
                    self.updateDatabase('settings','controllers',{'name' : name},
                            {'$set' : {'%s.%s' % (which, controller['runmode']) : val}})
                    changes.append(which)
            elif which == 'runmode':
                text = 'Runmode:'
                val = utils.getUserInput(text, input_type=[str], exceptions=['n'], be_in=['default','testing','recovery'])
                if val != 'n':
                    self.updateDatabase('settings','controllers',{'name' : name},
                            {'$set' : {which : val}})
            else:
                print('Can\'t change %s here' % which)
            which = utils.getUserInput('Parameter:', input_type=[str],be_in=keys1+keys2,exceptions=['n'])

        print(60 * '-')
        print('New controller settings:')
        controller = self.readFromDatabase('settings','controllers',{'name' : name}, onlyone=True)
        for k in keys1:
            print('{:>16}: {}'.format(k, controller[k]))
        print()
        for key in keys2:
            print("{:>16}: {} ".format(k, controller[k][controller['runmode']]))
        #self.addSettingToConfigHistory(controller)

    def updateSettings(self):
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

    def getDefaultSettings(self, opmode=None, name=None):
        """
        Reads default Doberman settings from database.
        Returns a dict or the specified value
        """
        if opmode:
            doc = self.readFromDatabase('settings','opmodes',{'mode' : opmode})
            if name:
                return doc['name']
            return doc
        cursor = self.readFromDatabase('settings','opmodes')
        return {doc['mode'] : doc for doc in cursor}

    def getContacts(self,status=None):
        """
        Reads contacts from database.
        """
        if not status:
            cursor = self.readFromDatabase('settings','contacts')
        elif status == 'sms':
            cursor = self.readFromDatabase('settings','contacts',
                    cuts={'status' : {'$in' : ['ON','SMS']}})
        elif status == 'email':
            cursor = self.readFromDatabase('settings','contacts',
                    cuts={'status' : {'$in' : ['ON','MAIL']}})
        if cursor.count() == 0:
            self.logger.warning("No contacts found (with status %s)" % str(status))
            return []
        return [row for row in cursor]

    def updateContacts(self):
        """
        Update active contacts
        """
        contacts = self.getContacts()
        existing_numbers = list(map(str, range(len(contacts))))
        # Print informations
        print('\n' + 60 * '-' + '\n')
        print('  - No string signs (") needed.\n  '
              '- Enter n for no change')
        print('\n' + 60 * '-' +
              '\n  Saved contacts are:\n  (Name, Status, Email, Phone)\n')
        if contacts == -1:
            self.logger.error("Could not load contacts.")
            return -1
        for key in contacts:
            for field in contacts[key]:
                print('%s: %s' % field, contacts[key][field])
            print()
        print('\n' + 60 * '-' + '\n')

        # Change contact
        text = "Enter the number of the contact you would like to update"
        name = utils.getUserInput(text,
                                 input_type=[str],
                                 be_in=existing_numbers)
        contact = contacts[list(contacts.keys())[int(name)]]
        # Status
        text = ("Enter new status of contact '%s' (or n for no change). "
                    "It can be 'ON' (all notifications), "
                    "'OFF' (no notifications), 'MAIL' (only by email), "
                    "'SMS' (only by phone)." % name)
        status = utils.getUserInput(text, input_type=[str],
                                       be_in=['ON', 'OFF', 'MAIL', 'SMS', 'n'])
        if status != 'n':
            if self.updateDatabase('settings','contacts',
                    cuts={'name' : contact['name']},
                    update={'$set' : {'status' : status}}):
                self.logger.error('Could not update contact!')
                return -1
        return 0

    def writeDataToDatabase(self, name, when, data, status):
        """
        Writes data to the database
        Status:
          0 = OK,
          -1 = no connection,
          -2 = No error status aviable (ok)
          1 = Warning
          2 = Alarm
        """
        ret = self.insertIntoDatabase('data', name,
                {'when' : when, 'data' : data, 'status' : status})
        if ret:
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % name)
            return -1
        self.logger.debug('Wrote data from %s' % name)
        return 0

    def askForUpdates(self):
        which = ''
        to_quit = ['q','Q','n']
        while which not in to_quit:
            print('What do you want to update?')
            print('contacts | controllers | settings')
            print('(use q, Q, or n to quit)')
            which = input('>>>')
            if which == 'contacts':
                self.updateContacts()
            elif which == 'controllers':
                self.updateController()
            elif which == 'settings':
                self.updateSettings()
            elif which not in to_quit:
                print('Invalid input: %s' % which)

def main():
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n DobermanDB interface')

    db = DobermanDB()
    parser.add_argument('--update', action='store_true', default=False,
                        help='Update settings/contacts/etc')
    parser.add_argument('-- command', action='store_true', default=False,
                        help='Issue a command to the system. Format: '
                            '<name> <command>', nargs='+')
    parser.add_argument('--add-opmode', action='store_true', default=False,
                        help='Add a new operation preset')
    parser.add_argument('--add-contact', action='store_true', default=False,
                        help='Add a new contact')
    parser.add_argument('--add-controller', default=None, type=str,
                        help='Specify a new controller config file to load')
    args = parser.parse_args()
    if args.command:
        db.StoreCommand(' '.join(args.command))
    if args.update:
        try:
            db.askForUpdates()
        except KeyboardInterrupt:
            print('Interrupted!')
        except Exception as e:
            print('Exception! %s' % e)

    print('Ciao!')
    db.close()
    return

if __name__ == '__main__':
    main()
