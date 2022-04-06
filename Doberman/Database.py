import Doberman
import datetime
from socket import getfqdn, create_connection
import time
import requests
import json
import pytz
import itertools

__all__ = 'Database'.split()

dtnow = Doberman.utils.dtnow


class Database(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self, mongo_client, experiment_name=None, bucket_override=None):
        self.hostname = getfqdn()
        self.experiment_name = experiment_name
        self._db = mongo_client[self.experiment_name]
        influx_cfg = self.read_from_db('experiment_config', {'name': 'influx'}, onlyone=True)
        url = influx_cfg['url']
        query_params = [('precision', influx_cfg.get('precision', 'ms'))]
        if (influx_version := influx_cfg.get('version', 2)) == 1:
            query_params += [('u', influx_cfg['username']),
                            ('p', influx_cfg['password']),
                            ('db', influx_cfg['org'])]
            url += '/write?'
            headers = {}
        elif influx_version == 2:
            query_params += [('org', influx_cfg['org']),
                            ('bucket', bucket_override or influx_cfg['bucket'])]
            url += '/api/v2/write?'
            headers = {'Authorization': 'Token ' + influx_cfg['token']}
        else:
            raise ValueError(f'I only take influx versions 1 or 2, not "{influx_version}"')
        url += '&'.join([f'{k}={v}' for k, v in query_params])
        precision = {'s': 1, 'ms': 1000, 'us': 1_000_000, 'ns': 1_000_000_000}
        self.influx_cfg = (url, headers, precision[influx_cfg.get('precision', 'ms')])
        self.address_cache = {}

    def close(self):
        print('DB shutting down')
        pass

    def __del__(self):
        self.close()

    def __exit__(self):
        self.close()

    def insert_into_db(self, collection_name, document, **kwargs):
        """
        Inserts document(s) into the specified database/collection

        :param collection_name: name of the collection
        :param document: a dictionary or iterable of dictionaries
        :param **kwargs: any keyword args, passed to collection.insert_(one|many)
        :returns 0 if successful, -1 if a multiple insert failed, -2 if a single
        insert failed, or 1 if `document` has the wrong type
        """
        collection = self._db[collection_name]
        if isinstance(document, (list, tuple)):
            result = collection.insert_many(document, **kwargs)
            if len(result.inserted_ids) != len(document):
                self.logger.error(f'Inserted {len(result.inserted_ids)} entries instead of {len(document)} into'
                                  + f'{collection_name}')
                return -1
            return 0
        if isinstance(document, dict):
            result = collection.insert_one(document, **kwargs)
            if result.acknowledged:
                return 0
            return -2
        self.logger.error(f'Not sure what to do with {type(document)} type')
        return 1

    def read_from_db(self, collection_name, cuts={}, onlyone=False, **kwargs):
        """
        Finds one or more documents that pass the specified cuts

        :param collection_name: name of the collection
        :param cuts: dictionary of the query to apply. Default {}
        :param onlyone: bool, if only one document is requested
        :param **kwargs: keyword args passed to collection.find. The 'sort' kwarg
        is handled separately because otherwise it doesn't do anything
        :returns document if onlyone=True else cursor
        """
        collection = self._db[collection_name]
        cursor = collection.find(cuts, **kwargs)
        if 'sort' in kwargs:
            cursor.sort(kwargs['sort'])
        if onlyone:
            for doc in cursor:
                return doc
        else:
            return cursor

    def update_db(self, collection_name, cuts, updates, **kwargs):
        """
        Updates documents that meet pass the specified cuts

        :param collection_name: name of the collection
        :param cuts: the dictionary specifying the query
        :param updates: the dictionary specifying the desired changes
        :param **kwargs: keyword args passed to collection.update_many
        :returns 0 if successful, 1 if not
        """
        collection = self._db[collection_name]
        ret = collection.update_many(cuts, updates, **kwargs)
        if not ret.acknowledged:
            return 1
        return 0

    def delete_documents(self, collection_name, cuts):
        """
        Deletes documents from the specified collection

        :param collection_name: name of the collection
        :param cuts: dictionary specifying the query
        :returns None
        """
        collection = self._db[collection_name]
        collection.delete_many(cuts)

    def get_experiment_config(self, name, field=None):
        """
        Gets an experiment config document
        :param name: the name of the document
        :param field: a specific field
        :returns: The whole document if field = None, either just the field
        """
        doc = self.read_from_db('experiment_config', {'name': name}, onlyone=True)
        if doc and field and field in doc:
            return doc[field]
        return doc

    def distinct(self, collection_name, field, cuts={}, **kwargs):
        """
        Transfer function for collection.distinct
        """
        return self._db[collection_name].distinct(field, cuts, **kwargs)

    def count(self, collection_name, cuts, **kwargs):
        """
        Transfer function for collection.count/count_documents
        """
        return self._db[collection_name].count_documents(cuts, **kwargs)

    def find_one_and_update(self, collection_name, cuts, updates, **kwargs):
        """
        Finds one document and applies updates. A bit of a special implementation so
        the 'sort' kwarg will actually do something

        :param collection_name: name of the collection
        :param cuts: a dictionary specifying the query
        :param updates: a dictionary specifying the updates
        :**kwargs: keyword args passed to readFromDatabase
        :returns document
        """
        doc = self.read_from_db(collection_name, cuts, onlyone=True, **kwargs)
        if doc is not None:
            self.update_db(collection_name, {'_id': doc['_id']}, updates)
        return doc

    def log_command(self, command, to, issuer, delay=0, bypass_hypervisor=False):
        """
        Issue a command to someone else
        :param command: the command for them to process
        :param to: who the command is for
        :param issuer: who is issuing the command
        :param delay: how far into the future the command should happen, default 0
        :param bypass_hypervisor: bool, communicate directly with recipient?
        :returns: None
        """
        doc = {
                'to': to,
                'command': command,
                'by': issuer,
                'time': time.time() + delay
                }
        hn, p = self.find_listener_address(to if bypass_hypervisor else 'hypervisor')
        with create_connection((hn, p), timeout=0.1) as sock:
            sock.sendall((command if bypass_hypervisor else json.dumps(doc)).encode())

    def get_experiment_config(self, name, field=None):
        """
        Gets a document or parameter from the experimental configs
        :param field: which field you want, default None which gives you all of them
        :returns: either the whole document or a specific field
        """
        doc = self.read_from_db('experiment_config', {'name': name}, onlyone=True)
        if doc is not None and field is not None:
            return doc.get(field)
        return doc

    def get_pipeline_stats(self, name):
        """
        Gets the status info of another pipeline
        :param name: the pipeline in question
        :returns:
        """
        return self.read_from_db('pipelines', {'name': name}, onlyone=True,
                projection={'status': 1, 'cycles': 1, 'error': 1, 'rate': 1, '_id': 0})

    def get_pipeline(self, name):
        """
        Gets a pipeline config doc
        :param name: the name of the pipeline
        """
        return self.read_from_db('pipelines', {'name': name}, onlyone=True)

    def get_pipelines(self, flavor):
        """
        Generates a list of names of pipelines to start now. Called by
        PipelineMonitors on startup.
        :param flavor: which type of pipelines to select, should be one of "alarm", "control", "convert"
        :yields: string
        """
        query = {'status': {'$in': ['active', 'silent']},
                 'name': {'$regex': f'^{flavor}_'}}
        for doc in self.read_from_db('pipelines', query, projection={'name': 1}):
            yield doc['name']

    def set_pipeline_value(self, name, kvp):
        """
        Updates a pipeline config
        :param name: the name of the pipeline
        :param kvp: a list of (key, value) pairs to set
        """
        return self.update_db('pipelines', {'name': name}, {'$set': dict(kvp)})

    def get_message_protocols(self, level):
        """
        Gets message protocols for the specified alarm level. If none are found,
        takes those from the highest level defined.

        :param level: which alarm level is in question (0, 1, etc)
        :returns: list of message protocols to use
        """
        protocols = self.get_experiment_config('alarm', 'protocols')
        if len(protocols) < level:
            self.logger.error(f'No message protocols for alarm level {level}! '
                               'Defaulting to highest level defined')
            return protocols[-1]
        return protocols[level]

    def get_message_recipients(self, level):
        """
        Gets message recipients for the specified alarm level

        :param level: which alarm level is in question (0, 1, etc)
        :returns: set of recipient names
        """
        recipient_groups = self.get_experiment_config('alarm', 'recipients')
        if len(recipient_groups) < level:
            recipient_groups = ['everyone']
        else:
            recipient_groups = recipient_groups[level]
        recipient_names = set()
        for group in recipient_groups:
            if group == 'shifters':
                for doc in self.read_from_db('contacts', {'on_shift': True}):
                    recipient_names.add(doc['name'])
            elif group == 'experts':
                for doc in self.read_from_db('contacts', {'expert': True}):
                    recipient_names.add(doc['name'])
            elif group == 'everyone':
                for doc in self.read_from_db('contacts'):
                    recipient_names.add(doc['name'])
        return list(recipient_names)


    def get_contact_addresses(self, level):
        """
        Returns a list of addresses to contact at 'level' who are currently on shift,
            defined as when the function is called

        :param level: which alarm level the message will be sent at
        :returns dict, keys = message protocols, values = list of addresses
        """
        protocols = self.get_message_protocols(level)
        recipients = self.get_message_recipients(level)
        ret = {k: [] for k in protocols}
        for doc in self.read_from_db('contacts', {'name': {'$in': recipients}}):
            for p in protocols:
                try:
                    ret[p].append(doc[p])
                except KeyError:
                    contactname = doc['name']
                    self.logger.info(f"No {p} contact details for {contactname}")
        return ret

    def get_heartbeat(self, device=None):
        doc = self.read_from_db('devices', cuts={'name': device}, onlyone=True)
        return doc['heartbeat'].replace(tzinfo=pytz.utc)

    def update_heartbeat(self, device=None):
        """
        Heartbeats the specified device or host
        """
        self.update_db('devices', cuts={'name': device},
                       updates={'$set': {'heartbeat': dtnow()}})
        return

    def get_device_setting(self, name, field=None):
        """
        Gets a specific setting from one device

        :param name: the name of the device
        :param field: the field you want
        :returns: the value of the named field
        """
        doc = self.read_from_db('devices', cuts={'name': name},
                                onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def set_device_setting(self, name, field, value):
        """
        Updates the setting from one device

        :param name: the name of the device
        :param field: the specific field to update
        :param value: the new value
        """
        self.update_db('devices', cuts={'name': name},
                       updates={'$set': {field: value}})

    def get_sensor_setting(self, name, field=None):
        """
        Gets a value for one sensor

        :param name: the name of the sensor
        :param field: a specific field, default None which return the whole doc
        :returns: named field, or the whole doc
        """
        doc = self.read_from_db('sensors', cuts={'name': name},
                onlyone=True)
        return doc[field] if field is not None and field in doc else doc

    def get_runmode_setting(self, runmode=None, field=None):
        """
        Reads default Doberman settings from database.

        :param runmode: the runmode to get settings for
        :param field: the name of the setting
        :returns: the setting dictionary if name=None, otherwise the specific field
        """
        doc = self.read_from_db('runmodes',
                                {'mode': runmode}, onlyone=True)
        if field is not None:
            return doc[field]
        return doc

    def notify_hypervisor(self, active=None, inactive=None, unmanage=None):
        """
        A way for devices to tell the hypervisor when they start and stop and stuff
        :param active: the name of a device that's just starting up
        :param inactive: the name of a device that's stopping
        :param unmanage: the name of a device that doesn't need to be monitored
        """
        updates = {}
        if active:
            updates['$addToSet'] = {'processes.active': active}
        if inactive:
            updates['$pull'] = {'processes.active': inactive}
        if unmanage:
            updates['$pull'] = {'processes.managed': unmanage}
        if updates:
            self.update_db('experiment_config', {'name': 'hypervisor'},
                           updates)
        return

    def assign_listener_address(self, name):
        """
        Assign a hostname and port for communication
        :param name: who will get this assignment
        :returns: (string, int) tuple of hostname and port
        """
        doc = self.get_experiment_config('hypervisor', field='global_dispatch')
        if name in self.distinct('devices', 'name'):
            # this is a device
            host = self.get_device_setting(name, field='host')
        else:
            # probably a pipeline, assume it runs on the master host
            host = doc['hypervisor'][0]
        existing_ports = [p for (hn, p) in doc.values() if hn == host] or [doc['hypervisor'][1]]
        for port in itertools.count(min(existing_ports)):
            if port in existing_ports:
                continue
            self.logger.info(f'Assigning {host}:{port} to {name}')
            self.update_db('experiment_config', {'name': 'hypervisor'}, {'$set': {f'global_dispatch.{name}': [host, port]}})
            return host, int(port)

    def find_listener_address(self, name):
        """
        Get a hostname and port to communicate over. If none exist, raise an error

        :param name: the name of someone
        :returns: (string, int) tuple of the hostname and port
        """
        if name in self.address_cache:
            return self.address_cache[name]
        doc = self.get_experiment_config('hypervisor', field='global_dispatch')
        # doc looks like { name: [host, port], ...}
        if name in doc:
            host, port = doc[name]
            if name in ['pl_alarm', 'pl_control', 'pl_convert', 'hypervisor']:
                self.address_cache[name] = (host, int(port))
            return host, int(port)
        raise ValueError(f'No assigned listener info for {name}')

    def release_listener_port(self, name):
        """
        Return the port used by <name> to the pool
        """
        if name != 'hypervisor':
            self.update_db('experiment_config', {'name': 'hypervisor'}, {'$unset': {f'global_dispatch.{name}': 1}})

    def get_host_setting(self, host=None, field=None):
        """
        Gets the setting document of the specified host
        """
        if host is None:
            host = self.hostname
        doc = self.read_from_db('hosts', {'name': host}, onlyone=True)
        if doc is not None and field is not None and field in doc:
            return doc[field]
        return doc

    def write_to_influx(self, topic=None, tags=None, fields=None, timestamp=None):
        """
        Writes the specified data to Influx. See
        https://docs.influxdata.com/influxdb/v2.0/write-data/developer-tools/api/
        for more info. The URL and access credentials are stored in the database and cached for use
        :param topic: the named named type of measurement (temperature, pressure, etc)
        :param tags: a dict of tag names and values, usually 'subsystem' and 'sensor'
        :param fields: a dict of field names and values, usually 'value', required
        :param timestamp: a unix timestamp, otherwise uses whatever "now" is if unspecified.
        :returns: None
        """
        url, headers, precision = self.influx_cfg
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
        data += f' {int(timestamp * precision)}'
        r = requests.post(url, headers=headers, data=data)
        if r.status_code not in [200, 204]:
            # something went wrong
            self.logger.error(f'Got status code {r.status_code} instead of 200/204')
            try:
                self.logger.error(r.json())
            except:
                self.logger.error(r.content)

    def send_value_to_pipelines(self, sensor, value, timestamp):
        """
        Send a recently recorded value to the pipeline monitors
        :param sensor: string, the name of the sensor
        :param value: float/int, the value
        :param timestamp: float, the timestamp
        :returns: None
        """
        for pl in ['pl_alarm', 'pl_control', 'pl_convert']:
            self.log_command(
                        f'sensor_value {sensor} {timestamp} {value}',
                        to=pl,
                        issuer=None,
                        bypass_hypervisor=True)

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
                'devices': {}
            }
            for device_name in host_doc['default']:
                try:
                    device_doc = self.read_from_db('devices', cuts={'name': device_name}, onlyone=True)
                    status[hostname]['devices'][device_name] = {
                        'last_heartbeat': (now - device_doc['heartbeat']).total_seconds(),
                        'sensors': {}
                    }
                    if 'multi' in device_doc:
                        sensors = device_doc['multi']
                    else:
                        sensors = device_doc['sensors']
                    for sensor_name in sensors:
                        sensor_doc = self.get_sensor_setting(device_name, sensor_name)
                        status[hostname]['devices'][device_name]['sensors'][sensor_name] = {
                            'description': sensor_doc['description'],
                            'status': sensor_doc['status'],
                        }
                        if sensor_doc['status'] == 'online':
                            status[hostname]['devices'][device_name]['sensors'][sensor_name]['runmode'] \
                                = sensor_doc['runmode']
                except TypeError:
                    pass
        return status
