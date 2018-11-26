import enum
import math

from analysis.end_to_end_latency import EndToEndLatency

FLIT_DEFAULT_SIZE = 32
PACKET_DEFAULT_SIZE = 128


class Packet:
    def __init__(self, id, dest, message):
        self.id = id
        self.message = message
        self.flits = []

        # Flit construct
        flitNumber = int(math.ceil(float(PACKET_DEFAULT_SIZE / FLIT_DEFAULT_SIZE)))

        for i in range(flitNumber):
            if i == 0:  # Head Flit
                self.flits.append(Flit(i, FlitType.head, 0, self))
            elif i == flitNumber - 1:  # Tail Flit
                self.flits.append(Flit(i, FlitType.tail, 0, self))
            else:  # Body Flit
                self.flits.append(Flit(i, FlitType.body, 0, self))

        self.set_destination(dest)

    def set_destination(self, dest):
        for flit in self.flits:
            flit.set_destination_info(dest)

    def __str__(self):
        return 'Packet(%d) from Message(%d)' % (self.id, self.message.id)


#############################################################
class FlitType(enum.Enum):
    head = 1
    body = 2
    tail = 3


#############################################################
class Flit:
    def __init__(self, id, type, begin_time, packet):
        self.id = id
        self.type = type
        self.begin_time = begin_time
        self.destination = None
        self.packet = packet

    def set_destination_info(self, destination):
        self.destination = destination

    def set_arrival_time(self, arrival_time):
        self.arrival_time = arrival_time

    def __str__(self):
        return 'Flit(%d-%s) from %s' % (self.id, self.type, self.packet)


#############################################################
class Message:
    def __init__(self, id, period, size, offset, deadline, src, dest):
        self.id = id
        self.period = period
        self.offset = offset
        self.deadline = deadline
        self.src = src
        self.dest = dest
        self.size = size
        self.packets = []

        # Packet construct
        packet_number = int(math.ceil(float(self.size / PACKET_DEFAULT_SIZE))) + 2  # Payload + 2 (Head/Tail)

        for i in range(packet_number):
            self.packets.append(Packet(i, self.dest, self))

    def get_analysis_latency(self):
        # Routing Distance Computing
        nR = EndToEndLatency.routing_distance(self.src, self.dest)
        # Iteration Number
        nI = EndToEndLatency.iteration_number(len(self.packets), 4)  # TODO : change to dynamic

        # Network Latency
        # nI: Number of iteration
        # oV: Total VC occupied(pessimistic)
        # nR: Routing Distance
        nL = EndToEndLatency.network_latency(nI, 1, nR)

        return int((EndToEndLatency.NETWORK_ACCESS_LAT * 2) + nL)

    def __str__(self):
        return '[id: %d -- size: %d -- period: %d -- offset: %d -- deadline: %d -- src: %s -- dest: %s]' \
               % (self.id, self.size, self.period, self.offset, self.deadline, self.src, self.dest)


#############################################################


class MessageInstance(Message):
    def __init__(self, message, instance):
        super().__init__(message.id, message.period, message.size, message.offset,
                         message.deadline, message.src, message.dest)
        self.instance = instance

    def set_depart_time(self, depart_time):
        self._depart_time = depart_time

    def get_depart_time(self):
        return self._depart_time

    def get_arriving_time(self):
        arr = -1

        packets = self.packets
        for packet in packets:
            flits = packet.flits
            for flit in flits:
                if flit.type == FlitType.tail:
                    if arr < flit.arrival_time:
                        arr = flit.arrival_time

        return arr

    def get_latency(self):
        return self.get_arriving_time() - self.get_depart_time()

    def __str__(self):
        return 'Message (%d)(instance = %d)' % (self.id, self.instance)


#############################################################
class Node:
    def __init__(self, vc_src, vc_target):
        self.vc_src = vc_src
        self.vc_target = vc_target


class NodeArray:
    def __init__(self):
        self.array = []

    def add(self, node):
        self.array.append(node)

    def remove(self, vc_src):
        for node in self.array:
            if node.vc_src == vc_src:
                self.array.remove(node)

    def get_target(self, vc_src):
        for node in self.array:
            if node.vc_src == vc_src:
                return node.vc_target
        return None
