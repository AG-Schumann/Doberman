import Doberman



class Pipeline(object):
    """
    A generic data-processing pipeline graph intended to replace Storm
    """
    def __init__(self, *args, **kwargs):
        self.graph = {}
        self.logger = Doberman.utils.get_logger('Pipeline')

    def process_cycle(self):
        for node in self.graph.values():
            node._process_base()

    def build(self, config):
        """
        Generates the graph based on the input config, which looks like this:
        {
            name: (type, [upstream node names], [downstream node names]),
            name: ...
        }
        'type' is the type of Node ('Node', 'MergeNode', etc), [node names] is a list of names of the immediate up- and down-stream nodes.
        We generate nodes in such an order that we can just loop over them in the order of their construction
        and guarantee that everything that this node depends on has already run this loop
        """
        while len(self.graph) != len(config):
            start_len = len(self.graph)
            for name, (node_type, upstream, _) in config.items():
                if name in self.graph:
                    continue
                if len(upstream) == 0:
                    # we found a source node
                    self.graph[name] = SourceNode(name=name)
                if all([u in self.graph for u in upstream]):
                    # all this node's requirements are created
                    n = Node() # TODO do this correctly with node_type
                    for u in upstream:
                        n.upstream_nodes.append(self.graph[n])
                    self.graph[k] = n
            if len(self.graph) == start_len:
                # we didn't make any nodes this loop, we're probably stuck
                raise ValueError('Can\'t construct graph!')
        for k,(_, _, downstream) in config.items():
            for d in downstream:
                self.graph[k].downstream_nodes.append(self.graph[d])

        self.reconfigure()

    def reconfigure(self):
        doc = None # TODO
        for node in self.graph.values():
            node.reconfigure(doc)

class Node(object):
    """
    A generic graph node
    """
    def __init__(self, name=None, input_var=None, logger=None, **kwargs):
        self.buffer = Buffer(1)
        self.name = name
        self.input_var = input_var
        self.output_var = kwargs.get('output_var', input_var)
        self.logger = logger
        self.upstream_nodes = []
        self.downstream_nodes = []

    def _process_base(self):
        package = self.get_package()
        self.logger.debug(f'Got package: {package}')
        package = self._process_child(package)
        ret = self.process(package)
        if ret is None:
            pass
        elif isinstance(ret, dict):
            package = ret
        else:
            package[self.output_var] = ret
        self.send_downstream(package)

    def _process_child(self, package):
        return package

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

    def _load_config(self, doc):
        self.load_config(doc)

    def load_config(self, doc):
        """
        Load whatever runtime values are necessary
        """
        pass

    def process(self, package):
        """
        A function for an end-user to implement to do something with the data package
        """
        raise NotImplementedError()

class OperatorNode(Node):
    """
    This node does an operation on input
    """
    def load_config(self, doc):
        op = doc['operation']


    def process(self, package):
        return self.func(package[self.var])

class SourceNode(Node):
    """
    A node that adds data into a pipeline, probably by querying a db or kafka or something
    """
    def get_package(self):
        pass

class KafkaSourceNode(Node):
    def get_package(self):
        pass

class InfluxSourceNode(Node):
    def get_package(self):
        pass

class BufferNode(Node):
    def load_config(self, config):
        self.buffer.set_length(config['length'])

class MergeNode(BufferNode):
    """
    Merges packages from two or more upstream nodes into one new package
    """
    def get_package(self):
        return self.buffer

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

    def set_config(self, config):
        pass

class MergeAndSumNode(MergeNode):
    """
    Similar to a merge node, but adds all the values together
    """
    def process(self, packages):
        new_package = {'time': self.merge_time(packages)}
        val = 0
        for p in packages:
            for n in self.upstream_nodes:
                if n in p:
                    val += p[n]
                    break
        new_package[self.output_name] = val
        return new_package

class ActionNode(Node):
    """
    This node makes a decision about its input and does something
    """
    pass

class IntegralNode(BufferNode):
    """
    Calculates the integral-average of the specified value of the specified duration using the trapzoid rule.
    Divides by the time interval at the end
    """
    def load_config(self, config):
        self.scale = config.get('scale', 1.)
        self.buffer.set_length(config.get('length', len(self.buffer)))

    def process(self, packages):
        integral = 0
        for i in range(len(packages)-1):
            t0, v0 = packages[i]['time'], packages[i][self.input_key]
            t1, v1 = packages[i+1]['time'], packages[i][self.input_key]
            integral += (t1 - t0) * (v1 + v0) * 0.5
        return self.scale*integral/(packages[-1]['time'] - packages[0]['time'])

class DifferentialNode(BufferNode):
    """
    Calculates the derivative of the specified value over the specified duration by a chi-square linear fit. DivideByZero error
    is impossible as long as there are at least two values
    """
    def load_config(self, config):
        self.scale = config.get('scale', 1.)
        self.buffer.set_length(config.get('length', len(self.buffer)))

    def process(self, packages):
        t_min = min(pkg['time'] for pkg in packages)
        t = [pkg['time']-t_min for pkg in packages] # subtract t_min to keep the numbers smaller - result doesn't change
        y = [pkg[self.input_key] for pkg in packages]
        B = sum(v*v for v in t)
        C = len(packages)
        D = sum(tt*vv for (tt,vv) in zip(t,y))
        E = sum(y)
        F = sum(t)
        return self.scale*(D*C-E*F)/(B*C - F*F)

class TimeSinceNode(BufferNode):
    """
    Checks to see if the desired value is within a range
    """
    def process(self, packages):
        pass

class Buffer(object):
    """
    A custom semi-fixed-width buffer
    """
    def __init__(self, length):
        self._buf = []
        self.length = length

    def __len__(self):
        return len(self._buf)

    def append(self, obj):
        self._buf.append(obj)
        while len(self._buf) > self.length:
            self.pop_front()
        return

    def pop_front(self):
        return self._buf.pop(0)

    def __getitem__(self, index):
        return self._buf[index]

    def set_length(self, length):
        self.length = length

    def __iter__(self):
        return self._buf.__iter__()
