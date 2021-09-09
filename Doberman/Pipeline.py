import Doberman
import requests
import time
import itertools


class Pipeline(object):
    """
    A generic data-processing pipeline graph intended to replace Storm
    """
    def __init__(self, **kwargs):
        self.graph = {}
        self.db = kwargs['db']
        self.logger = kwargs['logger']

    def process_cycle(self):
        timing = {}
        for node in self.graph.values():
            t_start = time.time()
            node._process_base()
            t_end = time.time()
            timing[node.name] = (t_end-t_start)*1000
        self.logger.debug('Processing time: total {sum(timing.values()):.3f} ms, individual {timing}')

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
                        # TODO add db credentials and url
                        node_kwargs['db'] = 'pancake'
                        node_kwargs['influx_username'] = ''
                        node_kwargs['influx_password'] = ''
                        node_kwargs['influx_url'] = ''
                    downstream[name] = kwargs.pop('downstream', [])
                    # at this point, the only things left in kwargs should be options the node needs for construction
                    self.logger.debug(f'Kwargs for {name}: {kwargs}')
                    node_kwargs.update(kwargs)
                    n = getattr(Doberman, node_type)(**node_kwargs)
                    if isinstance(n, AlarmNode):
                        n.db = self.db
                    n.load_config(config['node_config'].get(name, {}))
                    self.graph[k] = n
            if (nodes_built := (len(self.graph) - start_len)) == 0:
                # we didn't make any nodes this loop, we're probably stuck
                raise ValueError('Can\'t construct graph! Check config')
            else:
                self.logger.debug(f'Created {nodes_built} nodes this iter, {len(self.graph)}/{len(pipeline_config)} total')
        for k,nodes in downstream.items():
            self.graph[k].downstream_nodes = [self.graph[d] for d in nodes]

    def reconfigure(self, doc):
        for node in self.graph.values():
            if node.name in doc:
                node.load_config(doc[node.name])

    def run(self):
        # TODO
        pass


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

    def _process_base(self):
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
    A node that adds data into a pipeline, probably by querying a db or kafka or something
    """
    def get_package(self):
        pass

class KafkaSourceNode(SourceNode):
    pass

class InfluxSourceNode(SourceNode):
    """
    Queries InfluxDB for the most recent value in some key
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url = kwargs.pop('influx_url')
        self.url_params = {'db': kwargs.pop('influx_db'), 'u': kwargs.pop('influx_username'), 'p': kwargs.pop('influx_password'),
                'q':"SELECT {} FROM {} WHERE {} ORDER BY time DESC LIMIT 1"} # TODO

    def get_package(self):
        r = requests.get(self.url, params=self.url_params)
        # TODO make sure status is 200
        data = r.json()['results'][0]['series'][0] # oh god the formatting of this thing
        date_str = data['values'][0][0]
        # date_str looks like YYYY-mm-DDTHH:MM:SS.FFZ, which doesn't quite work
        # so we strip the 'Z' and add an extra 0 so it ends with .FFF
        t = datetime.datetime.fromisoformat(data_str[:-1] + '0').timestamp()
        # TODO make sure t isn't too old
        column_i = data['columns'].index(self.input_var)
        return {'time': t, self.output_var: data['series'][0]['values'][0][column_i]}

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
            return (values[l//2] + values[l//2 + 1]) / 2
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
            t1, v1 = packages[i+1]['time'], packages[i][self.input_var]
            integral += (t1 - t0) * (v1 + v0) * 0.5
        integral = integral/(packages[-1]['time'] - packages[0]['time'])
        a,b = self.config.get('transform', [1,0])
        return a*integral + b

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
        a,b = self.config.get('transform', [1,0])
        return a*slope + b

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
        alarm_level = -1
        for i, (low, high) in enumerate(self.alarm_levels):
            if any([low <= v <= high for v in values]):
                # at least one value is in an acceptable range
                pass
            else:
                alarm_level = max(i, alarm_level)
        if alarm_level >= 0:
            msg = f'Alarm for {} measurement {} ({desc}) - {values[-1]} is outside the specified range ({self.alarm_levels[alarm_level]})'
            self.db.log_alarm() # TODO

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
