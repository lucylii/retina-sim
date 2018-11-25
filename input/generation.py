import yaml
import logging
import sys
import random
import copy
import math

from communication.routing import Coordinate
from communication.structure import Message
from input.unifast import Unifast


class Generation:
    def __init__(self):
        self.message_tab = []
        self._quantum_tab = []
        self._utilization_array = self.get_utilization_factors()
        self.period_array = [50, 100, 150, 200, 300, 600]
        self.offset_array = [0, 10, 15, 30, 60, 80]
        self.messages = []
        self.counter = 0

    def config(self, link):
        with open(link, 'r') as stream:
            try:
                data = yaml.load(stream)

                # parsing
                self._square_size = data['noc']['dimension']
                self._nbvc = data['noc']['numberOfVC']
                self._vc_size = data['noc']['VCBufferSize']

                # VC Quatum
                quantum = data['quantum']
                if len(quantum) != self._nbvc:
                    logging.info('Config Error : VC Quantum settings is not identical to the number of VC')
                    sys.exit()
                else:
                    for q in quantum.items():
                        self._quantum_tab.append(q[1])

            except yaml.YAMLError as exc:
                print(exc)

    def scenario(self, link):
        with open(link, 'r') as stream:
            try:
                data = yaml.load(stream)

                # Messages
                messages = data['scenario']
                count = 0
                for m in messages:
                    src = m['src']
                    dest = m['dest']
                    size = m['size']
                    offset = m['offset']
                    deadline = m['deadline']
                    period = m['period']

                    self.message_tab.append(Message(count,
                                                    period,
                                                    size,
                                                    offset,
                                                    deadline,
                                                    Coordinate(src['i'], src['j']),
                                                    Coordinate(dest['i'], dest['j']),
                                                    ))
                    count += 1

                return self.message_tab

            except yaml.YAMLError as exc:
                print(exc)

    def square_size(self):
        return self._square_size

    def nbvc(self):
        return self._nbvc

    def vc_size(self):
        return self._vc_size

    def vc_quantum(self):
        return self._quantum_tab

    # HyperPeriod Computation
    def gcd(self, a, b):
        while b != 0:
            remainder = a % b
            a = b
            b = remainder

        return a

    def lcm(self, a, b):
        if a == 0 or b == 0:
            return 0
        return (a * b) // self.gcd(a, b)

    def hyperperiod(self):
        hyperperiod = 1

        for message in self.message_tab:
            hyperperiod = self.lcm(hyperperiod, message.period)

        return hyperperiod

    # Generation : Unifast
    def generate_messages(self):

        self.counter = 0
        # Loop
        while len(self._utilization_array) > 0:
            # generate parameters
            utilization_factor = self.get_random_utiliz_fact()
            period = self.period_array[random.randint(len(self.period_array))]
            offset = self.offset_array[random.randint(len(self.offset_array))]
            size = int(math.ceil(period * utilization_factor))
            lower_bound = int(0.7 * period)
            deadline = random.randint((period - lower_bound + 1) + lower_bound)

            # Generate messages
            coord = self.generate_random_coordinate()
            src = coord[0]
            dest = coord[1]
            message = Message(self.counter, period, size, offset, deadline, src, dest)
            self.messages.append(message)

            # Generate task conflict
            self.generate_conflict_message(message)
            self.counter += 1

    # Utilization Factors
    def get_utilization_factors(self):
        unifast = Unifast(2, 16, 2)

        return unifast.generate_utilization()

    def get_random_utiliz_fact(self):
        index = random.randint(len(self._utilization_array))
        utilization_factor = copy.deepcopy(self._utilization_array[index])
        self._utilization_array.remove(utilization_factor)

        return utilization_factor

    # Conflict Task Generation
    def generate_conflict_message(self, message):
        # Left message
        if message.src.j - 1 > 0:
            self.counter += 1
            coord = Coordinate(message.src.i, message.src.i - 1)
            msg = Message(self.counter, message.period, message.size,
                          message.offset, message.deadline, coord, message.dest)
            self.messages.append(msg)

        # Right message
        if message.src.j + 1 < self._square_size:
            self.counter += 1
            coord = Coordinate(message.src.i, message.src.i + 1)
            msg = Message(self.counter, message.period, message.size,
                          message.offset, message.deadline, coord, message.dest)
            self.messages.append(msg)

    def generate_random_coordinate(self):

        # source router coordinate
        src_i = random.randint(self._square_size)
        src_j = random.randint(self._square_size)

        # destination router coordinate
        dest_i = src_i
        dest_j = src_j
        while src_i == dest_i:
            dest_i = random.randint(self._square_size)
        while src_j == dest_j:
            dest_j = random.randint(self._square_size)

        return [Coordinate(src_i, src_j), Coordinate(dest_i, dest_j)]
