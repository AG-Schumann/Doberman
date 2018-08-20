#!/usr/bin/env python3
import logging
import datetime
import pymongo
import utils
import argparse
import os
dtnow = datetime.datetime.now


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Load database connection details
        try:
            conn_str = os.environ['DOBERMAN_CONN']
        except Exception as e:
            print("Can not load database connection details. Error %s" % e)
            raise

        self.client = None
        self._connect(conn_str)

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def _connect(self, conn_str):
        if self.client is not None:
            return
        self.client = pymongo.MongoClient(conn_str)

    def _check(self, db_name, collection_name):
        """
        Returns the requested collection and logs if the database/collection don't yet exist
        """
        if db_name not in self.client.list_database_names():
            self.logger.debug('Database %s doesn\'t exist yet, creating it...' % db_name)
        elif collection_name not in self.client[db_name].list_collection_names(False):
            self.logger.debug('Collection %s not in database %s, creating it...' % (collection_name, db_name))
            self.client[db_name].create_collection(collection_name)
            self.client[db_name][collection_name].create_index('when')
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
        if not ret.acknowledged:
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
        """
        Adds commands to the database
        """
        controller, cmd = command.split(maxsplit=1)
        coll = self._check('settings','controllers')
        if cmd == 'help':
            print('Accepted commands for %s:' % controller)
            print('start: sets status to "ON"')
            print('stop: shuts down the controller')
            print('sleep: sets status to "OFF" (but does not shut down)')
            print('restart: restarts the controller')
            print('runmode <runmode>: changes the active runmode')

            if controller in coll.distinct('name'):
                ctrl_cls = utils.FindPlugin(controller, ['.'])
                if not hasattr(ctrl_cls, 'accepted_commands'):
                    return
                for row in ctrl_cls.accepted_commands:
                    print(row)
            return
        print(f"Storing command '{cmd}' for {controller}")
        if controller == 'all':
            controllers = coll.distinct('name',{'online' : True})
        else:
            controllers = [controller]
        for ctrl in controllers:
            if self.insertIntoDatabase('logging', 'commands',
                {'name' : ctrl, 'command' : cmd, 'logged' : dtnow()}):
                print('Could not store command for %s!' % ctrl)
        return 0

    def logAlarm(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging','alarm_history',document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
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

    def getDefaultSettings(self, runmode=None, name=None):
        """
        Reads default Doberman settings from database.
        Returns a dict or the specified value
        """
        if runmode:
            doc = self.readFromDatabase('settings','runmodes',
                    {'mode' : runmode},onlyone=True)
            if name:
                return doc[name]
            return doc
        doc = self.readFromDatabase('settings','defaults', onlyone=True)
        if name:
            return doc[name]
        return doc

    def getContacts(self,status=None):
        """
        Reads contacts from database.
        """
        if not status:
            cuts = {'name' : {'$exists' : 1}}  # cuts the 'conn_details' doc
        elif status == 'sms':
            cuts={'status' : {'$in' : ['ON','SMS']}}
        elif status == 'email':
            cuts={'status' : {'$in' : ['ON','MAIL']}}
        collection = self._check('settings','contacts')
        if collection.count(cuts) == 0:
            self.logger.warning("No contacts found (with status %s)" % str(status))
            return []
        return [row for row in collection.find(cuts)]

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
          -1 = No connection to controller
          -2 = Could not communicate with controller
          -3 = Wrong number of data received
          -4 = Error parsing data
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

    def addOpmode(self):
        print('What is the name of this runmode?')
        name = input('>>>')
        print('What loglevel (default 20?')
        loglevel = utils.getUserInput('Loglevel', input_type=[int], be_in=range(10,60,10),
                exceptions=['n'])
        if loglevel == 'n':
            loglevel = 20
        print('Testrun (default 5)?')
        testrun = utils.getUserInput('Testrun', input_type=[int],exceptions=['n'])
        if testrun == 'n':
            testrun = 5
        print('Message timer (default 5)?')
        msg_time = utils.getUserInput('Message timer', input_type=[int], exceptions=['n'])
        if msg_time == 'n':
            msg_time = 5
        if self.insertIntoDatabase('settings','runmodes',{'mode' : name,
            'loglevel' : loglevel, 'testrun' : testrun, 'message_time' : msg_time}):
            print('Could not add runmode!')
        return

    def addContact(self):
        print('Contact name:')
        name = input('>>>')
        print('Contact sms')
        sms = input('>>>')
        print('Contact email')
        email = input('>>>')
        print('Contact status (ON,SMS,MAIL,OFF)')
        status = utils.getUserInput('Status', input_type[str], be_in=['ON','SMS','MAIL','OFF'], exceptions=['n'])
        if status == 'n':
            status = 'OFF'
        if self.insertIntoDatabase('settings','contacts',{'name' : name, 'sms' : sms,
            'email' : email, 'status' : status}):
            print('Could not add contact!')
        return

    def addController(self, filename):
        with open(filename, 'r') as f:
            try:
                d = eval(f.read())
            except Exception as e:
                print('Could not read file! Error: %s' % e)
            if self.insertIntoDatabase('settings','controllers',d):
                print('Could not add controller!')
        return

def main():
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n DobermanDB interface')

    db = DobermanDB()
    parser.add_argument('--update', action='store_true', default=False,
                        help='Update settings/contacts/etc')
    parser.add_argument('--command', nargs='+',
                        help='Issue a command to the system. Format: '
                            '<name> <command>. <command> == \'help\' prints '
                            'accepted commands for <name>')
    parser.add_argument('--add-runmode', action='store_true', default=False,
                        help='Add a new operation preset')
    parser.add_argument('--add-contact', action='store_true', default=False,
                        help='Add a new contact')
    parser.add_argument('--add-controller', default=None, type=str,
                        help='Specify a new controller config file to load')
    parser.add_argument('--running', action='store_true', default=False,
                        help='List currently running controllers')
    args = parser.parse_args()
    if args.command:
        db.StoreCommand(' '.join(args.command))
    if args.running:
        cursor = db.readFromDatabase('settings','controllers',{'online' : True})
        print('Currently running controllers:')
        print('Name : Status : Runmode')
        for row in cursor:
            runmode = row['runmode']
            status = row['status'][runmode]
            print('  %s: %s : %s' % (row['name'], status, runmode))
    try:
        if args.add_runmode:
            db.addOpmode()
        if args.add_contact:
            db.addContact()
        if args.add_controller:
            db.addController(args.add_controller)
        if args.update:
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
