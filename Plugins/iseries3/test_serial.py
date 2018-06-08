import serial


class iseries:
  def __init__(self, port, name=None):
    self.__startcharakter = "*"  #Startcharakter may change if manualy set another   
    self.__CR = chr(13)
    self.__LF = chr(10)
    self._port = '/dev/ttyUSB{:d}'.format(port)
    self._name = name
    self.__device = serial.Serial(
                    port=self._port,
                    baudrate=9600,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout = 5
                )
    if not name == None:
      print "Connected to '{}' on port {}".format(self._name, self._port)
    else:
      print "connected to port {}".format(self._port)


  def communicate(self, message):
    message = self.__startcharakter + str(message)+self.__CR+self.__LF
    self.__device.write(message)
    response_raw = (self.__device.readline())
    return response_raw


if __name__ == '__main__':
#  i1 = iseries(port=0, name='iseries1') # iseries1 at ttyUSB0
#  i2 = iseries(port=3, name='iseries2') # iseries2 at ttyUSB3
#  i3 = iseries(port=6, name='iseries3') # iseries3 at ttyUSB6
#  i0 = iseries(port=0, name='i0')
#  i1 = iseries(port=1, name='i1')
#  i2 = iseries(port=2, name='i2')
#  i3 = iseries(port=3, name='i3')
#  i4 = iseries(port=4, name='i4')
  i5 = iseries(port=5, name='i5')
#  i6 = iseries(port=6, name='i6')

