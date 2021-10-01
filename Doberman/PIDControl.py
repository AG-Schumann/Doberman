import Doberman


class ErrorNode(Doberman.Node):
    """
    Calculates the difference between a value and the target. Separated from the PID node to prevent
    setpoint changes causing instability
    """
    def process(self, package):
        return self.config['setpoint'] - package[self.input_var]

class PIDControlNode(Doberman.Node, Doberman.ControlNode):
    """
    A fully-featured PID controller
    """
    def process(self, package):
        Kp = self.config.get('Kp', 0)
        Ki = self.config.get('Ki', 0)
        Kd = self.config.get('Kd', 0)
        bias = self.config.get('bias', 0)

        P = Kp * package['error']
        I = Ki * package['error_integral']
        D = Kd * package['error_derivative']

        pid = P + I + D + bias
        self.logger.debug(f'{self.name} P {P} I {I} D {D} bias {bias}')

        self.set_output(pid)

