import optparse, sys, json, socket, traceback, SocketServer, threading, time, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, 'third_party', 'Twisted-13.1.0'))
sys.path.append(os.path.join(SCRIPT_DIR, 'third_party', 'zope.interface-4.0.5', 'src'))

from twisted.internet import defer, reactor
from twisted.internet.protocol import Protocol, ClientFactory, ServerFactory,\
    DatagramProtocol
from twisted.protocols.basic import NetstringReceiver

#global variables
class Node(object):
    monitor = "undefinded"
    id = 0
    host = '127.0.0.1'
    my_sqn = 0
    neighbourhood = None
    overlay = None
    tcp_port = 13337
    udp_port = 13338

    def get_node(self):
        return {"host" : self.host,
                "udp_port" : self.udp_port,
                "tcp_port" : self.tcp_port}

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
    parser.add_option('-i', '--id', type='int', help=help)

    help = "The tcp port to listen on. Default to a random available port."
    parser.add_option('-t', '--tport', type='int', help=help)

    help = "The udp port to listen on. Default to a random available port."
    parser.add_option('-u', '--uport', type='int', help=help)

    help = "The interface to listen on."
    parser.add_option('--iface', help=help)

    help = "The node's neighbourhood, formatted as json list"
    parser.add_option('-n', '--neighbours', help=help)

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

        return {"host" : host, "tcp_port" : int(port)}

    return options, parse_address(address[0])

class Neighbourhood(object):
    nodes = dict()
    pings = dict()

    def __init__(self, vir_nodes):
        global MyNode
        for node in vir_nodes:
            if not node == MyNode.id:
                self.nodes[node] = {}
        self.lookup()

    def lookup(self):
        global MyNode
        from twisted.internet import reactor
        for nodeID, node in self.nodes.items():
            if "host" not in node:
                send_msg(MyNode.monitor, {"command" : "lookup", "id" : nodeID})


    def add_node():
        log_status("Neighbourhood lookup")

class Overlay(object):
    nodes = dict()
    last_msg = dict()
    edges = dict()
    dist = dict()
    route = dict()

    def __init__(self):
        self.edges[MyNode.id] = dict()

    def update_node(self, node, neighbours, sqn):
        self.nodes[node] = sqn
        self.last_msg[node] = time.time()
        self.edges[node] = neighbours
        self.dijkstra_dist()

    def is_valid_msg(self, msg):
        if msg["source"] == MyNode.id:
            return False
        if not msg["source"] in self.nodes:
            return True
        if self.nodes[msg["source"]] < msg["sequence"]:
            return True
        else:
            return False

    def dijkstra_dist(self):
        self.edges[MyNode.id] = MyNode.neighbourhood.pings
        INF = 1000.0                # infinity value
        self.dist = dict()          # reset distances
        self.route = dict()         # reset routes
        v = dict()                  # initialise set with unvisited nodes
        for node in self.nodes:
            self.dist[node] = INF
            self.route[node] = []
            v[node] = 1
        self.dist[MyNode.id] = 0    # add myself
        self.route[MyNode.id] = []
        v[MyNode.id] = 1
        min_dist_id = MyNode.id     # set start node to myself
        min_dist_value = 0
        while len(v) > 0:           # while unvisited nodes
            min_dist_value = INF
            c = min_dist_id         # current selected node
            print(self.edges[c])
            for (key,val) in self.edges[c].iteritems():
                if key in v:          # check all edges to unvisited nodes
                    if self.dist[c]+val < self.dist[key]:
                        self.dist[key] = self.dist[c]+val
                        self.route[key] = self.route[c][:]
                        self.route[key].append(c)
                    if self.dist[key] < min_dist_value:
                        min_dist_value = self.dist[key]
                        min_dist_id = key
            del v[c]
            if c == min_dist_id:
                # other nodes not reachable, finished
                v = dict()
        print("DIJKSTRA FINISHED!")
        print(self.dist)
        print(self.route)


class ClientService(object):

    def OK(self, reply):
        pass

    def DNS_Reply(self, reply):
        global MyNode
        if "node" in reply:
            MyNode.neighbourhood.nodes[reply["id"]] = reply["node"]
            log_lookup(reply["id"], reply["node"])
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
            for nodeID,node in MyNode.neighbourhood.nodes.items():
                if "host" in node:
                    send_msg(node, reply)
            log_overlay()

    commands = {"ok"    : OK,
                "error" : Error,
                "dns_reply" : DNS_Reply,
                "heartbeat" : Heartbeat }

class ClientProtocol(NetstringReceiver):

    def connectionMade(self):
        self.sendRequest(self.factory.request)

    def sendRequest(self, request):
        self.sendString(json.dumps(request))

    def stringReceived(self, reply):
        self.transport.loseConnection()
        reply = json.loads(reply)
        command = reply["command"]

        if command not in self.factory.service.commands:
            print "Command <%s> does not exist!" % command
            self.transport.loseConnection()
            return

        self.factory.handleReply(command, reply)

class ServerProtocol(NetstringReceiver):
    def stringReceived(self, request):
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
    def datagramReceived(self, data, (host, port)):
        self.transport.write(data, (host, port))

class UDPClient(DatagramProtocol):

    host = ''
    port = 0
    node = 0

    def __init__(self, node, nodeID):
        self.host = node["host"]
        self.port = node["udp_port"]
        self.nodeID = nodeID

    def startProtocol(self):
        self.transport.connect(self.host, self.port)
        self.sendDatagram()

    def datagramReceived(self, datagram, host):
        global MyNode
        s = datagram.split(":")
        t = self.time() - int(s[1])
        MyNode.neighbourhood.pings[int(s[0])] = t
#TODO: log pings

    def sendDatagram(self):
        msg = str(self.nodeID)+":"+str(time.time())
        self.transport.write(msg)
    def time(self):
        return int(round(time.time() * 10000))

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
    reactor.connectTCP(address["host"], address["tcp_port"], factory)
    return factory.deferred

def error_callback(s):
    log("Debug", "Error in sending message: %s " % str(s))

# Log functions

def log_status(msg):
    global LOG_FILE
    msg = "    " + msg
    filename = LOG_FILE
    log_timestamp(filename)
    f = open(filename, "a")
    f.write(msg + "\n")
    f.close()
    print(msg)

def log_overlay():
    global LOG_FILE
    filename = LOG_FILE
    log_timestamp(filename)
    log_members(filename)

def log_lookup(node, address):
    global LOG_FILE
    filename = LOG_FILE
    log_timestamp(filename)
    tab = "    "
    msg = tab + "[LOOKUP]: node" + str(node) + "->" + address["host"]+\
            ":" + str(address["tcp_port"])
    f = open(filename, "a")
    f.write(msg + "\n")
    print(msg)
    f.close()

def log_timestamp(filename):
    f = open(filename, "a")
    msg = time.strftime("%Y/%m/%d %H:%M:%S") + ":"
    f.write(msg + "\n")
    print(msg)
    f.close()

def log_members(filename):
    global MyNode
    f = open(filename, "a")
    tab = "    "
    dtab = tab + tab
    msg = "[OVERLAY]: node" + str(MyNode.id)
    f.write(msg + "\n")
    print(msg)
    for node in MyNode.overlay.nodes:
        msg = dtab + "node" + str(node) + "[sqn:" +\
                str(MyNode.overlay.nodes[node]) +\
                ",t:" + str(MyNode.overlay.last_msg[node]) + "]: "+\
                str(MyNode.overlay.edges[node])
        f.write(msg + "\n")
        print(msg)
    f.close()

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
    print(msg)
    f.write(msg + "\n")
    f.close()

# Monitor logger function
# No linebreaks in event or desc!
# If event == "Debug" it is only shown when monitor is in debug mode.
def log(event, desc): 
    global MyNode
    data = dict()
    data["event"] = event
    data["desc"] = desc
    data["time"] = time.strftime("%H:%M:%S")
    data["command"] = "log_msg"
    data["id"] = MyNode.id
    send_msg(MyNode.monitor, data)

#Ping call to measure the latency (called periodically by
# the reactor through LoopingCall)
def measure_latency():
    global MyNode
    log_status("MEASURE LATENCY")
    print(MyNode.neighbourhood.nodes)
#TODO: Add something funnier than a empty string here (but dont clutter down the
#      log window
    log("Measure latency", "Sending ping to %d neighbours: %s" %
            (len(MyNode.neighbourhood.nodes),
                str(MyNode.neighbourhood.nodes.keys())))
    for nodeID, node in MyNode.neighbourhood.nodes.items():
        if "host" in node:
            protocol = UDPClient(node, nodeID)
            reactor.listenUDP(0, protocol)

# Heartbeat function of the client (called periodically 
# by the reactor through LoopingCall)
#   Collect pings from neighbours
#   Send alive message
def client_heartbeat():
    global MyNode
    # send heartbeat msg to all neighbours
    log_status("Client Heartbeat")
    msg = {"command":"heartbeat","source":MyNode.id,\
            "sequence":MyNode.get_sqn(),"neighbours":\
            MyNode.neighbourhood.pings}
    for nodeID, node in MyNode.neighbourhood.nodes.items():
        if "host" in node:
            send_msg(node, msg)

# INITIALIZATION
def init_with_monitor(monitor, node, my_id):
    """
    Register our DNS data and id_nbr with the monitor at host:port.
    """
    from twisted.internet import reactor
    service = ClientService()
    factory = NodeClientFactory(service, {"command" : "map", "id" : my_id, 
                                            "node" : node})
    reactor.connectTCP(monitor["host"], monitor["tcp_port"], factory)
    return factory.deferred


# MAIN

def main():
    global MyNode
    options, MyNode.monitor = parse_args()
    MyNode.id = options.id or 0
    MyNode.host = options.iface or socket.gethostbyname(socket.gethostname())
    MyNode.tcp_port = options.tport or 0
    MyNode.udp_port = options.uport or 0
    if options.neighbours:
        MyNode.neighbourhood = Neighbourhood(json.loads(options.neighbours))
    else:
        MyNode.neighbourhood = Neighbourhood([0,1,2])

    from twisted.internet.task import LoopingCall

    log_status("Startup node" + str(MyNode.id) + " with tcp address " +\
            str(MyNode.host)+":"+str(MyNode.tcp_port))

    # initialize UDP socket
    listen_udp = reactor.listenUDP(MyNode.udp_port, UDPServer(), interface=MyNode.host)
    log("init", 'Listening on %s.' % (listen_udp.getHost()))
    MyNode.udp_port = listen_udp.getHost().port

    service = ClientService()
    factory = NodeServerFactory(service)
    listen_tcp = reactor.listenTCP(MyNode.tcp_port, factory, interface=MyNode.host)
    log("init", 'Listening on %s.' % (listen_tcp.getHost()))
    MyNode.tcp_port = listen_tcp.getHost().port

    # initialize Neighbourhood
    MyNode.overlay = Overlay()

    d = init_with_monitor(MyNode.monitor,\
            MyNode.get_node(), MyNode.id)

    # refresh addresses periodically
    LoopingCall(MyNode.neighbourhood.lookup).start(30)
    LoopingCall(client_heartbeat).start(20)
    LoopingCall(measure_latency).start(5)

    reactor.run()


if __name__ == '__main__':
    main()
