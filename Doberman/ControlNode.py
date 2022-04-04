import Doberman


class ControlNode(Doberman.Node):
    """
    Another empty base class to handle different database access
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self._log_command = kwargs['log_command']
        self.control_target = kwargs['control_target']
        self.control_value = kwargs['control_value']

    def set_output(self, value, _force=False):
        self.logger.debug(f'Setting output to {value}')
        if not self.is_silent and not _force:
            self._log_command(f'set {self.control_value} {value}', self.control_target,
                    self.name)

    def on_error_do_this(self):
        if (v := self.config.get('default_output')) is not None:
            self.set_output(v, _force=True)

class DigitalControl(ControlNode):
    """
    A generalized node to handle digital output. The logic is assumed to be
    upstream.
    """
    def process(self, package):
        if package['condition_a']:
            self.logger.info('Condition a met')
            self.set_output(self.config.get('output_a', 1))
        elif package['condition_b']:
            self.logger.info('Condition b met')
            self.set_output(self.config.get('output_b', 0))

class AnalogControl(ControlNode):
    """
    A generalized node to handle analog output. The logic is assumed to be
    upstream
    """
    def process(self, package):
        val = package[self.input_var]
        if (min_output := self.config.get('min_output')) is not None:
            val = max(val, min_output)
        if (max_output := self.config.get('max_output')) is not None:
            val = min(val, max_output)
        self.set_output(val)

class PipelineControl(ControlNode):
    """
    Sometimes you want one pipeline to control another. Currently no idea how
    to implement this inside the current constraints.
    """
    def process(self, package):
        if package.get('condition_x', False):
            # this one is mainly for testing
            self.control_pipeline(self.pipeline.name, 'stop')

    def control_pipeline(self, pipeline, action):
        if self.is_silent:
            return
        if pipeline.startswith('control'):
            # we can do this directly
            self.pipeline.monitor.process_command(f'pipelinectl_{action} {pipeline}')
            return
        if pipeline.startswith('alarm'):
            target = 'pl_alarm'
        elif pipeline.startswith('convert'):
            target = 'pl_convert'
        self.pipeline.db.log_command(f'pipelinectl_{action} {pipeline}', to=target,
                issuer=self.pipeline.name)

