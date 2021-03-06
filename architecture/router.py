import copy
import logging

import math
import time

from communication.structure import NodeArray, FlitType, Node, PACKET_DEFAULT_SIZE, FLIT_DEFAULT_SIZE
from engine.simulation import TRACESET


class Router:
    def __init__(self, env, id, coordinate, proc_engine):
        self.action = env.process(self.run())
        self.env = env
        self.id = id
        self.coordinate = coordinate
        self.proc_engine = proc_engine
        self.logger = logging.getLogger(' ')
        self.noc = None

        # Process Attribute
        self.vcs_dictionary = NodeArray()
        self.vcs_target_north = []
        self.vcs_target_south = []
        self.vcs_target_east = []
        self.vcs_target_west = []
        self.vcs_target_pe = []
        self.pipelined_sending = []

    def inport_setting(self, inNorth, inSouth, inEast, inWest):
        self.inNorth = inNorth
        self.inSouth = inSouth
        self.inEast = inEast
        self.inWest = inWest

    def outport_setting(self, outNorth, outSouth, outEast, outWest):
        self.outNorth = outNorth
        self.outSouth = outSouth
        self.outEast = outEast
        self.outWest = outWest

    def proc_engine_setting(self, inPE, outPE):
        self.inPE = inPE
        self.outPE = outPE

    def noc_settings(self, noc):
        self.noc = noc

    def run(self):
        while True:
            yield self.env.timeout(1)

            if self.noc.arbitration == "RR":
                self.rr_arbitration()

            elif self.noc.arbitration == "PRIORITY_PREEMPT":
                self.priority_preemptive_arbitration()

    def route_computation(self, flit):
        # On X axe (Column)
        # By the West
        if self.coordinate.j > flit.destination.j:
            return self.outWest
        # By the East
        elif self.coordinate.j < flit.destination.j:
            return self.outEast
        # On Y axe (Row)
        else:
            if self.coordinate.i > flit.destination.i:
                return self.outNorth
            # By the East
            elif self.coordinate.i < flit.destination.i:
                return self.outSouth
            else:
                # Destination Reached
                return self.outPE

    def is_packet_still_in_vc(self, packet):
        if self.inPE.is_packet_still_in_vc(packet) or \
                self.inSouth.is_packet_still_in_vc(packet) or \
                self.inNorth.is_packet_still_in_vc(packet) or \
                self.inWest.is_packet_still_in_vc(packet) or \
                self.inEast.is_packet_still_in_vc(packet):
            return True
        else:
            return False

    def receiving_from_pe(self, packet):
        if self.is_packet_still_in_vc(packet):
            return False

        if self.noc.arbitration == "RR":
            requested_vc = self.inPE.vc_allocator()
        elif self.noc.arbitration == "PRIORITY_PREEMPT":
            requested_vc = self.inPE.priority_vc_allocator(packet.priority)
        else:
            requested_vc = None

        if requested_vc is not None:
            for flit in packet.flits:
                requested_vc.enqueue(flit)
                self.logger.info(
                    '(%d) : %s - %s -> %s -> %s' % (self.env.now, flit, self.proc_engine, requested_vc, self))

                # set depart time for the first first in the first packet
                if flit.id == 0 and flit.packet.id == 0:
                    flit.packet.message.set_depart_time(self.env.now)

            return True
        else:
            return False

    def vc_target_outport(self, vc):

        if len(vc.flits) > 0:
            if self.route_computation(vc.flits[0]) == self.outNorth \
                    and vc not in self.vcs_target_north:
                self.vcs_target_north.append(vc)

            elif self.route_computation(vc.flits[0]) == self.outSouth \
                    and vc not in self.vcs_target_south:
                self.vcs_target_south.append(vc)

            elif self.route_computation(vc.flits[0]) == self.outEast \
                    and vc not in self.vcs_target_east:
                self.vcs_target_east.append(vc)

            elif self.route_computation(vc.flits[0]) == self.outWest \
                    and vc not in self.vcs_target_west:
                self.vcs_target_west.append(vc)

            elif self.route_computation(vc.flits[0]) == self.outPE \
                    and vc not in self.vcs_target_pe:
                self.vcs_target_pe.append(vc)

    def arrived_flit(self, vc):
        flit = vc.dequeue()

        # Flit Timestamp to avoid premature sending
        if flit.timestamp == self.env.now:
            vc.restore(flit)
            return

        flit.timestamp = copy.copy(self.env.now)

        if flit.type == FlitType.tail:
            self.vcs_dictionary.remove(vc)
            vc.release()

        vc.credit_out()

        # Flit store
        self.proc_engine.flit_receiving(flit)

        TRACESET.set_flit_arrival(flit.packet.message, self.env.now)

        # set arrival time to the last flit into the message
        nb_flit = PACKET_DEFAULT_SIZE / FLIT_DEFAULT_SIZE
        nb_packet = math.ceil(flit.packet.message.size / PACKET_DEFAULT_SIZE)

        if flit.id == nb_flit - 1 and flit.packet.id == nb_packet - 1:
            flit.packet.message.set_arrival_time(self.env.now + 1)

        self.logger.info('(%d) : %s - %s -> %s' % (self.env.now, flit, self, self.proc_engine))

    def send_flit(self, vc, outport):

        # getting the first flit in VC
        flit = vc.dequeue()

        # Flit Timestamp to avoid premature sending
        if flit.timestamp == self.env.now:
            vc.restore(flit)
            return

        # if is a Head Flit
        if flit.type == FlitType.head:

            # Get idle VC from next Input
            if self.noc.arbitration == "RR":
                vc_allotted = outport.inPort.vc_allocator()
            elif self.noc.arbitration == "PRIORITY_PREEMPT":
                vc_allotted = outport.inPort.priority_vc_allocator(flit.packet.priority)
            else:
                vc_allotted = None

            if vc_allotted is not None:
                self.logger.debug('(%d) - VC (%s) allotted' % (self.env.now, vc_allotted))
                vc_allotted.enqueue(flit)
                flit.timestamp = copy.copy(self.env.now)
                self.logger.info(
                    '(%d) : %s ON %s- %s -> %s -> %s' % (self.env.now, flit, vc, self, vc_allotted, vc_allotted.router))
                # vc.credit_out()

                # registering VC allotted in dictionary
                self.vcs_dictionary.add(Node(vc, vc_allotted))

            else:  # No idle VC
                vc.restore(flit)  # restore
                self.logger.debug('(%d) - %s was not sent - VC not allotted ON %s' %
                                  (self.env.now, flit, outport.inPort.router))
                # outport.inPort.vcs_status()
                # time.sleep(1)

        # if is a Body Flit
        elif flit.type == FlitType.body:
            # Getting the alloted vc
            vc_allotted = self.vcs_dictionary.get_target(vc)
            self.logger.debug('(%d) - Retreiving allotted VC (%s)' % (self.env.now, vc_allotted))

            # Sending to the next router
            sent = vc_allotted.enqueue(flit)

            if not sent:  # No Place
                vc.restore(flit)  # restore
                self.logger.debug('(%d) - %s was not sent - No Place in VC (%s)' % (self.env.now, flit, vc_allotted))
            else:
                self.logger.info(
                    '(%d) : %s ON %s- %s -> %s -> %s' % (self.env.now, flit, vc, self, vc_allotted, vc_allotted.router))
                # vc.credit_out()
                flit.timestamp = copy.copy(self.env.now)

        # if is a Tail Flit
        elif flit.type == FlitType.tail:
            # Getting the alloted vc
            vc_allotted = self.vcs_dictionary.get_target(vc)

            # Sending to the next router
            sent = vc_allotted.enqueue(flit)

            if not sent:  # No Place
                vc.restore(flit)  # restore
                self.logger.debug('(%d) - %s was not sent - No Place in VC (%s)' % (self.env.now, flit, vc_allotted))
            else:
                self.vcs_dictionary.remove(vc)
                flit.timestamp = copy.copy(self.env.now)
                # vc.credit_out()
                vc.release()
                self.logger.debug('(%d) - VC (%s) - released' % (self.env.now, vc))

        vc.credit_out()

    def rr_arbitration(self):
        # ---------- VC election ----------
        for vc in self.inPE.vcs:
            self.vc_target_outport(vc)
        # Checking North VC
        for vc in self.inNorth.vcs:
            self.vc_target_outport(vc)
        # Checking South VC
        for vc in self.inSouth.vcs:
            self.vc_target_outport(vc)
        # Checking East VC
        for vc in self.inEast.vcs:
            self.vc_target_outport(vc)
        # Checking West VC
        for vc in self.inWest.vcs:
            self.vc_target_outport(vc)

        # VC targeting -> North
        if len(self.vcs_target_north) > 0:
            vc = self.vcs_target_north.pop(0)
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outNorth)

            # re-insert if credit is not finished
            self.vc_reinsertion(vc, self.vcs_target_north)

        # VC targeting -> South
        if len(self.vcs_target_south) > 0:
            vc = self.vcs_target_south.pop(0)
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outSouth)

            # re-insert if credit is not finished
            self.vc_reinsertion(vc, self.vcs_target_south)

        # VC targeting -> East
        if len(self.vcs_target_east) > 0:
            vc = self.vcs_target_east.pop(0)
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outEast)

            # re-insert if credit is not finished
            self.vc_reinsertion(vc, self.vcs_target_east)

        # VC targeting -> West
        if len(self.vcs_target_west) > 0:
            vc = self.vcs_target_west.pop(0)
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outWest)

            # re-insert if credit is not finished
            self.vc_reinsertion(vc, self.vcs_target_west)

        # VC targeting -> PE
        if len(self.vcs_target_pe) > 0:
            vc = self.vcs_target_pe.pop(0)
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.arrived_flit(vc)

            # re-insert if credit is not finished
            self.vc_reinsertion(vc, self.vcs_target_pe)

    def vc_reinsertion(self, vc, target_queue):
        if vc.quantum > 0 and len(vc.flits) > 0:
            target_queue.insert(0, vc)
        else:
            vc.reset_credit()

    def get_highest_preemptive_priority_vc(self, candidates):

        # No Arbitration
        if len(candidates) == 1:
            return candidates[0]

        # filtering by timestamp
        for can in candidates:
            if can.flits[-1].timestamp == self.env.now:
                candidates.remove(can)

        priority_vc = candidates[0]

        # Arbitration according to Priority
        for candidate in candidates[1:]:
            if priority_vc.id > candidate.id:
                priority_vc = candidate

        return priority_vc

    def priority_preemptive_arbitration(self):
        # ---------- VC election ----------
        for vc in self.inPE.vcs:
            self.vc_target_outport(vc)
        # Checking North VC
        for vc in self.inNorth.vcs:
            self.vc_target_outport(vc)
        # Checking South VC
        for vc in self.inSouth.vcs:
            self.vc_target_outport(vc)
        # Checking East VC
        for vc in self.inEast.vcs:
            self.vc_target_outport(vc)
        # Checking West VC
        for vc in self.inWest.vcs:
            self.vc_target_outport(vc)

        # VC targeting -> North
        if len(self.vcs_target_north) > 0:
            vc = self.get_highest_preemptive_priority_vc(self.vcs_target_north)
            self.vcs_target_north.clear()
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outNorth)

        # VC targeting -> South
        if len(self.vcs_target_south) > 0:
            vc = self.get_highest_preemptive_priority_vc(self.vcs_target_south)
            self.vcs_target_south.clear()
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outSouth)

        # VC targeting -> East
        if len(self.vcs_target_east) > 0:
            vc = self.get_highest_preemptive_priority_vc(self.vcs_target_east)
            self.vcs_target_east.clear()
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outEast)

        # VC targeting -> West
        if len(self.vcs_target_west) > 0:
            vc = self.get_highest_preemptive_priority_vc(self.vcs_target_west)
            self.vcs_target_west.clear()
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.send_flit(vc, self.outWest)

        # VC targeting -> PE
        if len(self.vcs_target_pe) > 0:
            vc = self.get_highest_preemptive_priority_vc(self.vcs_target_pe)
            self.vcs_target_pe.clear()
            self.logger.debug('(%d) - %s From %s -> Elected' % (self.env.now, vc, self))
            self.arrived_flit(vc)

    def __str__(self):
        return 'Router (%d,%d)' % (self.coordinate.i, self.coordinate.j)
