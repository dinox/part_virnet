import optparse, sys, json, socket, traceback, SocketServer, threading, time

from twisted.internet import defer, reactor
from twisted.internet.protocol import Protocol, ClientFactory, ServerFactory,\
    DatagramProtocol
from twisted.protocols.basic import NetstringReceiver

#global variables
class Node(object):
    monitor = "undefinded"
    my_id = 0
    my_node = '127.0.0.1'
    my_sqn = 0
    neighbourhood = None
    overlay = None
    client_factory = None

    def get_sqn(self):
        self.my_sqn = self.my_sqn + 1
        return self.my_sqn

MyNode = Node()

# global output file names
LOG_FILE = "overlay.log"
LATENCY_FILE = "latency.log"
PINGS_FILE = "pings.log"
EXCEPTION_FILE = "exceptions.log"

def parse_args():
    usage = """usage: %prog [options] [hostname]:port
    Specify hostname and port of monitor node.
    You can also specify and id number with --id option."""

    parser = optparse.OptionParser(usage)

    help = "The id number for this node. Default to 0."
    parser.add_option('--id', type='int', help=help)

    help = "The port to listen on. Default to a random available port."
    parser.add_option('--port', type='int', help=help)

    help = "The interface to listen on."
    parser.add_option('--iface', help=help)


    options, address = parser.parse_args()

    if not address :
        print parser.format_help()
        parser.exit()

    def parse_address(addr):
        if ':' not in addr:
            host = '127.0.0.1'
            port = addr
        else:
            host, port = addr.split(':', 1)

        if not port.isdigit():
            parser.error('Ports must be integers.')

        return {"host" : host, "port" : int(port)}

    return options, parse_address(address[0])

class Neighbourhood(object):
    nodes = []
    addresses = dict()
    pings = dict()

    def __init__(self, vir_nodes):
        global MyNode
        for node in vir_nodes:
            if not node == MyNode.my_id:
                self.nodes.append(node)
        self.lookup()

    def lookup(self):
        global MyNode
        from twisted.internet import reactor
        for node in self.nodes:
            send_msg(MyNode.monitor, {"command" : "lookup", "id" : node})
        log_status("Neighbourhood lookup")

class Overlay(object):
    nodes = dict()
    last_msg = dict()
    edges = dict()

    def update_node(self, node, neighbours, sqn):
        self.nodes[node] = sqn
        self.last_msg[node] = time.time()
        self.edges[node] = neighbours

    def is_valid_msg(self, msg):
        if msg["source"] == MyNode.my_id:
            return False
        if not msg["source"] in self.nodes:
            return True
        if self.nodes[msg["source"]] < msg["sequence"]:
            return True
        else:
            return False


class ClientService(object):

    def OK(self, reply):
        pass

    def DNS_Reply(self, reply):
        global MyNode
        if "node" in reply:
            MyNode.neighbourhood.addresses[reply["id"]] = reply["node"]
        else:
            print "DNS reply did not contain node data"

    def Error(self, reply):
        if "reason" in reply:
            print "Unexpected error: %s" % reply["reason"]
        else:
            print "Unexpected error with no reason"

    def Heartbeat(self, reply):
        global MyNode
        if MyNode.overlay.is_valid_msg(reply):
            MyNode.overlay.update_node(reply["source"], reply["neighbours"],
                    reply["sequence"])
            for nodeID in MyNode.neighbourhood.addresses:
                send_msg(MyNode.neighbourhood.addresses[nodeID], reply)
            print("Heartbeat message received")
            print(MyNode.overlay.nodes)
            print(MyNode.overlay.last_msg)

    commands = {"ok"    : OK,
                "error" : Error,
                "dns_reply" : DNS_Reply,
                "heartbeat" : Heartbeat }

class ClientProtocol(NetstringReceiver):

    def connectionMade(self):
        self.sendRequest(self.factory.request)

    def sendRequest(self, request):
        print "Sending: %s" % self.factory.request
        self.sendString(json.dumps(request))

    def stringReceived(self, reply):
        self.transport.loseConnection()
        print "Received: %s" % reply
        reply = json.loads(reply)
        command = reply["command"]

        if command not in self.factory.service.commands:
            print "Command <%s> does not exist!" % command
            self.transport.loseConnection()
            return

        self.factory.handleReply(command, reply)

class ServerProtocol(NetstringReceiver):
    def stringReceived(self, request):
        print "Received: %s" % request
        command = json.loads(request)["command"]
        data = json.loads(request)

        if command not in self.factory.service.commands:
            print "Command <%s> does not exist!" % command
            self.transport.loseConnection()
            return

        self.commandReceived(command, data)

    def commandReceived(self, command, data):
        reply = self.factory.reply(command, data)

        if reply is not None:
            print "Send: %s" % reply
            self.sendString(reply)

        self.transport.loseConnection()

class NodeClientFactory(ClientFactory):

    protocol = ClientProtocol

    def __init__(self, service, request):
        self.request = request
        self.service = service
        self.deferred = defer.Deferred()

    def handleReply(self, command, reply):
        def handler(reply):
            return self.service.commands[command](self.service, reply)
        cmd_handler = self.service.commands[command]
        if cmd_handler is None:
            return None
        self.deferred.addCallback(handler)
        self.deferred.callback(reply)

    def clientConnectionFailed(self, connector, reason):
        if self.deferred is not None:
            d, self.deferred = self.deferred, None
            d.errback(reason)

class NodeServerFactory(ServerFactory):

    protocol = ServerProtocol

    def __init__(self, service):
        self.service = service

    def reply(self, command, data):
        create_reply = self.service.commands[command]
        if create_reply is None: # no such command
            return None
        try:
            return create_reply(self.service, data)
        except:
            traceback.print_exc()
            return None # command failed


# UDP serversocket, answers to ping requests

class UDPServer(DatagramProtocol):
    def datagramReceived(self, datagram, address):
        print("*** UDP RECEIVED" + str(address) + " - " + datagram + "***")
        self.transport.write(datagram, address)

class EchoClientDatagramProtocol(DatagramProtocol):

    msg = ''
    host = ''
    port = 0

    def __init__(self, addr, msg):
        self.host = addr["host"]
        self.port = addr["port"]+1
        self.msg = msg
        
    def sendDatagram(self):
        self.transport.write(self.msg)

    def startProtocol(self):
        self.transport.connect(self.host, self.port)
        self.sendDatagram()
        print("*** UDP SENT " + self.host + ":" + str(self.port) + "***")

    def datagramReceived(self, datagram, host):
        print("*** Datagram received: " + datagram + "*!*!*")
        sys_exit()

# Ping request

def send_ping():
    global MyNode
    for nodeID, node in MyNode.neighbourhood.nodes:
        pass

# send TCP message

def send_msg(address, msg):
    from twisted.internet import reactor
    service = ClientService()
    factory = NodeClientFactory(service, msg)
    factory.deferred.addErrback(error_callback)
    reactor.connectTCP(address["host"], address["port"], factory)

def error_callback(s):
    log_exception("Callback", str(s))

# Log functions

def log_status(msg):
    global LOG_FILE, EXCEPTION_FILE
    for filename in (LOG_FILE, EXCEPTION_FILE):
        f = open(filename, "a")
        f.write(msg + "\n")
        f.close()
    print(msg)

def log_membership():
    global is_coordinator, LOG_FILE
    filename = LOG_FILE
    log_timestamp(filename)
    if not is_coordinator:
        log_coordinator(filename)
    log_members(filename)

def log_event(nodeID, event):
    global LOG_FILE
    filename = LOG_FILE
    log_timestamp(filename)
    tab = "    "
    msg = tab + "[EVENT " + event + "]: node" + str(nodeID)
    f = open(filename, "a")
    f.write(msg + "\n")
    print(msg)
    f.close()
    log_members(filename)

def log_timestamp(filename):
    f = open(filename, "a")
    msg = time.strftime("%Y/%m/%d %H:%M:%S") + ":"
    f.write(msg + "\n")
    print(msg)
    f.close()

def log_coordinator(filename):
    global coordinator
    f = open(filename, "a")
    tab = "    "
    msg = tab + "[COORDINATOR]: node" + str(coordinator["id"])
    f.write(msg + "\n")
    print(msg)
    f.close()

def log_members(filename):
    global is_coordinator, members
    f = open(filename, "a")
    tab = "    "
    msg = tab + "[MEMBERS]: ["
    is_empty = True
    # Make copy of members since another thread may change it 
    for nodeID, node in copy.deepcopy(members).items():
        if not is_empty:
            msg = msg + ", "
        msg = msg + "node" + str(nodeID)
        is_empty = False
    msg = msg + "]"
    f.write(msg + "\n ")
    print(msg)
    f.close()
    log_exception("INFO", "My id: node" + str(my_id))

def log_latency(nodeID, new_latency):
    global pings, my_id, LATENCY_FILE
    f = open(LATENCY_FILE, "a")
    msg = "["+str(my_id)+", "+str(nodeID)+", "+str(new_latency)+\
            ", "+str(pings[nodeID])+", "+str(time.time())+"]"
    f.write(msg+"\n")
    f.close()
    print(msg)

def log_pings(ping_list, sourceID):
    global PINGS_FILE
    f = open(PINGS_FILE, "a")
    print("LOG PINGS: ")
    for destID, line in ping_list.items():
        msg = "[" + str(sourceID) + ", " + str(destID) + ", " + \
                str(line) + "]"
        f.write(msg + "\n")
        print(msg)
    f.close()

def log_exception(info, exception):
    global EXCEPTION_FILE
    f = open(EXCEPTION_FILE, "a")
    msg = time.strftime("%Y/%m/%d %H:%M:%S") + ": " + info + "\n"
    msg = msg + "    " + str(exception)
    #print(msg)
    f.write(msg + "\n")
    f.close()


def init_with_monitor(monitor, my_node, my_id):
    """
    Register our DNS data and id_nbr with the monitor at host:port.
    """
    from twisted.internet import reactor
    service = ClientService()
    factory = NodeClientFactory(service, {"command" : "map", "id" : my_id, 
                                            "node" : my_node})
    reactor.connectTCP(monitor["host"], monitor["port"], factory)
    return factory.deferred

#Ping call to measure the latency (called periodically by
# the reactor through LoopingCall)
def measure_latency():
    global MyNode
    for nodeID in MyNode.neighbourhood.addresses:
        addr = MyNode.neighbourhood.addresses[nodeID]
        protocol = EchoClientDatagramProtocol(addr, "msg")
        reactor.listenUDP(0, protocol)

# Heartbeat function of the client (called periodically 
# by the reactor through LoopingCall)
#   Collect pings from neighbours
#   Send alive message
def client_heartbeat():
    global MyNode
    # send heartbeat msg to all neighbours
    print("Client Heartbeat")
    msg = {"command":"heartbeat","source":MyNode.my_id,\
            "sequence":MyNode.get_sqn(),"neighbours":{1:0.12}}
    print(msg)
    for nodeID in MyNode.neighbourhood.addresses:
        send_msg(MyNode.neighbourhood.addresses[nodeID], msg)

# INITIALIZATION

# create dummy/test neighbourhood, should be replaced with real neighourhood
# initialization
def init_neighbourhood_dummy(vir_nodes):
    global MyNode
    MyNode.neighbourhood = Neighbourhood(vir_nodes)


# MAIN

def main():
    global MyNode
    options, MyNode.monitor = parse_args()
    MyNode.my_id = options.id or 0
    MyNode.my_node = {"host" : options.iface or
            socket.gethostbyname(socket.gethostname()),
            "port" : options.port or 13337}
    from twisted.internet import reactor
    from twisted.internet.task import LoopingCall

    log_status("Startup node" + str(MyNode.my_id) + " with address " +\
            str(MyNode.my_node))

    # initialize UDP socket
    reactor.listenUDP(MyNode.my_node["port"]+1, UDPServer())

    service = ClientService()
    factory = NodeServerFactory(service)
    port = reactor.listenTCP(MyNode.my_node["port"], factory, 
            interface=MyNode.my_node["host"])

    # initialize Neighbourhood
    init_neighbourhood_dummy([0,1])
    MyNode.overlay = Overlay()

    d = init_with_monitor(MyNode.monitor, MyNode.my_node, MyNode.my_id)

    # refresh addresses periodically
    LoopingCall(MyNode.neighbourhood.lookup).start(30)
    LoopingCall(client_heartbeat).start(20)
    LoopingCall(measure_latency).start(5)

    reactor.run()


if __name__ == '__main__':
    main()
