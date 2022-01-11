import Doberman
import requests
import itertools

class Node(object):
    """
    A generic graph node
    """
    def __init__(self, pipeline=None, name=None, logger=None, **kwargs):
        self.pipeline = pipeline
        self.buffer = _Buffer(1)
        self.name = name
        self.input_var = kwargs.pop('input_var', None)
        self.output_var = kwargs.pop('output_var', self.input_var)
        self.logger = logger
        self.upstream_nodes = kwargs.pop('_upstream', [])
        self.downstream_nodes = []
        self.config = {}
        self.is_silent = True
        self.logger.debug(f'{name} constructor')

    def setup(self, **kwargs):
        """
        Allows a child class to do some setup
        """
        pass

    def _process_base(self, status):
        self.logger.debug(f'{self.name} processing')
        self.is_silent = status == 'silent'
        package = self.get_package() # TODO discuss this wrt BufferNodes
        self.logger.debug(f'{self.name} input {package}')
        ret = self.process(package)
        self.logger.debug(f'{self.name} output {ret}')
        if ret is None:
            pass
        elif isinstance(ret, dict):
            package = ret
        else:
            if isinstance(self, BufferNode):
                package = package[-1]
            package[self.output_var] = ret
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
        for k,v in doc.items():
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
    def process(self):
        return None

class InfluxSourceNode(SourceNode):
    """
    Queries InfluxDB for the most recent value in some key
    """
    def setup(self, **kwargs):
        """
        How we actually make the request changes depending on what version of influx and schema is used
        :param topic: the reading's topic
        :param config_doc: the influx document from experiment_config
        :return: none
        """
        super().setup(**kwargs)
        config_doc = kwargs['config_doc']
        topic = kwargs['topic']
        if config_doc.get('schema', 'new') == 'old':
            variable = self.input_var
            where = ''
        else:
            variable = 'value'
            # note that the single quotes in the WHERE clause are very important
            # see https://docs.influxdata.com/influxdb/v1.8/query_language/explore-data/#a-where-clause-query-unexpectedly-returns-no-data
            where = f"WHERE reading='{self.input_var}'"
        query = f'SELECT last({variable}) FROM {topic} {where};'
        url = config_doc['url'] + '/query?'
        headers = {'Accept': 'application/csv'}
        if (version := config_doc.get('version', 2)) == 1:
            url += f'u={config_doc["username"]}&p={config_doc["password"]}&db={config_doc["database"]}&q={query}'
            json = {}
        elif version == 2:
            # even though you're using influxv2 we still use the v1 query endpoint
            # because the v2 query is garbage for our purposes
            url += f'db={config_doc["org"]}' # org -> db, because reasons
            headers.update({'Authorization': f'Token {config_doc["auth_token"]}'})
            json = {'q': query}
        else:
            raise ValueError("Invalid version specified: must be 1 or 2")
        self.precision = int({'s': 1, 'ms': 1e3, 'us': 1e6, 'ns': 1e9}[config_doc['precision']])

        self.req_url = url
        self.req_headers = headers
        self.req_json = json
        self.last_time = 0

    def get_package(self):
        response = requests.get(self.req_url, headers=self.req_headers, json=self.req_json)
        try:
            timestamp, val = response.content.decode().splitlines()[1].split(',')[-2:]
        except Exception as e:
            raise ValueError(f'Error parsing data: {response.content}')

        timestamp = int(timestamp) # TODO this might be broken because influx and ns
        # timestamp = int(timestamp[:-(9-int(np.log10(self.precision)))])
        val = int(val) if '.' not in val else float(val)
        if self.last_time == timestamp:
            raise ValueError(f'{self.name} didn\'t get a new value for {self.input_var}!')
        self.last_time = timestamp
        self.logger.debug(f'{self.name} time {timestamp} value {val}')
        return {'time': timestamp/self.precision, self.output_var: val}

class BufferNode(Node):
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.strict = kwargs.get('strict_length', False)

    def get_package(self):
        if self.strict and len(self.buffer) != self.buffer.length:
            raise ValueError(f'{self.name} is not full')
        # deep copy because the MergeNode will change its input
        return list(map(dict, self.buffer))

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
        common_keys = set(packages[0].keys())
        for p in packages[1:]:
            common_keys &= set(p.keys())
        for key in common_keys:
            # average other common keys
            new_package[key] = sum(p.pop(key) for p in packages)/len(packages)
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
    Divides by the time interval at the end. Supports a 't_offset' config value, which is some time offset
    from the end of the buffer.
    """
    def process(self, packages):
        offset = self.config.get('t_offset', 0)
        t = [p['time'] for p in packages]
        v = [p[self.input_var] for p in packages]
        integral = sum((t[i] - t[i-1]) * (v[i] + v[i-1]) * 0.5 for i in range(1, len(packages)-offset))
        integral /= (t[0] - t[-1-offset])
        return integral

class DerivativeNode(BufferNode):
    """
    Calculates the derivative of the specified value over the specified duration by a chi-square linear fit to
    minimize the impact of noise. DivideByZero error is impossible as long as there are at least two values in
    the buffer
    """
    def process(self, packages):
        t_min = packages[0]['time']
        # we subtract t_min to keep the numbers smaller - result doesn't change and we avoid floating-point
        # issues that can show up when we multiply large floats together
        t = [p['time']-t_min for p in packages]
        y = [p[self.input_var] for p in packages]
        B = sum(v*v for v in t)
        C = len(packages)
        D = sum(tt*vv for (tt,vv) in zip(t,y))
        E = sum(y)
        F = sum(t)
        slope = (D*C-E*F)/(B*C - F*F)
        return slope

class PolynomialNode(Node):
    """
    Does a polynomial transformation on a value
    """
    def process(self, package):
        xform = self.config.get('transform', [0,1])
        return sum(a*package[self.input_var]**i for i,a in enumerate(xform))

class InfluxSinkNode(Node):
    """
    Puts a value back into influx
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.topic = kwargs['topic']
        self.write_to_influx = kwargs['write_to_influx']

    def process(self, package):
        if not self.is_silent:
            self.write_to_influx(topic=self.topic, tags={'reading': self.output_var, 'sensor': 'pipeline'},
                                fields={'value': package[self.input_var]}, timestamp=package['time'])

class EvalNode(Node):
    """
    An evil node that executes an arbitrary operation specified by the user
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.operation = kwargs['operation']

    def process(self, package):
        v = [package[i] for i in self.input_var]
        c = self.config.get('c', [])
        return eval(self.operation)

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

    def __str__(self):
        return str(list(map(str, self._buf)))
