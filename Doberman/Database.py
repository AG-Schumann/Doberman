import Doberman
import datetime
from socket import getfqdn
from functools import partial
import time
try:
    from kafka import KafkaProducer
    has_kafka=True
except ImportError:
    has_kafka=False


dtnow = datetime.datetime.utcnow

__all__ = 'Database'.split()

class FakeKafka(object):
    """
    Something for testing on platforms without the Kafka driver
    """
    def send(self, *args, **kwargs):
        pass

    def close(self, *args, **kwargs):
        pass

class Database(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self, mongo_client, loglevel='INFO', experiment_name=None):
        self.client = mongo_client
        self.logger = Doberman.utils.Logger(name='Database', db=self, loglevel=loglevel)
        self.hostname = getfqdn()
        self.experiment_name=experiment_name
        if has_kafka:
            self.has_kafka = True
            kafka_cfg = self.readFromDatabase('settings', 'experiment_config', {'name' : 'kafka'}, onlyone=True)
            self.logger.debug(f" Trying to connect to Kafka: {kafka_cfg['bootstrap_servers']}")
            try: 
                self.kafka = KafkaProducer(bootstrap_servers=kafka_cfg['bootstrap_servers'],
                        value_serializer=partial(bytes, encoding='utf-8'))
            except Exception as e:

                self.logger.debug(f"Connection to Kafka couldn't be established: {e}. I will run in independent mode")
                self.kafka = FakeKafka()
                self.has_kafka = False
        else:
            self.logger.debug(f"Could not import KafkaProducer. I will run in independent mode.")
            self.kafka = FakeKafka()
            self.has_kafka = False

    def close(self):
        self.kafka.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def _check(self, db_name, collection_name):
        """
        Returns the requested collection and logs if the database or
        collection don't yet exist. If the collection must be
        created, it adds an index onto the 'when' field (used for logs,
        alarms, data, etc)

        :param db_name: the name of the database
        :param collection_name: the name of the collections
        :returns collection instance of the requested collection.
        """
        if not hasattr(self, 'experiment_name'):
            raise ValueError('I don\'t know what experiment to look for')
        db_name = self.experiment_name + '_' + db_name
        if collection_name == 'hosts':
            db_name = 'common'
        return self.client[db_name][collection_name]

    def insertIntoDatabase(self, db_name, collection_name, document, **kwargs):
        """
        Inserts document(s) into the specified database/collection

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param document: a dictionary or iterable of dictionaries
        :param **kwargs: any keyword args, passed to collection.insert_(one|many)
        :returns 0 if successful, -1 if a multiple insert failed, -2 if a single
        insert failed, or 1 if `document` has the wrong type
        """
        collection = self._check(db_name, collection_name)
        if isinstance(document, (list, tuple)):
            result = collection.insert_many(document, **kwargs)
            if len(result.inserted_ids) != len(document):
                self.logger.error('Inserted %i entries instead of %i into %s/%s' % (
                    len(result.inserted_ids), len(document), db_name, collection_name))
                return -1
            return 0
        elif isinstance(document, dict):
            result = collection.insert_one(document, **kwargs)
            if result.acknowledged:
                return 0
            else:
                return -2
        else:
            self.logger.error('Not sure what to do with %s type' % type(document))
            return 1

    def readFromDatabase(self, db_name, collection_name, cuts={}, onlyone = False, **kwargs):
        """
        Finds one or more documents that pass the specified cuts

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: dictionary of the query to apply. Default {}
        :param onlyone: bool, if only one document is requested
        :param **kwargs: keyword args passed to collection.find. The 'sort' kwarg
        is handled separately because otherwise it doesn't do anything
        :returns document if onlyone=True else cursor
        """
        collection = self._check(db_name, collection_name)
        cursor = collection.find(cuts, **kwargs)
        if 'sort' in kwargs:
            cursor.sort(kwargs['sort'])
        if onlyone:
            for doc in cursor:
                return doc
        else:
            return cursor

    def updateDatabase(self, db_name, collection_name, cuts, updates, **kwargs):
        """
        Updates documents that meet pass the specified cuts

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: the dictionary specifying the query
        :param updates: the dictionary specifying the desired changes
        :param **kwargs: keyword args passed to collection.update_many
        :returns 0 if successful, 1 if not
        """
        collection = self._check(db_name, collection_name)
        ret = collection.update_many(cuts, updates, **kwargs)
        if not ret.acknowledged:
            return 1
        return 0

    def DeleteDocuments(self, db_name, collection_name, cuts):
        """
        Deletes documents from the specified collection

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: dictionary specifying the query
        :returns None
        """
        collection = self._check(db_name, collection_name)
        collection.delete_many(cuts)

    def DeleteAlarm(self, reading_name, alarm_type):
        """
        Delete alarm of specific type from a reading
        :param reading_name: name of the reading
        :param alarm_type: alarm type to be removed
        """
        self.updateDatabase('settings', 'readings', {'name' : reading_name},
                {'$pull': {'alarms': {'type': alarm_type}}}) 
    def UpdateAlarm(self, reading_name, alarm_doc):
        alarm_type = alarm_doc['type']
        self.DeleteAlarm(reading_name, alarm_type)
        self.updateDatabase('settings', 'readings', {'name' : reading_name},
                {'$push': {'alarms': alarm_doc}})

    def Distinct(self, db_name, collection_name, field, cuts={}, **kwargs):
        """
        Transfer function for collection.distinct
        """
        return self._check(db_name, collection_name).distinct(field, cuts, **kwargs)

    def Count(self, db_name, collection_name, cuts, **kwargs):
        """
        Transfer function for collection.count/count_documents
        """
        return self._check(db_name, collection_name).count_documents(cuts, **kwargs)

    def FindOneAndUpdate(self, db_name, collection_name, cuts, updates, **kwargs):
        """
        Finds one document and applies updates. A bit of a special implementation so
        the 'sort' kwarg will actually do something

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: a dictionary specifying the query
        :param updates: a dictionary specifying the updates
        :**kwargs: keyword args passed to readFromDatabase
        :returns document
        """
        doc = self.readFromDatabase(db_name, collection_name, cuts, onlyone=True, **kwargs)
        if doc is not None:
            self.updateDatabase(db_name, collection_name, {'_id' : doc['_id']}, updates)
        return doc

    def FindCommand(self, name):
        """
        Finds the oldest unacknowledged command for the specified entity
        and updates it as acknowledged. Deletes command documents used in
        the feedback subsystem

        :param name: the entity to find a command for
        :returns command document
        """
        now = dtnow()
        doc = self.FindOneAndUpdate('logging', 'commands',
                cuts={'name' : name,
                      'acknowledged' : {'$exists' : 0},
                      'logged' : {'$lte' : now}},
                updates={'$set' : {'acknowledged' : now}},
                sort=[('logged', 1)])
        if doc and 'by' in doc and doc['by'] == 'feedback':
            self.DeleteDocuments('logging', 'commands', {'_id' : doc['_id']})
        return doc

    def LogCommand(self, doc):
        """
        """
        if 'logged' not in doc:
            doc['logged'] = dtnow()
        self.insertIntoDatabase('logging', 'commands', doc)

    def getMessageProtocols(self, level):
        """
        Gets message protocols for the specified alarm level. If none are found,
        takes those from the next lowest level.

        :param level: which alarm level is in question (0, 1, etc)
        :returns: list of message protocols to use
        """
        doc = self.readFromDatabase('settings', 'alarm_config',
                {'level' : level}, onlyone=True)
        if doc is None:
            self.logger.error(('No message protocols for alarm level %i! '
                'Defaulting to next lowest level' % level))
            doc = self.readFromDatabase('settings', 'alarm_config',
                    {'level' : {'$lte' : level}}, onlyone=True,
                    sort=[('level', -1)])
        return doc['protocols']

    def getContactAddresses(self, level):
        """
        Returns a list of addresses to contact at 'level' who are currently on shift,
            defined as when the function is called

        :param level: which alarm level the message will be sent at
        :returns dict, keys = message protocols, values = list of addresses
        """
        protocols = self.getMessageProtocols(level)
        ret = {k : [] for k in protocols}
        now = datetime.datetime.now()  # no UTC here, we want local time
        shifters = self.readFromDatabase('settings', 'shifts',
                {'start' : {'$lte' : now}, 'end' : {'$gte' : now}},
                onlyone=True)['shifters']
        for doc in self.readFromDatabase('settings', 'contacts',
                    {'name' : {'$in' : shifters}}):
            for p in protocols:
                ret[p].append(doc[p])
        return ret
    
    def GetHeartbeat(self, host=None, sensor=None):
        if host is not None:
            cuts = {'hostname' : host}
            coll = 'hosts'
        elif sensor is not None:
            cuts = {'name': sensor}
            coll = 'sensors'
        doc = self.readFromDatabase('settings', coll, cuts=cuts, onlyone=True)
        return doc['heartbeat']

    def UpdateHeartbeat(self, host=None, sensor=None):
        """
        Heartbeats the specified sensor or host
        """
        if host is not None:
            cuts = {'hostname' : host}
            coll = 'hosts'
        elif sensor is not None:
            cuts = {'name' : sensor}
            coll = 'sensors'
        self.updateDatabase('settings', coll, cuts=cuts,
                    updates={'$set' : {'heartbeat' : dtnow()}})
        return
    
    def LogAlarm(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging', 'alarm_history', document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def LogUpdate(self, **kwargs):
        """
        Logs changes submitted from the website
        """
        self.insertIntoDatabase('logging', 'updates', kwargs)
        return

    def GetSensorSetting(self, name, field=None):
        """
        Gets a specific setting from one sensor

        :param sensor_name: the name of the sensor
        :param field: the field you want
        :returns: the value of the named field
        """
        doc = self.readFromDatabase('settings', 'sensors', cuts={'name' : name},
                onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def SetSensorSetting(self, name, field, value):
        """
        Updates the setting from one sensor

        :param name: the name of the sensor
        :param field: the specific field to update
        :param value: the new value
        """
        self.updateDatabase('settings', 'sensors', cuts={'name' : name},
                updates = {'$set' : {field : value}})
        return

    def GetReadingSetting(self, sensor=None, name=None, field=None):
        """
        Gets the document from one reading

        :param sensor: the name of the sensor
        :param name: the name of the reading
        :returns: reading document
        """
        doc = self.readFromDatabase('settings', 'readings',
                cuts={'sensor' : sensor, 'name' : name}, onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def SetReadingSetting(self, sensor=None, name=None, field=None, value=None):
        """
        Updates a parameter for a reading, used only by the web interface

        :param sensor: the name of the sensor
        :param name: the name of the reading
        :param field: the specific field to update
        :param value: the new value
        """
        self.updateDatabase('settings', 'readings',
                cuts={'sensor' : sensor, 'name' : name},
                updates={'$set' : {field : value}})
        return

    def GetRunmodeSetting(self, runmode=None, field=None):
        """
        Reads default Doberman settings from database.

        :param runmode: the runmode to get settings for
        :param field: the name of the setting
        :returns: the setting dictionary if name=None, otherwise the specific field
        """
        doc = self.readFromDatabase('settings', 'runmodes',
                    {'mode' : runmode}, onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def GetHostSetting(self, host=None, field=None):
        """
        Gets the setting document of the specified host
        """
        if host is None:
            host = self.hostname
        doc = self.readFromDatabase('settings', 'hosts', {'hostname' : host},
                onlyone=True)
        if field is not None:
            return doc[field]
        return doc
    
    def SetHostSetting(self, host=None, **kwargs):
        """
        Updates the setting document of the specified host. Kwargs should be one
        of the Mongo commands (set, unset, push, pull) without the $ char.
        Ex: set={field:value}
        """
        if host is None:
            host = self.hostname
        self.updateDatabase('settings', 'hosts', {'hostname' : host},
                updates={f'${k}'  : v for k, v in kwargs.items()})
        return
    
    def GetUnmonitoredSensors(self):
        """
        Returns list of sensors that are not in 'default' of e.g. not read out by any host
        """
        all_sensors = self.Distinct('settings', 'sensors', 'name')
        hosts = self.Distinct('common', 'hosts', 'hostname')
        monitored = []
        for host in hosts:
            monitored.extend(self.GetHostSetting(host, 'default'))
        return list(set(all_sensors) - set(monitored))

    def GetKafka(self, topic):
        """
        Returns a setup kafka producer to whoever wants it
        """
        return partial(self.kafka.send, topic=f'{self.experiment_name}_{topic}')

    def GetCurrentStatus_old(self):
        """
        Gives a snapshot of the current system status
        """
        status = {}
        now = dtnow()
        for sensor_doc in self.readFromDatabase('settings', 'sensors'):
            sensor_name = sensor_doc['name']
            if 'Test' in sensor_name:
                continue
            status[sensor_name] = {
                    'last_heartbeat' : (now - sensor_doc['heartbeat']).total_seconds(),
                    'readings' : {}
                    }
            for reading_name in sensor_doc['readings']:
                reading_doc = self.GetReadingSetting(sensor_name, reading_name)
                status[sensor_name]['readings'][reading_name] = {
                        'description' : reading_doc['description'],
                        'status' : reading_doc['status'],
                    }
                if reading_doc['status'] == 'online':
                    status[sensor_name]['readings'][reading_name]['runmode'] = reading_doc['runmode'],
                    data_doc = self.readFromDatabase('data', sensor_name,
                                cuts={reading_name : {'$exists' : 1}},
                                sort=[('_id', -1)], onlyone=True)
                    if data_doc is None:
                        continue
                    status[sensor_name]['readings'][reading_name]['last_value'] = data_doc[reading_name]
                    doc_time = int(str(data_doc['_id'])[:8], 16)
                    status[sensor_name]['readings'][reading_name]['last_time'] = time.time() - doc_time
        return status

    def GetCurrentStatus(self):
        """
        Gives a snapshot of the current system status
        """
        status = {}
        now = dtnow()
        for host_doc in self.readFromDatabase('common', 'hosts'):
            hostname = host_doc['hostname']
            status[hostname] = {
                    'status' : host_doc['status'],
                    'last_heartbeat' : (now - host_doc['heartbeat']).total_seconds(),
                    'sensors' : {}
                    }
            for sensor_name in host_doc['default']:
                try :
                    sensor_doc = self.readFromDatabase('settings', 'sensors', cuts={'name' : sensor_name}, onlyone = True)
                    status[hostname]['sensors'][sensor_name] = {
                        'last_heartbeat' : (now - sensor_doc['heartbeat']).total_seconds(),
                        'readings' : {}
                        }
                    for reading_name in sensor_doc['readings']:
                        reading_doc = self.GetReadingSetting(sensor_name, reading_name)
                        status[hostname]['sensors'][sensor_name]['readings'][reading_name] = {
                            'description' : reading_doc['description'],
                            'status' : reading_doc['status'],
                            }
                        if reading_doc['status'] == 'online':
                            status[hostname]['sensors'][sensor_name]['readings'][reading_name]['runmode'] = reading_doc['runmode'],
                except TypeError as e:
                    pass
        return status
