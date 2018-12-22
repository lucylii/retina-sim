import math
import random
import sys
import copy
import yaml

from communication.routing import Coordinate
from communication.structure import Message, Link, LinkArray
from gen.unifast import Unifast


class Generation:
    def __init__(self):
        self._quantum_tab = []
        self.period_array = [50, 100, 150, 200, 300, 600]
        self.offset_array = [0, 10, 15, 30, 60, 80]
        self.messages = []
        self.counter = 0

    def set_noc(self, noc):
        self.noc = noc

    def config(self, link):
        with open(link, 'r') as stream:
            try:
                data = yaml.load(stream)

                # parsing
                self._square_size = data['noc']['dimension']
                self._nbvc = data['noc']['numberOfVC']
                self._vc_size = data['noc']['VCBufferSize']
                self._arbitration = data['noc']['arbitration']

                # VC Quatum
                quantum = data['quantum']
                if len(quantum) != self._nbvc:
                    print('Config Error : VC Quantum settings is not identical to VC number')
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
                if 'scenario' in data:
                    messages = data['scenario']
                    count = 0
                    for m in messages:
                        src = m['src']
                        dest = m['dest']
                        size = m['size']
                        offset = m['offset']
                        deadline = m['deadline']
                        period = m['period']

                        self.messages.append(Message(count,
                                                     period,
                                                     size,
                                                     offset,
                                                     deadline,
                                                     Coordinate(src['i'], src['j']),
                                                     Coordinate(dest['i'], dest['j']),
                                                     ))
                        count += 1

                # Automatic generation
                elif 'task' in data:
                    nb_task = data['task']
                    method = data['method']
                    load = data['load']

                    if method == 'UuniFast':
                        self.messages = self.uunifast_generate(nb_task, load)

                return self.messages

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

    def arbitration(self):
        return self._arbitration

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

        for message in self.messages:
            hyperperiod = self.lcm(hyperperiod, message.period)

        return hyperperiod

    # Generation : Unifast
    def uunifast_generate(self, nb_task, load):
        self._utilization_array = self.get_utilization_factors(nb_task)

        self.counter = 0
        # Loop
        while len(self._utilization_array) > 0:
            # generate parameters
            utilization_factor = self._utilization_array.pop(random.randrange(len(self._utilization_array)))
            period = self.period_array[random.randint(0, len(self.period_array) - 1)]
            offset = self.offset_array[random.randint(0, len(self.offset_array) - 1)]
            size = int(math.ceil(period * utilization_factor))
            lower_bound = int(load * period)
            deadline = random.randint(0, (period - lower_bound + 1) + lower_bound)

            # Generate messages
            coord = self.generate_random_coordinate()
            src = coord[0]
            dest = coord[1]
            message = Message(self.counter, period, size, offset, deadline, src, dest)
            self.messages.append(message)

            # Generate task conflict
            # self.generate_conflict_message(message, 4)
            self.counter += 1

        return self.messages

    # Utilization Factors
    def get_utilization_factors(self, nb_task):
        """
        The UUniFast algorithm was proposed by Bini for generating task
        utilizations on uniprocessor architectures.

        The UUniFast-Discard algorithm extends it to multiprocessor by
        discarding task sets containing any utilization that exceeds 1.

        This algorithm is easy and widely used. However, it suffers from very
        long computation times when n is close to u. Stafford's algorithm is
        faster.

        Args:
            - `nb_task`: The number of tasks in a task set.
            - `nb_set`: Number of sets to generate.
            - `u`: Total utilization of the task set.
        Returns `nsets` of `n` task utilizations.
        """
        unifast = Unifast(nb_task, 1, 2)
        return unifast.UUniFastDiscard()

    def generate_random_coordinate(self):

        # source router coordinate
        src_i = random.randint(0, self._square_size - 1)
        src_j = random.randint(0, self._square_size - 1)

        # destination router coordinate
        dest_i = src_i
        dest_j = src_j
        while src_i == dest_i:
            dest_i = random.randint(0, self._square_size - 1)
        while src_j == dest_j:
            dest_j = random.randint(0, self._square_size - 1)

        return [Coordinate(src_i, src_j), Coordinate(dest_i, dest_j)]

    """
    Creation and Generation Conflict Task Part
    """

    def generate_random_communicating_task(self, max_size, offset):
        coord = self.generate_random_coordinate()
        src = coord[0]
        dest = coord[1]
        size = random.randint(1, max_size)
        period = self.period_array[random.randint(0, len(self.period_array) - 1)]
        lower_bound = int(0.7 * period)
        deadline = random.randint(0, (period - lower_bound + 1) + lower_bound)

        message = Message(self.counter, period, size, offset, deadline, src, dest)
        self.counter += 1
        return message

    def generation_conflict_coordinate(self, src):
        dest_i = src.i
        dest_j = src.j
        while src.i == dest_i:
            dest_i = random.randint(0, self._square_size - 1)
        while src.j == dest_j:
            dest_j = random.randint(0, self._square_size - 1)

        return Coordinate(dest_i, dest_j)

    def conflict_task_generation_discard(self, message, rate, error_rate):
        # extract message XY routing coordinate
        path1 = self.get_xy_path_coordinate(message)

        # while loop to check if the whole path respects rate
        while self.check_rate_equal_path(path1, rate, error_rate):

            # generate random task with random size
            message_conflict = self.generate_random_communicating_task(message.size, message.offset)
            path2 = self.get_xy_path_coordinate(message_conflict)

            # if the two tasks share at least one physical link (overlap)
            overlap = self.task_overlap(path1, path2)
            if not overlap:
                continue  # Discard

            conflict_lu = message_conflict.get_link_utilization()

            # check if generated communication doesn't exceed the rate + error
            if path2.check_utilization_rate(conflict_lu, rate, error_rate):
                continue  # Discard

            # add a communication task to message array
            self.messages.append(message_conflict)

    def get_xy_path_coordinate(self, message):
        src = copy.copy(message.src)
        dest = message.dest

        # put the first router
        link_array = LinkArray()
        path_array = [message.src]

        while True:
            # On X axe (Column)
            # By the West
            if src.j > dest.j:
                src.j -= 1
                path_array.append(Coordinate(src.i, src.j))
            # By the East
            elif src.j < dest.j:
                src.j += 1
                path_array.append(Coordinate(src.i, src.j))
            # On Y axe (Row)
            else:
                if src.i > dest.i:
                    src.i -= 1
                    path_array.append(Coordinate(src.i, src.j))
                # By the East
                elif src.i < dest.i:
                    src.i += 1
                    path_array.append(Coordinate(src.i, src.j))
                else:
                    break

        # fill path
        for i in range(len(path_array) - 1):
            link_array.add_link(Link(path_array[i], path_array[i + 1]))

        return link_array

    def is_links_equal(self, l1, l2):
        if l1.trans.i == l2.trans.i and l1.receiv.i == l2.receiv.i \
                and l1.trans.j == l2.trans.j and l1.receiv.j == l2.receiv.j:
            return True
        else:
            return False

    def task_overlap(self, p1, p2):
        for m in p1.array:
            for n in p2.array:
                if self.is_links_equal(m, n):
                    return True
        return False

    def get_link_utilisation(self, link):
        return link.utilization_rate

    def check_rate_equal_path(self, path, rate, error_rate):
        for p in path.array:
            if p.utilization_rate > rate + error_rate or \
                    p.utilization_rate < rate - error_rate:
                return False
        return True