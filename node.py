import optparse, sys, json, socket, traceback, SocketServer, threading, time,\
        os

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
    id = "0"
    host = '127.0.0.1'
    my_sqn = 0
    neighbourhood = None
    overlay = None
    tcp_port = 13337
    udp_port = 13338
    TIMEOUT = 11
    HEARTBEAT = 5
    LOOKUP = 30
    PING = 20

    def get_node(self):
        return {"host" : self.host,
                "udp_port" : self.udp_port,
                "tcp_port" : self.tcp_port}

    def get_sqn(self):
        self.my_sqn = self.my_sqn + 1
        return self.my_sqn

MyNode = Node()

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
    is_complete = False

    def __init__(self, vir_nodes):
        global MyNode
        for node in vir_nodes:
            if not node == MyNode.id:
                self.nodes[str(node)] = {}
        self.lookup()

    def lookup(self):
        global MyNode
        for nodeID, node in self.nodes.items():
            send_msg(MyNode.monitor, {"command" : "lookup", "id" : nodeID})

    def check_complete(self):
        self.is_complete = True
        for node in self.nodes:
            if self.nodes[node] == {}:
                self.is_complete = False
                return

class Overlay(object):
    nodes = dict()
    last_msg = dict()
    edges = dict()
    route = dict()

    def __init__(self):
        self.edges[MyNode.id] = dict()

    def delete(self, node):
        global MyNode
        try:
            del self.nodes[node]
            del self.last_msg[node]
            del self.edges[node]
            del self.route[node]
            if node in MyNode.neighbourhood.nodes:
                MyNode.neighbourhood.nodes[node] = {}
            if node in MyNode.neighbourhood.pings:
                del MyNode.neighbourhood.pings[node]
        except:
            log("error", "Exception in Overlay.delete()")
            traceback.print_exc()
        self.dijkstra_dist()
        log("fail", "node"+node)
        print("FAIL node"+node)

    def view(self):
        global MyNode
        l = []
        for node in self.nodes:
            l.append(node)
        l.append(MyNode.id)
        return l

    def update_node(self, node, neighbours, sqn):
        node = str(node)
        if not node in self.nodes:
            log("join", "node"+node)
            print("JOIN node"+node)
        n = MyNode.neighbourhood.nodes
        if node in n and not "host" in n[node]:
            # Node in my neighbourhood joined, do lookup
            MyNode.neighbourhood.lookup()
        self.nodes[node] = sqn
        self.last_msg[node] = gettime()
        self.edges[node] = neighbours
        self.dijkstra_dist()
        log("Debug", "routing table: "+str(self.route))

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
        INF = 999999999999.0                # infinity value
        dist = dict()                # reset distances
        self.route = dict()         # reset routes
        v = dict()                  # initialise set with unvisited nodes
        for node in self.nodes:
            dist[node] = INF
            self.route[node] = []
            v[node] = 1
        dist[MyNode.id] = 0    # add myself
        self.route[MyNode.id] = []
        v[MyNode.id] = 1
        min_dist_id = MyNode.id     # set start node to myself
        min_dist_value = 0
        while len(v) > 0:           # while unvisited nodes
            min_dist_value = INF
            c = min_dist_id         # current selected node
            for (key,val) in self.edges[c].iteritems():
                if key in v:          # check all edges to unvisited nodes
                    if dist[c]+val < dist[key]:
                        dist[key] = dist[c]+val
                        self.route[key] = self.route[c][:]
                        self.route[key].append(c)
                    if dist[key] < min_dist_value:
                        min_dist_value = dist[key]
                        min_dist_id = key
            del v[c]
            if c == min_dist_id:
                # other nodes not reachable, finished
                v = dict()
        print("route table: "+str(self.route))
        log("Debug", "Dijkstra dist"+str(dist))
        log("Debug", "Dijkstra route"+str(self.route))


class ClientService(object):

    def OK(self, reply):
        pass

    def DNS_Reply(self, reply):
        global MyNode
        if "node" in reply:
            is_new = True
            try:
                if "host" in MyNode.neighbourhood.nodes[reply["id"]]:
                    is_new = False
            except:
                pass
            MyNode.neighbourhood.nodes[reply["id"]] = reply["node"]
            MyNode.neighbourhood.check_complete()
            if is_new:
                measure_latency()
                client_heartbeat()
            log("lookup", "node"+str(reply["id"])+"->"+str(reply["node"]))
        else:
            print "DNS reply did not contain node data"

    def DNS_Fail(self, reply):
        log("lookup", "node"+str(reply["id"])+" is not alive")

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
            try:
                log("overlay", str(MyNode.overlay.view()))
            except:
                traceback.print_exc()


    def RoutedMessage(self, pkg):
        print pkg
        if "route" in pkg and "data" in pkg:
            print("Forward routed message")
            del pkg["route"][0]
            if len(pkg["route"]) == 1 and pkg["route"][0] in MyNode.neighbourhood.nodes:
                print("forward to neighbour")
                print(pkg["data"])
                send_msg(MyNode.neighbourhood.nodes[pkg["route"][0]], pkg["data"])
            elif pkg["route"][0] in MyNode.neighbourhood.nodes:
                send_msg(MyNode.neighbourhood.nodes[pkg["route"][0]], pkg)
            else:
                print "I do not know %s" % pkg["route"][0]
                return {"command" : "error", "reason" : "I do not know node%s" %
                        pkg["route"][0]}
        else:
            print "Wrong format"
            return {"command" : "error", "reason" : "Wrong format"}

    def Reply(self, data):
        global MyNode
        print("ROUTET MESSAGE RECEIVED!!")
        if "source" in data:
            msg = {"command" : "ok"}
            send_routed_msg(data["source"], msg)
        else:
            log("error", "invalid Reply message")

    def Debug(self, data):
        print data
        log("Debug", "Got debug message: %s" % data)


    commands = {"ok"    : OK,
                "error" : Error,
                "dns_reply" : DNS_Reply,
                "dns_fail"  : DNS_Fail,
                "heartbeat" : Heartbeat,
                "route"     : RoutedMessage,
                "debug"     : Debug,
                "reply"     : Reply }

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
            self.sendString(json.dumps(reply))

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
        t = gettime() - float(s[1])
        MyNode.neighbourhood.pings[s[0]] = t
        log("Debug", "Ping to "+s[0]+" in "+str(t)+"ms")

    def sendDatagram(self):
        msg = str(self.nodeID)+":"+str(gettime())
        self.transport.write(msg)


# time function
def gettime():
    return int(round(time.time() * 10000))

# Ping request

def send_ping():
    global MyNode
    for nodeID, node in MyNode.neighbourhood.nodes:
        pass

# send TCP message
# msg should contain a command, se ClientService or MonitorService
def send_msg(address, msg):
    from twisted.internet import reactor
    service = ClientService()
    factory = NodeClientFactory(service, msg)
    factory.deferred.addErrback(error_callback)
    reactor.connectTCP(address["host"], address["tcp_port"], factory)
    return factory.deferred

# To send a routed message to node3 via node2 use following:
# send_routed_msg([2,3], message)
# Message should contain a command so that node3 knows
# what to do with it. It is essentially ekvivalent to send_msg method above.
def send_routed_msg(route, msg):
    global MyNode
    if MyNode.id in route:
        del route[MyNode.id]
    if len(route) == 1:
        return send_msg(MyNode.neighbourhood.nodes[route[0]], request)
    request = {"command" : "route", "route" : route, "source" : MyNode.id,
            "data" : msg}
    send_msg(MyNode.neighbourhood.nodes[route[0]], request)

def send_msg_to_node(nodeID, msg):
    global MyNode
    routes = MyNode.overlay.route
    if nodeID in routes:
        r = routes[nodeID]
        print(r)
        if len(r) == 0 or not r[0] == MyNode.id:
            log("error", "invalid route")
        else:
            if len(r) == 1:
                send_msg(MyNode.overlay.nodes[nodeID], msg)
            else:
                del r[0]
                r.append(nodeID)
                send_routed_msg(r, msg)
    log("Debug", "No route to send message")

def error_callback(s):
    log("Debug", "Error in sending message: %s " % str(s))

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

def alive_heartbeat():
    global MyNode
    for node,item in MyNode.overlay.last_msg.items():
        if MyNode.overlay.last_msg[node] + (MyNode.TIMEOUT*10000) < gettime():
            # assume node is dead
            MyNode.overlay.delete(node)

def route_msg_heartbeat():
    global MyNode
    source = "1"
    dest = "3"
    if MyNode.id == source:
        log("routed_msg", "Send msg from node"+source+" to node"+dest)
        k = 'a'*1000
        print("ROUTED MSG SENT")
        msg = {"command":"reply","time":str(gettime()), "load":k}
        send_msg_to_node(dest, msg)

#Ping call to measure the latency (called periodically by
# the reactor through LoopingCall)
def measure_latency():
    global MyNode
    log("Debug", "Measure latency: Sending ping to %d neighbours: %s" %
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
    if not MyNode.neighbourhood.is_complete:
        MyNode.neighbourhood.lookup()
    # send heartbeat msg to all neighbours
    log("Heartbeat", "Heartbeat node"+str(MyNode.id))
    msg = {"command":"heartbeat","source":MyNode.id,\
            "sequence":MyNode.get_sqn(),"neighbours":\
            MyNode.neighbourhood.pings}
    print("PINGS: "+str(MyNode.neighbourhood.pings))
    for nodeID, node in MyNode.neighbourhood.nodes.items():
        if "host" in node:
            send_msg(node, msg)

# So we can know if the node is alive
def monitor_heartbeat():
    global MyNode
    msg = {"command":"heartbeat","id":MyNode.id}
    send_msg(MyNode.monitor, msg)
 

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
    MyNode.id = str(options.id or 0)
    MyNode.host = options.iface or socket.gethostbyname(socket.gethostname())
    MyNode.tcp_port = options.tport or 0
    MyNode.udp_port = options.uport or 0
    if options.neighbours:
        MyNode.neighbourhood = Neighbourhood(json.loads(options.neighbours))
    else:
        MyNode.neighbourhood = Neighbourhood([0,1,2])

    from twisted.internet.task import LoopingCall

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

    def monitor_not_reachable(_):
        print "Monitor not reachable!"
        reactor.stop()

    d.addErrback(monitor_not_reachable)

    # refresh addresses periodically
    LoopingCall(MyNode.neighbourhood.lookup).start(MyNode.LOOKUP)
    LoopingCall(client_heartbeat).start(MyNode.HEARTBEAT)
    LoopingCall(measure_latency).start(MyNode.PING)
    LoopingCall(monitor_heartbeat).start(MyNode.HEARTBEAT)
    LoopingCall(alive_heartbeat).start(MyNode.HEARTBEAT)
    LoopingCall(route_msg_heartbeat).start(MyNode.PING)

    reactor.run()


if __name__ == '__main__':
    main()
