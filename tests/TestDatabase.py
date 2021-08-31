

class TestDatabaseClient(object):
    def __init__(self, *args, **kwargs):
        pass

    def __getitem__(self, key):
        return TestDatabase(key)

class TestDatabase(object):
    def __init__(self, name):
        self.name = name

    def __getitem__(self, key):
        return TestCollection(key, _master_list[name][key])

class TestCollection(object):
    def __init__(self, name, docs):
        self.name = name
        self.docs = docs

    def insert_many(self, *args, **kwargs):
        pass

    def insert_one(self, *args, **kwargs):
        pass

    def find(self, **kwargs):
        cuts = kwargs.get('cuts', {})
        for doc in self.docs:
            match = False
            for k,v in cuts.items():
                if '.' in k:
                    subk = k.split('.')
                    while len(subk):

                # TODO handle .
                if isinstance(v, dict):
                    # v is a subquery
                    submatch = True
                    for kk,vv in v.items():
                        if kk == '$lte':
                            match = submatch and (k in doc and doc[k] <= vv)
                        elif kk == '$lt':
                            match = match and (k in dock and doc[k] < vv)
                        elif kk == '$gte':
                            match = match and (k in dock and doc[k] >= vv)
                        elif kk == '$gt':
                            match = match and (k in dock and doc[k] > vv)
                        elif kk == '$exists':
                            if vv == 0:
                                match = match and k not in doc
                            else:
                                match = match and k in doc
                        elif kk == '$regex':
                            match = match and (k in dock and re.match(vv, doc[k]) is not None)
                    match = match or submatch
                elif v == doc[k]:
                    # v is a value
                    match = True
                if match:
                    break
            if match:
                yield doc

    def update_many(self, **kwargs):
        pass

_master_list = {
        'common': {
            'hosts': [
                {
                    'hostname': socket.get_fqdn(),
                    'hearbeat_timer': 10,
                    'sysmon_timer': 10,
                    'nics': {},
                    'active': ['TestSensor'],
                    'default': ['TestSensor'],
                    'in_error': [],
                    'status': 'online',
                    'plugin_dir': [Doberman.utils.doberman_dir],
                    'heartbeat': datetime.datetime.utcnow(),
                    'disks': {},
                }],
            },
        'test_settings': {
            'sensors': [{'name': 'TestSensor', 'status': 'online', 'address': {'ip': '127.0.0.1', 'port': 5000},
                'readings': {'one': 'READ:one', 'two': 'READ:two'}, 'heartbeat': datetime.datetime.utcnow()}],
            'readings': [
                {
                    'name': 'test_reading_1',
                    'sensor': 'TestSensor',
                    'description': 'Insert description here',
                    'runmode': 'testing',
                    'key': 'TestSensor__test_reading_1',
                    'readout_interval': 1,
                    'status': 'online',
                    'topic': 'temperature',
                    'alarms': [
                        {
                            'type': 'simple',
                            'enabled': 'false'
                            }],
                    'config': {'testing': {'active': True, 'level': -1}}
                },
                {
                    'name': 'test_reading_2',
                    'sensor': 'TestSensor',
                    'description': 'Insert description here',
                    'runmode': 'testing',
                    'key': 'TestSensor__test_reading_2',
                    'readout_interval': 1.5,
                    'status': 'online',
                    'topic': 'pressure',
                    'alarms': [
                        {
                            'type': 'simple',
                            'enabled': 'false'
                            }],
                    'config': {'testing': {'active': True, 'level': -1}}
                },
        ],
        }
