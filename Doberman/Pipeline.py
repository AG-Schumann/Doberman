import Doberman
import time

__all__ = 'Pipeline'.split()

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
        self.last_error = -1

    def stop(self):
        try:
            self.db.set_pipeline_value(self.name, [('status', 'inactive')])
        except Exception as e:
            pass

    def process_cycle(self):
        """
        This function gets Registered with the owning PipelineMonitor
        """
        doc = self.db.get_pipeline(self.name)
        self.reconfigure(doc['node_config'])
        status = 'silent' if self.cycles <= self.startup_cycles else doc['status']
        timing = {}
        self.logger.debug(f'Pipeline {self.name} cycle {self.cycles}')
        for node in self.graph.values():
            t_start = time.time()
            try:
                node._process_base(status)
            except Exception as e:
                self.last_error = self.cycles
                msg = f'Pipeline {self.name} node {node.name} threw {type(e)}: {e}'
                if self.cycles <= self.startup_cycles:
                    # we expect errors during startup as buffers get filled
                    self.logger.debug(msg)
                else:
                    self.logger.warning(msg)
                break # probably shouldn't finish the cycle if something errored
            t_end = time.time()
            timing[node.name] = (t_end-t_start)*1000
        total_timing = ', '.join(f'{k}: {v:.1f}' for k,v in timing.items())
        self.logger.debug(f'Processing time: total {sum(timing.values()):.1f} ms, individual {total_timing}')
        self.cycles += 1
        self.db.set_pipeline_value(self.name,
                [('heartbeat', Doberman.utils.dtnow()),
                    ('cycles', self.cycles),
                    ('error', self.last_error),
                    ('rate', sum(timing.values()))])
        drift = 0.001 # 1ms extra per cycle, so we don't accidentally get ahead of the new values
        return max(self.db.get_sensor_setting(name=n, field='readout_interval') for n in self.depends_on) + drift

    def build(self, config):
        """
        Generates the graph based on the input config, which looks like this:
        [
            {
                "name": <name>,
                "type: <node type>,
                "upstream": [upstream node names],
                **kwargs
            },
        ]
        'type' is the type of Node ('Node', 'MergeNode', etc), [node names] is a list of names of the immediate neighbor nodes,
        and kwargs is whatever that node needs for instantiation
        We generate nodes in such an order that we can just loop over them in the order of their construction
        and guarantee that everything that this node depends on has already run this loop
        """
        pipeline_config = config['pipeline']
        self.logger.debug(f'Loading graph config, {len(pipeline_config)} nodes total')
        num_buffer_nodes = 0
        longest_buffer = 0
        influx_cfg = self.db.get_experiment_config('influx')
        alarm_cfg = self.db.get_experiment_config('alarm')
        self.depends_on = config['depends_on']
        while len(self.graph) != len(pipeline_config):
            start_len = len(self.graph)
            for kwargs in pipeline_config:
                if kwargs['name'] in self.graph:
                    continue
                upstream = kwargs.get('upstream', [])
                existing_upstream = [self.graph[u] for u in upstream if u in self.graph]
                if len(upstream) == 0 or len(upstream) == len(existing_upstream):
                    self.logger.debug(f'{kwargs["name"]} ready for creation')
                    # all this node's requirements are created
                    node_type = kwargs.pop('type')
                    node_kwargs = {
                            'pipeline': self,
                            'logger': self.logger,
                            '_upstream': existing_upstream} # we _ the key because of the update line below
                    node_kwargs.update(kwargs)
                    self.logger.debug(node_kwargs)
                    n = getattr(Doberman, node_type)(**node_kwargs)
                    if isinstance(kwargs['input_var'], str):
                        # some things take lists
                        setup_kwargs = self.db.get_sensor_setting(name=kwargs['input_var'])
                    else:
                        setup_kwargs = {}
                    setup_kwargs['influx_cfg'] = influx_cfg
                    setup_kwargs['operation'] = kwargs.get('operation')
                    setup_kwargs['sink_topic'] = kwargs.get('topic')
                    setup_kwargs['sink_subsystem'] = kwargs.get('subsystem')
                    setup_kwargs['write_to_influx'] = self.db.write_to_influx
                    setup_kwargs['log_alarm'] = self.db.log_alarm
                    setup_kwargs['log_command'] = self.db.log_command
                    for k in 'target value'.split():
                        setup_kwargs[f'control_{k}'] = kwargs.get(f'control_{k}')
                    setup_kwargs['strict_length'] = True if isinstance(n, Doberman.AlarmNode) else kwargs.get('strict_length', False)
                    for k in 'escalation_config silence_duration'.split():
                        setup_kwargs[k] = alarm_cfg[k]
                    n.setup(**setup_kwargs)
                    n.load_config(config.get('node_config', {}).get(n.name, {}))
                    self.graph[n.name] = n
                    if isinstance(n, Doberman.BufferNode):
                        num_buffer_nodes += 1
                        longest_buffer = max(longest_buffer, n.buffer.length)

            if (nodes_built := len(self.graph) - start_len) == 0:
                # we didn't make any nodes this loop, we're probably stuck
                created = list(self.graph.keys())
                all_nodes = set(d['name'] for d in pipeline_config)
                self.logger.debug(f'Created {created}')
                self.logger.debug(f'Didn\'t create {list(all_nodes - set(created))}')
                raise ValueError('Can\'t construct graph! Check config and logs')
            else:
                self.logger.debug(f'Created {nodes_built} nodes this iter, {len(self.graph)}/{len(pipeline_config)} total')
        for kwargs in pipeline_config:
            for u in kwargs.get('upstream', []):
                self.graph[u].downstream_nodes.append(self.graph[kwargs['name']])

        self.startup_cycles = num_buffer_nodes + longest_buffer # I think?
        self.logger.debug(f'I estimate we will need {self.startup_cycles} cycles to start')

    def reconfigure(self, doc):
        for node in self.graph.values():
            if isinstance(node, Doberman.AlarmNode):
                rd = self.db.get_sensor_setting(name=node.input_var)
                if node.name not in doc:
                    doc[node.name] = {}
                doc[node.name].update(alarm_thresholds=rd['alarm_thresholds'], readout_interval=rd['readout_interval'])
            if isinstance(node, Doberman.SimpleAlarmNode):
                if node.name not in doc:
                    doc[node.name] = {}
                doc[node.name].update(length=rd['alarm_recurrence'])
            if node.name in doc:
                node.load_config(doc[node.name])

    def silence_for(self, duration):
        """
        Silence this pipeline for a set amount of time
        """
        self.db.set_pipeline_value(self.name, [('status', 'silent')])
        self.db.log_command(f'pipelinectl_active {self.name}', self.name, self.name, duration)

