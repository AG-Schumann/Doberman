from pymongo import MongoClient
import os

SENSOR_INPUT = 'V_LB_01'

pl = {
        'name': 'test_pipeline',
        'status': 'inactive',
        'depends_on': [SENSOR_INPUT],
        'node_config': {
            'filter': {'length': 5},
            'diff': {'length': 5},
            'integral': {'length': 10}
        },
        'pipeline': [
            {
                'name': 'input_db',
                'type': 'InfluxSourceNode',
                'input_var': SENSOR_INPUT,
                'accept_old': True,
            },
            {
                'name': 'input_sync',
                'type': 'SensorSourceNode',
                'input_var': SENSOR_INPUT,
            },
            {
                'name': 'input_sync_5',
                'type': 'SensorSourceNode',
                'input_var': 'X_SYNC_5',
                'new_value_required': True
            },
            {
                'name': 'filter',
                'type': 'MedianFilter',
                'input_var': SENSOR_INPUT,
                'upstream': ['input_sync'],
            },
            {
                'type': 'MergeNode',
                'upstream': ['filter', 'input_db'],
                'name': 'merge',
                'merge_how': 'newest'
            },
            {
                'type': 'DerivativeNode',
                'name': 'diff',
                'upstream': ['merge'],
                'input_var': SENSOR_INPUT,
                'output_var': 't_rate'
            },
            {
                'type': 'IntegralNode',
                'name': 'integral',
                'input_var': 't_rate',
                'output_var': 't_whatever',
                'upstream': ['diff']
            },
            {
                'type': 'EvalNode',
                'operation': 'True',
                'output_var': 'condition_test',
                'input_var': [SENSOR_INPUT],
                'name': 'eval',
                'upstream': ['integral']
            },
            {
                'type': 'PipelineControl',
                'name': 'end',
                'input_var': '',
                'control_target': '',
                'control_value': '',
                'upstream': ['eval']
            }
        ],
    }

with MongoClient(os.environ['DOBERMAN_MONGO_URI']) as client:
    client.pancake.pipelines.update_one({'name': pl['name']}, {'$set': pl}, upsert=True)
