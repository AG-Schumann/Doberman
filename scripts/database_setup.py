from pymongo import MongoClient
import os

c = MongoClient(os.environ['DOBERMAN_MONGO_URI'])
experiment = os.environ['DOBERMAN_EXPERIMENT_NAME']

db = c[f'{experiment}_settings']
db.sensors.create_index({'name': 1})
db.readings.create_index({'name': 1})
db.shifts.create_index({'start': 1, 'end': -1})
db.experiment_config.insert_many([
    {'name': 'hypervisor', 'processes': {'managed': [], 'active': []}, 'period': 60, 'restart_timeout': 300},
    {'name': 'influx', 'url': 'http://localhost:8086/', 'token': 'influx_token_here', 'org': 'influx_org_here',
        'precision': 'ms', 'bucket': 'influx_bucket_here', 'version': 2},
    {'name': 'alarms',
        'email': {'contactaddr': '', 'server': '', 'port': 0, 'fromaddr': '', 'password': ''},
        'sms': {'contactaddr': '', 'server': '', 'identification': ''}},
    ])


db = c[f'{experiment}_logging']
db.alarm_history.create_index({'acknowledged': 0})
#db.logs.create_index({})
