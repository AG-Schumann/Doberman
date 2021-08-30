import Doberman



class Pipeline(object):
    """
    A generic data-processing pipeline graph intended to replace Storm
    """
    def __init__(self, *args, **kwargs):
        self.graph = {}
        pass

    def process_cycle(self):
        for node in self.graph.values():
            node._process_base()

    def build(self, config):
        """
        Generates the graph based on the input config, which looks like this:
        {
            name: ([upstream node names], [downstream node names]),
            name: ...
        }
        We generate nodes in such an order that we can just loop over them in the order of their construction
        and guarantee that everything that this node depends on has already run this loop
        """
        while len(self.graph) != len(config):
            start_len = len(self.graph)
            for k, (upstream, _) in config.items():
                if k in self.graph:
                    continue
                if len(upstream) == 0:
                    # we found a source node
                    self.graph[k] = SourceNode()
                if all([u in self.graph for u in upstream]):
                    # all this node's requirements are created
                    n = Node()
                    for u in upstream:
                        n.upstream_nodes.append(self.graph[n])
                    self.graph[k] = n
            if len(self.graph) == start_len:
                # we didn't make any nodes this loop, we're probably stuck
                raise ValueError('Can\'t construct graph!')
        for k,(_, downstream) in config.items():
            for d in downstream:
                self.graph[k].downstream_nodes.append(self.graph[d])

        self.reconfigure()

    def reconfigure(self):
        doc = None
        for node in self.graph.values():
            node.reconfigure(doc)

class Node(object):
    """
    A generic graph node
    """
    def __init__(self, *args, **kwargs):
        self.buffer = Buffer(1)
        self.name = kwargs.pop('name')
        self.upstream_nodes = []
        self.downstream_nodes = []

    def _process_base(self):
        package = self.get_package()
        package = self._process_child(package)
        ret = self.process(package)
        if isinstance(ret, dict):
            package = ret
        else:
            package[self.name] = ret
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

    def reconfigure(self, doc):
        pass

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

class OutputNode(Node):
    """
    A node that doesn't send data back into the pipeline
    """
    def send_downstream(self, package):
        pass

class MergeNode(Node):
    """
    Merges packages from two or more upstream nodes into one new package
    """
    def __init__(self):
        super().__init__()
        self.buffer.set_length(len(self.upstream_nodes))

    def get_package(self):
        return self.buffer

    def process(self, packages):
        new_package = {'time': 0}
        # TODO: average time? Take newest? Oldest?
        new_package['time'] = sum(p.pop('time') for p in packages)/len(packages)
        for common_key in set.intersection(set(p.keys() for p in packages)):
            new_package[common_key] = sum(p.pop(common_key) for p in packages)/len(packages)
        for p in packages:
            for k,v in p.items():
                new_package[k] = v
        return new_package


class ActionNode(Node):
    """
    This node makes a decision about its input and does something
    """
    pass

class BufferNode(Node):
    def __init__(self):
        super().__init__()
        self.buffer.set_length(length)

class IntegralNode(BufferNode):
    """
    Calculates the integral-average of the specified value of the specified duration using the trapzoid rule.
    Divides by the time interval at the end
    """
    def process(self, packages):
        integral = 0
        xy = [(pkg['time'], pkg[self.value_key]) for pkg in packages]
        for i, (t0,v0) in xy[:-1]:
            t1,v1 = xy[i+1]
            integral += (t1 - t0) * (v1 + v0)/2
        return integral/(xy[-1][0] - xy[0][0])

class DifferentialNode(BufferNode):
    """
    Calculates the derivative of the specified value over the specified duration by a chi-square linear fit
    """
    def process(self, packages):
        t_min = min(pkg['time'] for pkg in packages)
        t = [pkg['time']-t_min for pkg in packages] # subtract t_min to keep the numbers smaller - result doesn't change
        y = [pkg[self.value_key] for pkg in packages]
        B = sum(v*v for v in t)
        C = len(packages)
        D = sum(tt*vv for (tt,vv) in zip(t,y))
        E = sum(y)
        F = sum(t)
        return (D*C-E*F)/(B*C - F*F)

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
            self._buf.pop(0)
        return

    def pop_front(self):
        return self._buf.pop(0)

    def pop_back(self):
        return self._buf.pop()

    def __getitem__(self, index):
        return self._buf[index]

    def set_length(self, length):
        self.length = length

    def __iter__(self):
        return self._buf.__iter__()
