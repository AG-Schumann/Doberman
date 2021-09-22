import Doberman
import requests
import time
import itertools
import enum

class PipelineStatus(enum.Enum):
    offline = 0
    silent = 1
    active = 2


class Pipeline(object):
    """
    A generic data-processing pipeline graph intended to replace Storm
    """
    def __init__(self, **kwargs):
        self.graph = {}
        self.db = kwargs['db']
        self.logger = kwargs['logger']
        self.name = kwargs['name']
        self.cycles = 0

    def process_cycle(self):
        """
        This function gets Registered with the owning PipelineMonitor
        """
        doc = self.db.get_pipeline(self.name)
        self.reconfigure(doc['node_config'])
        timing = {}
        self.logger.debug(f'Pipeline {self.name} cycle {self.cycles}')
        for node in self.graph.values():
            t_start = time.time()
            try:
                node._process_base(doc['status']) # status == 1 is silent, 2 is active, 0 is off
            except Exception as e:
                msg = f'Pipeline {self.name} node {node.name} threw {type(e)}: {e}'
                if self.cycles <= self.startup_cycles:
                    # we expect errors during startup as buffers get filled
                    self.logger.debug(msg)
                else:
                    self.logger.warning(msg)
                break # probably shouldn't finish the cycle
            t_end = time.time()
            timing[node.name] = (t_end-t_start)*1000
        self.logger.debug(f'Processing time: total {sum(timing.values()):.3f} ms, individual {timing}')
        self.cycles += 1
        self.db.set_pipeline_value(self.name, [('heartbeat', Doberman.utils.dtnow(), 'cycles': self.cycles)])
        return doc['period']

    def build(self, config):
        """
        Generates the graph based on the input config, which looks like this:
        {
            name: {
                "type: <node type>,
                "upstream": [upstream node names],
                "downstream": [downstream node names],
                **kwargs
            },
            name: ...
        }
        'type' is the type of Node ('Node', 'MergeNode', etc), [node names] is a list of names of the immediate neighbor nodes,
        and kwargs is whatever that node needs for instantiation
        We generate nodes in such an order that we can just loop over them in the order of their construction
        and guarantee that everything that this node depends on has already run this loop
        """
        pipeline_config = config['pipeline']['config']
        self.logger.debug(f'Loading graph config, {len(pipeline_config)} nodes total')
        downstream = {}
        num_buffer_nodes = 0
        longest_buffer = 0
        influx_cfg = self.read_from_db('settings', 'experiment_config', {'name': 'influx'}, onlyone=True)
￼       influx_url = influx_cfg['url']
        influx_headers = influx_cfg['headers']
        while len(self.graph) != len(pipeline_config):
            start_len = len(self.graph)
            for name, kwargs in pipeline_config.items():
                if name in self.graph:
                    continue
                upstream = kwargs.get('upstream', [])
                if len(upstream) == 0 or all([u in self.graph for u in upstream]):
                    # all this node's requirements are created
                    node_type = kwargs.pop('type')
                    node_kwargs = {'name': name, 'logger': self.logger,
                            'upstream': [self.graph[u] for u in kwargs.pop('upstream', [])]}
                    if node_type == 'InfluxSourceNode':
                        node_kwargs['influx_url'] = influx_url + '/query'
                        node_kwargs['influx_headers'] = influx_headers
                        node_kwargs['influx_org'] = influx_cfg['query_params']['org']
                        node_kwargs['influx_bucket'] = influx_cfg['query_params']['bucket']
                        node_kwargs['topic'] = self.db.get_reading_setting(name=kwargs['input_var'], field='topic')
                    downstream[name] = kwargs.pop('downstream', [])
                    # at this point, the only things left in kwargs should be options the node needs for construction
                    self.logger.debug(f'Kwargs for {name}: {kwargs}')
                    node_kwargs.update(kwargs)
                    n = getattr(Doberman, node_type)(**node_kwargs)
                    if isinstance(n, AlarmNode):
                        n.db = self.db
                    n.load_config(config['node_config'].get(name, {}))
                    self.graph[k] = n
                    if isinstance(n, BufferNode):
                        num_buffer_nodes += 1
                        longest_buffer = max(longest_buffer, n.buffer.length)
            if (nodes_built := (len(self.graph) - start_len)) == 0:
                # we didn't make any nodes this loop, we're probably stuck
                raise ValueError('Can\'t construct graph! Check config')
            else:
                self.logger.debug(f'Created {nodes_built} nodes this iter, {len(self.graph)}/{len(pipeline_config)} total')
        for k,nodes in downstream.items():
            self.graph[k].downstream_nodes = [self.graph[d] for d in nodes]

        self.startup_cycles = num_buffer_nodes + longest_buffer # I think?
        self.logger.debug(f'I estimate we will need {self.startup_cycles} cycles to start')

    def reconfigure(self, doc):
        for node in self.graph.values():
            if node.name in doc:
                node.load_config(doc[node.name])


class Node(object):
    """
    A generic graph node
    """
    def __init__(self, name=None, logger=None, **kwargs):
        self.buffer = _Buffer(1)
        self.name = name
        self.input_var = kwargs.pop('input_var', None)
        self.output_var = kwargs.pop('output_var', self.input_var)
        self.logger = logger
        self.upstream_nodes = kwargs.pop('upstream', [])
        self.downstream_nodes = []
        self.config = {}
        self.is_silent = True

    def _process_base(self, status):
        status = PipelineStatus[status] if isinstance(status, str) else PipelineStatus(status)
        self.is_silent = status == PipelineStatus.silent
        package = self.get_package()
        self.logger.debug(f'Got package: {package}')
        ret = self.process(package)
        if ret is None:
            pass
        elif isinstance(ret, dict):
            package = ret
        else:
            package[self.output_var] = ret
        self.logger.debug(f'Sending downstream: {package}')
        self.send_downstream(package)

    def get_package(self):
        return self.buffer.pop_front()

    def send_downstream(self, package):
        """
        Sends a completed package on to downstream nodes
        """
        for node in self.downstream_nodes:
            node.receive_from_upstream(package)

    def receive_from_upstream(self, package):
        self.buffer.append(package)

    def load_config(self, doc):
        """
        Load whatever runtime values are necessary
        """
        for k,v in doc.values():
            if k == 'length' and isinstance(self, BufferNode):
                self.buffer.set_length(v)
            else:
                self.config[k] = v

    def process(self, package):
        """
        A function for an end-user to implement to do something with the data package
        """
        raise NotImplementedError()

class SourceNode(Node):
    """
    A node that adds data into a pipeline, probably by querying a db or something
    """
    def get_package(self):
        pass

class InfluxSourceNode(SourceNode):
    """
    Queries InfluxDB for the most recent value in some key
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.req_url = kwargs.pop('influx_url')
        self.req_headers = kwargs.pop('influx_headers')
        self.req_params = {'org': kwargs.pop('influx_org')}
        self.req_json = {'bucket': kwargs.pop('influx_bucket'), 'type': 'influxql',
                'query': f"SELECT last(value) FROM {kwargs.pop('topic')} WHERE reading='{self.input_var}';"}
        # note that the single quotes in the query are very important

    def get_package(self):
        x = requests.get(self.req_url, params=self.url_params, headers=self.req_headers, json=self.req_json).json()
        if 'code' in x:
            raise ValueError(f'Didn\'t get any data: {x["message"]}')
        data = x['results'][0]['series'][0] # oh god the formatting of this thing
        if len(data['values'][0]) == 2: # new schema
            date_str, val = data['values'][0]
        else:
            i = [i for i,v in enumerate(data['values'][0]) if v is not None][1]
            date_str, val = data['values'][0][0], data['values'][0][i]
        # date_str looks like YYYY-mm-DDTHH:MM:SS.FFFZ, which doesn't quite work so we strip the 'Z'
        # also sometimes there are only 2 digits of milliseconds, which also doesn't work
        not_ms, ms = date_str.split('.')
        if len(ms) != 4: # 4 is magic number: 3 milliseconds and Z
            ms = ms[:-1] + '0'*(4-len(ms))
        else:
            # just strip the Z
            ms = ms[:-1]
        t = datetime.datetime.fromisoformat(f'{not_ms}.{ms}')
        # TODO make sure t isn't too old
        self.logger.debug(f'{self.name} time {date_str} value {val}')
        return {'time': t, self.output_var: val}

class BufferNode(Node):
    def get_package(self):
        return self.buffer

class LowPassFilter(BufferNode):
    """
    Low-pass filters a value by taking the median of its buffer
    """
    def process(self, packages):
        values = sorted([p[self.input_var] for p in packages])
        l = len(values)
        if l % 2 == 0:
            # even length, we average the two adjacent to the middle
            return (values[l//2 - 1] + values[l//2]) / 2
        else:
            # odd length
            return values[l//2]

class MergeNode(BufferNode):
    """
    Merges packages from two or more upstream nodes into one new package
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.buffer.set_length(len(self.upstream_nodes))

    def merge_time(self, packages):
        # TODO: average time? Take newest? Oldest?
        return sum(p.pop('time') for p in packages)/len(packages)

    def process(self, packages):
        new_package = {'time': self.merge_time(packages)}
        for common_key in set.intersection(set(p.keys() for p in packages)):
            new_package[common_key] = sum(p.pop(common_key) for p in packages)/len(packages)
        for p in packages:
            for k,v in p.items():
                new_package[k] = v
        return new_package

    def load_config(self, config):
        """
        No configurable values for a MergeNode
        """
        return

class IntegralNode(BufferNode):
    """
    Calculates the integral-average of the specified value of the specified duration using the trapzoid rule.
    Divides by the time interval at the end
    """
    def process(self, packages):
        integral = 0
        for i in range(len(packages)-1):
            t0, v0 = packages[i]['time'], packages[i][self.input_var]
            t1, v1 = packages[i+1]['time'], packages[i+1][self.input_var]
            integral += (t1 - t0) * (v1 + v0) * 0.5
        integral = integral/(packages[-1]['time'] - packages[0]['time'])
        xform = self.config.get('transform', [0,1])
        return sum(a*integral**i for i,a in enumerate(xform))

class DifferentialNode(BufferNode):
    """
    Calculates the derivative of the specified value over the specified duration by a chi-square linear fit. DivideByZero error
    is impossible as long as there are at least two values
    """
    def process(self, packages):
        t_min = min(p['time'] for p in packages)
        # we subtract t_min to keep the numbers smaller - result doesn't change and we avoid floating-point issues
        # that might show up when we multiply large floats together
        t = [p['time']-t_min for p in packages]
        y = [p[self.input_var] for p in packages]
        B = sum(v*v for v in t)
        C = len(packages)
        D = sum(tt*vv for (tt,vv) in zip(t,y))
        E = sum(y)
        F = sum(t)
        slope = (D*C-E*F)/(B*C - F*F)
        xform = self.config.get('transform', [0,1])
        return sum(a*slope**i for i,a in enumerate(xform))

class AlarmNode:
    """
    An empty base class to handle database access
    """
    pass

class SimpleAlarmNode(BufferNode, AlarmNode):
    """
    A simple alarm
    """
    def process(self, packages):
        values = [p[self.input_var] for p in packages]
        level = -1
        alarm_levels = self.config.get('alarm_levels', [])
        try:
            for i, (low, high) in enumerate(alarm_levels):
                if any([low <= v <= high for v in values]):
                    # at least one value is in an acceptable range
                    pass
                else:
                    level = max(i, level)
            if level >= 0 and not self.is_silent:
                msg = f'Alarm for {} measurement {} ({desc}) - {values[-1]} is outside the specified range ({alarm_levels[level]})'
                self.db.log_alarm() # TODO
        except Exception as e:
            self.logger.debug(f'Caught a {type(e)} while processing alarms: {e}')
            self.logger.debug(f'Alarm levels: {alarm_levels}, values: {values}')

class TimeSinceNode(BufferNode):
    """
    Checks to see if the desired value is within a range
    """
    def process(self, packages):
        # TODO
        pass

class _Buffer(object):
    """
    A custom semi-fixed-width buffer that keeps itself sorted
    """
    def __init__(self, length):
        self._buf = []
        self.length = length

    def __len__(self):
        return len(self._buf)

    def append(self, obj):
        """
        Adds a new object to the queue, time-sorted
        """
        LARGE_NUMBER = 1e12  # you shouldn't get timestamps larger than this
        if len(self._buf) == 0:
            self._buf.append(obj)
        elif len(self._buf) == 1:
            if self._buf[0]['time'] >= obj['time']:
                self._buf.insert(0, obj)
            else:
                self._buf.append(obj)
        else:
            idx = len(self._buf)//2
            for i in itertools.count(2):
                lesser = self._buf[idx-1]['time'] if idx > 0 else -1
                greater = self._buf[idx]['time'] if idx < len(self._buf) else LARGE_NUMBER
                if lesser <= obj['time'] <= greater:
                    self._buf.insert(idx, obj)
                    break
                elif obj['time'] > greater:
                    idx += max(1, len(self._buf)>>i)
                elif obj['time'] < lesser:
                    idx -= max(1, len(self._buf)>>i)
        if len(self._buf) > self.length:
            self._buf = self._buf[-self.length:]
        return

    def pop_front(self):
        return self._buf.pop(0)

    def __getitem__(self, index):
        return self._buf[index]

    def set_length(self, length):
        self.length = length

    def __iter__(self):
        return self._buf.__iter__()
