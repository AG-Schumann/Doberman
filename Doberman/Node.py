import Doberman
import requests
import socket
import threading


class Node(object):
    """
    A generic graph node
    """
    def __init__(self, pipeline=None, name=None, logger=None, **kwargs):
        self.pipeline = pipeline
        self.buffer = Doberman.utils.SortedBuffer(1)
        self.name = name
        self.input_var = kwargs.pop('input_var', None)
        self.output_var = kwargs.pop('output_var', self.input_var)
        self.logger = logger
        self.upstream_nodes = kwargs.pop('_upstream', [])
        self.downstream_nodes = []
        self.config = {}
        self.is_silent = True
        self.logger.debug(f'{name} constructor')

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass

    def setup(self, **kwargs):
        """
        Allows a child class to do some setup
        """
        pass

    def shutdown(self):
        """
        Allows a child class to do some shutdown
        """
        pass

    def _process_base(self, status):
        self.logger.debug(f'{self.name} processing')
        self.is_silent = status == 'silent'
        package = self.get_package() # TODO discuss this wrt BufferNodes
        ret = self.process(package)
        if ret is None:
            pass
        elif isinstance(ret, dict):
            package = dict(ret)
        else: # ret is a number or something
            if isinstance(self, BufferNode):
                package = package[-1]
            package[self.output_var] = ret
        self.send_downstream(package)
        self.post_process()

    def get_package(self):
        return self.buffer.get_front()

    def send_downstream(self, package):
        """
        Sends a completed package on to downstream nodes
        """
        #self.logger.debug(f'{self.name} sending downstream {package}')
        for node in self.downstream_nodes:
            node.receive_from_upstream(package)

    def receive_from_upstream(self, package):
        #self.logger.debug(f'{self.name} receiving from upstream')
        self.buffer.add(package)

    def load_config(self, doc):
        """
        Load whatever runtime values are necessary
        """
        for k,v in doc.items():
            if k == 'length' and isinstance(self, BufferNode):
                self.buffer.set_length(int(v))
            else:
                self.config[k] = v

    def process(self, package):
        """
        A function for an end-user to implement to do something with the data package
        """
        raise NotImplementedError()

    def post_process(self):
        """
        Anything a node wants to do after sending its result downstream
        """
        pass

    def on_error_do_this(self):
        """
        If the pipeline errors, do this thing (ie, closing a valve).
        Only really makes sense for ControlNodes
        """
        pass

class SourceNode(Node):
    """
    A node that adds data into a pipeline, probably by querying a db or something
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        if kwargs.get('new_value_required', False):
            self.pipeline.required_inputs.add(self.name)

    def process(self, *args, **kwargs):
        return None

class InfluxSourceNode(SourceNode):
    """
    Queries InfluxDB for the most recent value in some key

    Setup params:
    :param topic: the value's topic
    :param influx_cfg: the document containing influx config params
    :param accept_old: bool, default False. If you don't get a new value from the database,
        is this ok?

    Required params in the influx config doc:
    :param url: http://address:port
    :param version: which major version of InfluxDB you use, either 1 or 2 (note that v1.8 counts as 2)
    :param db: the mapped database name corresponding to your bucket and retention policy,
        see https://docs.influxdata.com/influxdb/cloud/query-data/influxql/ (InfluxDB >= v1.8)
    :param org: the name of the organization (probably your experiment name) (InfluxDB >= v1.8)
    :param token: the auth token (InfluxDB >= v1.8)
    :param username: the username (InfluxDB < 1.8)
    :param password: the password (InfluxDB < 1.8)
    :param database: the database (InfluxDB < 1.8)
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        if self.input_var.startswith('X_SYNC_'):
            raise ValueError('Cannot use Influx for SYNC signals')
        self.accept_old = kwargs.get('accept_old', False)
        config_doc = kwargs['influx_cfg']
        topic = kwargs['topic']
        if config_doc.get('schema', 'v2') == 'v1':
            variable = self.input_var
            where = ''
        else:
            variable = 'value'
            # note that the single quotes in the WHERE clause are very important
            # see https://docs.influxdata.com/influxdb/v1.8/query_language/explore-data/#a-where-clause-query-unexpectedly-returns-no-data
            where = f"WHERE sensor='{self.input_var}'"
        query = f'SELECT last({variable}) FROM {topic} {where};'
        url = config_doc['url'] + '/query?'
        headers = {'Accept': 'application/csv'}
        params = {'q': query}
        if (version := config_doc.get('version', 2)) == 1:
            params['u'] = config_doc['username']
            params['p'] = config_doc['password']
            params['db'] = config_doc['database']
        elif version == 2:
            # even though you're using influxv2 we still use the v1 query endpoint
            # because the v2 query is bad and should feel bad
            params['db'] = config_doc['db']
            params['org'] = config_doc['org']
            headers['Authorization'] = f'Token {config_doc["token"]}'
        else:
            raise ValueError("Invalid version specified: must be 1 or 2")

        self.req_url = url
        self.req_headers = headers
        self.req_params = params
        self.last_time = 0

    def get_from_influx(self):
        response = requests.get(self.req_url, headers=self.req_headers, params=self.req_params)
        try:
            timestamp, val = response.content.decode().splitlines()[1].split(',')[-2:]
        except Exception as e:
            raise ValueError(f'Error parsing data: {response.content}')
        timestamp = int(timestamp)
        self.logger.debug(f'{self.name} got timestamp {timestamp}')
        val = float(val) # 53 bits of precision and we only ever have small integers
        return timestamp, val

    def get_package(self):
        timestamp, val = self.get_from_influx()
        if self.last_time == timestamp and not self.accept_old:
            # try again, in the 10ms or so a new value may have just arrived
            timestamp, val = self.get_from_influx()
            if self.last_time == timestamp:
                # still nothing
                raise ValueError(f'{self.name} didn\'t get a new value for {self.input_var}!')
        self.last_time = timestamp
        self.logger.debug(f'{self.name} time {timestamp} value {val}')
        return {'time': timestamp*(10**-9), self.output_var: val}

class SensorSourceNode(SourceNode):
    """
    A node to support synchronous pipeline input directly from the sensors
    """
    def shutdown(self):
        self.pipeline.monitor.unregister_listener(self)

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.cv = kwargs['cv']
        self.pipeline.monitor.register_listener(self.input_var, self)

    def receive_from_upstream(self, package):
        """
        This won't get called from the "operating" thread so we 
        wrap with CV
        """
        with self.cv:
            if package[self.input_var] is not None or self.accept_old:
                super().receive_from_upstream(package)
                # let the pipeline know that we've got mail
                self.pipeline.has_new.add(self.name)
            self.cv.notify()

class PipelineSourceNode(SourceNode):
    """
    A node to source info about another pipeline.
    The input_var is the name of another PL
    """
    def setup(**kwargs):
        super().setup(**kwargs)
        self.get_from_db = kwargs['get_pipeline_stats']

    def get_package(self):
        doc = self.get_from_db(self.input_var)
        # TODO discuss renaming fields?
        return doc

class BufferNode(Node):
    """
    A node that supports inputs spanning some range of time

    Setup params:
    :param strict_length: bool, default False. Is the node allowed to run without a 
        full buffer?

    Runtime params:
    :param length: int, how many values to buffer
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.strict = kwargs.get('strict_length', False)

    def get_package(self):
        if self.strict and len(self.buffer) != self.buffer.length:
            raise ValueError(f'{self.name} is not full')
        # deep copy
        return list(map(dict, self.buffer))

class MedianFilter(BufferNode):
    """
    Filters a value by taking the median of its buffer. If the length is even,
    the two values adjacent to the middle are averaged.

    Setup params:
    :param strict_length: bool, default False. Is the node allowed to run without a 
        full buffer?

    Runtime params:
    :param length: int, how many values to buffer
    """
    def process(self, packages):
        values = sorted([p[self.input_var] for p in packages])
        if (l := len(values)) % 2 == 0:
            # even length, we average the two adjacent to the middle
            return (values[l//2 - 1] + values[l//2]) / 2
        else:
            # odd length
            return values[l//2]

class MergeNode(BufferNode):
    """
    Merges packages from two or more upstream nodes into one new package. This is
    necessary to merge streams from different Input nodes without mangling timestamps

    Setup params:
    :param merge_how: string, how to merge timestamps, one of "avg", "min", "max", "newest", or "oldest". Default 'avg'

    Runtime params:
    None
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.buffer.set_length(len(self.upstream_nodes))

    def post_process(self):
        self.buffer.clear()

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.strict = True
        self.method = kwargs.get('merge_how', 'avg')

    def merge_field(self, field, packages):
        how = self.method
        if how == 'avg':
            return sum(p[field] for p in packages)/len(packages)
        if how == 'min':
            return min(p[field] for p in packages)
        if how == 'max':
            return max(p[field] for p in packages)
        if how == 'newest':
            return packages[-1][field]
        if how == 'oldest':
            return packages[0][field]
        raise ValueError(f'Invalid merge method given: {how}. Must be "avg", "max", "min", "newest", or "oldest"')

    def process(self, packages):
        new_package = {}
        common_keys = set(packages[0].keys())
        uncommon_keys = set(packages[0].keys())
        for p in packages[1:]:
            common_keys &= set(p.keys())
            uncommon_keys ^= set(p.keys())
        for key in common_keys:
            new_package[key] = self.merge_field(key, packages)
        for p in packages:
            for k,v in p.items():
                if k in common_keys:
                    continue
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

    Setup params:
    :param length: the number of values over which you want the integral calculated.
        You'll need to do the conversion to time yourself
    :param strict_length: bool, default False. Is the node allowed to run without a 
        full buffer?

    Runtime params:
    :param t_offset: Optional. How many of the most recent values you want to skip.
        The integral is calculated up to t_offset from the end of the buffer
    """
    def process(self, packages):
        offset = int(self.config.get('t_offset', 0))
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

    Setup params:
    :param length: The number of values over which you want the derivative calculated.
        You'll need to do the conversion to time yourself.
    :param strict_length: bool, default False. Is the node allowed to run without a 
        full buffer?

    Runtime params:
    None
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

    Setup params:
    None

    Runtime params:
    :param transform: list of numbers, the little-endian-ordered coefficients. The
        calculation is done as a*v**i for i,a in enumerate(transform), so to output a 
        constant you would specity [value], to leave the input unchanged you would
        specify [0, 1], a quadratic could be [c, b, a], etc
    """
    def process(self, package):
        xform = self.config.get('transform', [0,1])
        return sum(a*package[self.input_var]**i for i,a in enumerate(xform))

class InfluxSinkNode(Node):
    """
    Puts a value back into influx.

    Setup params:
    :param topic: string, the type of measurement (temperature, pressure, etc)
    :param subsystem: string, the subsystem the quantity belongs to
    :param device: string, optional. The name of the device this quantity "comes from", defaults to "pipeline"

    Runtime params:
    None
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.topic = kwargs['topic']
        self.subsystem = kwargs['subsystem']
        self.write_to_influx = kwargs['write_to_influx']
        self.device = kwargs.get('device', 'pipeline')

    def process(self, package):
        if not self.is_silent:
            self.logger.debug(f'{self.topic}, {self.subsystem}, {self.device}, {self.input_var}')
            self.write_to_influx(topic=self.topic, tags={'sensor': self.output_var,
                'device': self.device, 'subsystem': self.subsystem},
                fields={'value': package[self.input_var[0]]}, timestamp=package['time'])

class EvalNode(Node):
    """
    An evil node that executes an arbitrary operation specified by the user.
    Room for abuse, probably, but we aren't designing for protection against
    malicious actors with system access.

    Setup params:
    :param operation: string, the operation you want performed. Input values will be 
        assembed into a dict "v", and any constant values specified will be available as
        described below.
        For instance, "(v['input_1'] > c['min_in1']) and (v['input_2'] < c['max_in2'])"
        or "math.exp(v['input_1'] + c['offset'])". The math library is available for use.
    :param output_var: string, the name to assign to the output variable

    Runtime params:
    :param c: dict, optional. Some constant values you want available for the operation.
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.operation = kwargs['operation']

    def process(self, package):
        c = self.config.get('c', {})
        for k, v in c.items():
            # the website casts things as strings because fuck you, so we float them here
            c[k] = float(v)
        v = {k:package[k] for k in self.input_var}
        return eval(self.operation)
