import Doberman
import datetime
from socket import getfqdn
import time
import requests

__all__ = 'Database'.split()

dtnow = Doberman.utils.dtnow


class Database(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self, mongo_client, experiment_name=None):
        self.client = mongo_client
        self.hostname = getfqdn()
        self.experiment_name = experiment_name
        influx_cfg = self.read_from_db('settings', 'experiment_config', {'name': 'influx'}, onlyone=True)
        self.influx_url = influx_cfg['url'] + '/write?'
        if influx_cfg['version'] == 1:
            query_params = [('u', influx_cfg['username']), ('p', influx_cfg['password']),
                            ('db', influx_cfg['org']), ('precision', influx_cfg['precision'])]
            self.influx_headers = {}
        elif influx_cfg['version'] == 2:
            query_params = [('org', influx_cfg['org']), ('precision', influx_cfg['precision']),
                            ('bucket', influx_cfg['bucket'])]
            self.influx_headers = {'Authorization': 'Token ' + influx_cfg['token']}
        else:
            raise ValueError(f'I only take influx versions 1 or 2, not "{influx_cfg["version"]}"')
        self.influx_url += '&'.join([f'{k}={v}' for k, v in query_params])
        self.influx_precision = int(dict(zip(['s', 'ms', 'us', 'ns'], [1, 1e3, 1e6, 1e9]))[influx_cfg['precision']])

    def close(self):
        pass

    def __del__(self):
        self.close()

    def __exit__(self):
        self.close()

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

    def insert_into_db(self, db_name, collection_name, document, **kwargs):
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
                self.logger.error(f'Inserted {len(result.inserted_ids)} entries instead of {len(document)} into'
                                  + f'{db_name}.{collection_name}')
                return -1
            return 0
        if isinstance(document, dict):
            result = collection.insert_one(document, **kwargs)
            if result.acknowledged:
                return 0
            return -2
        self.logger.error(f'Not sure what to do with {type(document)} type')
        return 1

    def read_from_db(self, db_name, collection_name, cuts={}, onlyone=False, **kwargs):
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

    def update_db(self, db_name, collection_name, cuts, updates, **kwargs):
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

    def delete_documents(self, db_name, collection_name, cuts):
        """
        Deletes documents from the specified collection

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: dictionary specifying the query
        :returns None
        """
        collection = self._check(db_name, collection_name)
        collection.delete_many(cuts)

    def get_experiment_config(self, name, field=None):
        """
        Gets an experiment config document
        :param name: the name of the document
        :param field: a specific field
        :returns: The whole document if field = None, either just the field
        """
        doc = self.read_from_db('settings', 'experiment_config', {'name': name}, onlyone=True)
        if field:
            return doc[field]
        return doc

    def delete_alarm(self, reading_name, alarm_type):
        """
        Delete alarm of specific type from a reading
        :param reading_name: name of the reading
        :param alarm_type: alarm type to be removed
        """
        self.update_db('settings', 'readings', {'name': reading_name},
                       {'$pull': {'alarms': {'type': alarm_type}}})

    def update_alarm(self, reading_name, alarm_doc):
        alarm_type = alarm_doc['type']
        self.delete_alarm(reading_name, alarm_type)
        self.update_db('settings', 'readings', {'name': reading_name},
                       {'$push': {'alarms': alarm_doc}})

    def distinct(self, db_name, collection_name, field, cuts={}, **kwargs):
        """
        Transfer function for collection.distinct
        """
        return self._check(db_name, collection_name).distinct(field, cuts, **kwargs)

    def count(self, db_name, collection_name, cuts, **kwargs):
        """
        Transfer function for collection.count/count_documents
        """
        return self._check(db_name, collection_name).count_documents(cuts, **kwargs)

    def find_one_and_update(self, db_name, collection_name, cuts, updates, **kwargs):
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
        doc = self.read_from_db(db_name, collection_name, cuts, onlyone=True, **kwargs)
        if doc is not None:
            self.update_db(db_name, collection_name, {'_id': doc['_id']}, updates)
        return doc

    def find_command(self, name):
        """
        Finds the oldest unacknowledged command for the specified entity
        and updates it as acknowledged. Deletes command documents used in
        the feedback subsystem

        :param name: the entity to find a command for
        :returns command document
        """
        now = dtnow()
        doc = self.find_one_and_update('logging', 'commands',
                                       # the order of terms in the query is important
                                       cuts={'acknowledged': 0,
                                             'logged': {'$lte': now},
                                             'name': name},
                                       updates={'$set': {'acknowledged': now}},
                                       sort=[('logged', 1)])
        if doc and 'by' in doc and doc['by'] == 'feedback':
            self.delete_documents('logging', 'commands', {'_id': doc['_id']})
        return doc

    def log_command(self, doc):
        """
        """
        if 'logged' not in doc:
            doc['logged'] = dtnow()
        doc['acknowledged'] = 0
        self.insert_into_db('logging', 'commands', doc)

    def get_pipeline(self, name):
        """
        Gets a pipeline config doc
        :param name: the name of the pipeline
        """
        return self.read_from_db('settings', 'pipelines', {'name': name}, onlyone=True)

    def get_alarm_pipelines(self, inactive=False):
        """
        Returns a list of names of pipelines.
        :param inactive: bool, include currently inactive pipelines in the return
        :yields: names of pipelines
        """
        query = {'name': {'$regex': 'alarm'}, 'status': {'$in': ['active', 'silent']}}
        if inactive:
            del query['status']
        for doc in self.read_from_db('settings', 'pipelines', query):
            yield doc['name']

    def set_pipeline_value(self, name, kvp):
        """
        Updates a pipeline config
        :param name: the name of the pipeline
        :param kvp: a list of (key, value) pairs to set
        """
        return self.update_db('settings', 'pipelines', {'name': name}, {'$set': dict(kvp)})

    def get_message_protocols(self, level):
        """
        Gets message protocols for the specified alarm level. If none are found,
        takes those from the next lowest level.

        :param level: which alarm level is in question (0, 1, etc)
        :returns: list of message protocols to use
        """
        doc = self.read_from_db('settings', 'alarm_config',
                                {'level': level}, onlyone=True)
        if doc is None:
            self.logger.error(('No message protocols for alarm level %i! '
                               'Defaulting to next lowest level' % level))
            doc = self.read_from_db('settings', 'alarm_config',
                                    {'level': {'$lte': level}}, onlyone=True,
                                    sort=[('level', -1)])
        return doc['protocols']

    def get_contact_addresses(self, level):
        """
        Returns a list of addresses to contact at 'level' who are currently on shift,
            defined as when the function is called

        :param level: which alarm level the message will be sent at
        :returns dict, keys = message protocols, values = list of addresses
        """
        if level == 'ohshit':
            # shit shit fire ze missiles!
            protocols = set()
            for doc in self.read_from_db('settings', 'alarm_config', {'level': {'$gte': 0}}):
                protocols |= set(doc['protocols'])
            ret = {k: [] for k in protocols}
            for doc in self.read_from_db('settings', 'contacts'):
                for p in protocols:
                    try:
                        ret[p].append(doc[p])
                    except:
                        pass
            return ret
        else
            protocols = self.get_message_protocols(level)
            ret = {k: [] for k in protocols}
            now = datetime.datetime.now()  # no UTC here, we want local time
            shifters = self.read_from_db('settings', 'shifts',
                                         {'start': {'$lte': now}, 'end': {'$gte': now}},
                                         onlyone=True)['shifters']
            for doc in self.read_from_db('settings', 'contacts',
                                         {'name': {'$in': shifters}}):
                for p in protocols:
                    ret[p].append(doc[p])
            return ret

    def get_heartbeat(self, sensor=None):
        doc = self.read_from_db('settings', 'sensors', cuts={'name': sensor}, onlyone=True)
        return doc['heartbeat']

    def update_heartbeat(self, sensor=None):
        """
        Heartbeats the specified sensor or host
        """
        self.update_db('settings', coll, cuts={'name': sensor},
                       updates={'$set': {'heartbeat': dtnow()}})
        return

    def log_alarm(self, document):
        """
        Adds the alarm to the history.
        """
        document['acknowledged'] = 0
        if self.insert_into_db('logging', 'alarm_history', document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def log_update(self, **kwargs):
        """
        Logs changes submitted from the website
        """
        self.insert_into_db('logging', 'updates', kwargs)

    def get_sensor_setting(self, name, field=None):
        """
        Gets a specific setting from one sensor

        :param name: the name of the sensor
        :param field: the field you want
        :returns: the value of the named field
        """
        doc = self.read_from_db('settings', 'sensors', cuts={'name': name},
                                onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def set_sensor_setting(self, name, field, value):
        """
        Updates the setting from one sensor

        :param name: the name of the sensor
        :param field: the specific field to update
        :param value: the new value
        """
        self.update_db('settings', 'sensors', cuts={'name': name},
                       updates={'$set': {field: value}})

    def get_reading_setting(self, sensor=None, name=None, field=None):
        """
        Gets the document from one reading

        :param sensor: the name of the sensor (ignored)
        :param name: the name of the reading
        :param field: the specific field to return
        :returns: reading document
        """
        doc = self.read_from_db('settings', 'readings', cuts={'name': name}, onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def set_reading_setting(self, sensor=None, name=None, field=None, value=None):
        """
        Updates a parameter for a reading, used only by the web interface

        :param sensor: the name of the sensor
        :param name: the name of the reading
        :param field: the specific field to update
        :param value: the new value
        """
        self.update_db('settings', 'readings',
                       cuts={'sensor': sensor, 'name': name},
                       updates={'$set': {field: value}})

    def get_runmode_setting(self, runmode=None, field=None):
        """
        Reads default Doberman settings from database.

        :param runmode: the runmode to get settings for
        :param field: the name of the setting
        :returns: the setting dictionary if name=None, otherwise the specific field
        """
        doc = self.read_from_db('settings', 'runmodes',
                                {'mode': runmode}, onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def notify_hypervisor(self, active=None, inactive=None, unmanage=None):
        """
        A way for sensors to tell the hypervisor when they start and stop and stuff
        :param active: the name of a sensor that's just starting up
        :param inactive: the name of a sensor that's stopping
        :param unamange: the name of a sensor that doesn't need to be monitored
        """
        updates = {}
        if active:
            updates['$addToSet'] = {'processes.active': active}
        if inactive:
            updates['$pull'] = {'processes.active': inactive}
        if unmanage:
            updates['$pull'] = {'processes.managed': unmanage}
        if updates:
            self.update_db('settings', 'experiment_config', {'name': 'hypervisor'},
                    updates)
        return

    def get_host_setting(self, host=None, field=None):
        """
        Gets the setting document of the specified host
        """
        if host is None:
            host = self.hostname
        doc = self.read_from_db('settings', 'hosts', {'hostname': host},
                                onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def set_host_setting(self, host=None, **kwargs):
        """
        Updates the setting document of the specified host. Kwargs should be one
        of the Mongo commands (set, unset, push, pull) without the $ char.
        Ex: set={field:value}
        """
        if host is None:
            host = self.hostname
        self.update_db('settings', 'hosts', {'hostname': host},
                       updates={f'${k}': v for k, v in kwargs.items()})

    def write_to_influx(self, topic=None, tags=None, fields=None, timestamp=None):
        """
        Writes the specified data to Influx. See
        https://docs.influxdata.com/influxdb/v2.0/write-data/developer-tools/api/
        for more info. The URL and access credentials are stored in the database and cached for use
        :param topic: the named named type of measurement (temperature, pressure, etc)
        :param tags: a dict of tag names and values, usually 'sensor' and 'reading'
        :param fields: a dict of field names and values, usually 'value', required
        :param timestamp: a unix timestamp, otherwise uses whatever "now" is if unspecified.
        """
        if topic is None or fields is None:
            raise ValueError('Missing required fields for influx insertion')
        data = f'{topic}' if self.experiment_name != 'testing' else 'testing'
        if tags is not None:
            data += ',' + ','.join([f'{k}={v}' for k, v in tags.items()])
        data += ' '
        data += ','.join([
            f'{k}={v}i' if isinstance(v, int) else f'{k}={v}' for k, v in fields.items()
        ])
        timestamp = timestamp or time.time()
        data += f' {int(timestamp * self.influx_precision)}'
        if requests.post(self.influx_cfg['url'], headers=self.influx_cfg['headers'], data=data).status_code != 200:
            # something went wrong
            pass

    def get_current_status(self):
        """
        Gives a snapshot of the current system status
        """
        status = {}
        now = dtnow()
        for host_doc in self.read_from_db('common', 'hosts'):
            hostname = host_doc['hostname']
            status[hostname] = {
                'status': host_doc['status'],
                'last_heartbeat': (now - host_doc['heartbeat']).total_seconds(),
                'sensors': {}
            }
            for sensor_name in host_doc['default']:
                try:
                    sensor_doc = self.read_from_db('settings', 'sensors', cuts={'name': sensor_name}, onlyone=True)
                    status[hostname]['sensors'][sensor_name] = {
                        'last_heartbeat': (now - sensor_doc['heartbeat']).total_seconds(),
                        'readings': {}
                    }
                    if 'multi' in sensor_doc:
                        readings = sensor_doc['multi']
                    else:
                        readings = sensor_doc['readings']
                    for reading_name in readings:
                        reading_doc = self.get_reading_setting(sensor_name, reading_name)
                        status[hostname]['sensors'][sensor_name]['readings'][reading_name] = {
                            'description': reading_doc['description'],
                            'status': reading_doc['status'],
                        }
                        if reading_doc['status'] == 'online':
                            status[hostname]['sensors'][sensor_name]['readings'][reading_name]['runmode'] \
                                = reading_doc['runmode']
                except TypeError:
                    pass
        return status
