import optparse, sys, json, socket, traceback, SocketServer, threading

from twisted.internet import defer
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.protocols.basic import NetstringReceiver

#global variables
monitor = "undefinded"
my_id = 0
my_node = '127.0.0.1'
neighbourhood = None

# global output file names
LOG_FILE = "overlag.log"
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
    is_initialized = False
    nodeIDs = []
    addresses = dict()

    def __init__(self, vir_nodes):
        global my_id
        for node in vir_nodes:
            if not node == my_id:
                self.nodeIDs.append(node)
        self.lookup()

    def lookup(self):
        global monitor, my_id
        from twisted.internet import reactor
        for node in self.nodeIDs:
            service = MonitorClientService()
            factory = MonitorClientFactory(service, {"command" : "lookup", "id"
                : node})
            reactor.connectTCP(monitor["host"], monitor["port"], factory)
        log_status("Neighbourhood lookup")

class MonitorClientService(object):

    def OK(self, reply):
        pass

    def DNS_Reply(self, reply):
        global neighbourhood
        if "node" in reply:
            neighbourhood.addresses[reply["id"]] = reply["node"]
        else:
            print "DNS reply did not contain node data"

    def Error(self, reply):
        if "reason" in reply:
            print "Unexpected error: %s" % reply["reason"]
        else:
            print "Unexpected error with no reason"

    commands = {"ok"    : OK,
                "error" : Error,
                "dns_reply" : DNS_Reply }

class MonitorClientProtocol(NetstringReceiver):

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

class MonitorClientFactory(ClientFactory):

    protocol = MonitorClientProtocol

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

# UDP serversocket, answers to ping requests

class MyUDPServer(SocketServer.ThreadingUDPServer):
    allow_reuse_address = True

class MyUDPServerHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        global last_ping, my_port, members, coordinator, my_id, is_alive,\
                COORDINATOR_TIMEOUT, DEBUG_MODE
        if time.time() > is_alive + COORDINATOR_TIMEOUT:
            # too long not alive, kill myself
            log_exception("DEAD in MyUDPServerHandler.handle", "Assume main" + \
                    "thread is dead, kill myself.")
            sys.exit()
        try:
            data = self.request[0].decode().strip()
            socket = self.request[1]
            # Reply with our ID
            socket.sendto(str(my_id).encode(), self.client_address)
            # If ping was from coordinator, update last_time variable with the
            # current time
            if str(data) == str(coordinator["id"]):
                last_ping = time.time()
        except Exception, e:
            log_exception("EXCEPTION in MyUDPServerHandler.handle", e)
            if DEBUG_MODE:
                traceback.print_exc()

# Ping request

def send_ping():
    global neighbourhood
    for nodeID, node in neighbourhood.nodeIDs:
        pass

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
    service = MonitorClientService()
    factory = MonitorClientFactory(service, {"command" : "map", "id" : my_id, 
                                            "node" : my_node})
    reactor.connectTCP(monitor["host"], monitor["port"], factory)
    return factory.deferred

def test():
    global monitor, my_id
    from twisted.internet import reactor
    service = MonitorClientService()
    factory = MonitorClientFactory(service, {"command" : "lookup", "id" : my_id})
    reactor.connectTCP(monitor["host"], monitor["port"], factory)

#Ping call to measure the latency (called periodically by
# the reactor through LoopingCall)
def measure_latency():
    pass

# Heartbeat function of the client (called periodically 
# by the reactor through LoopingCall)
#   Collect pings from neighbors
#   Send alive message
def client_heartbeat():
    global neighbourhood
    if not neighbourhood.is_initialized:
        neighbourhood.initialize()

# INITIALIZATION

def initialize_UDP_socket(port):
    # listen for UDP messages for ping request
    pingServer = MyUDPServer(('0.0.0.0', port), MyUDPServerHandler)
    pingThread = threading.Thread(target=pingServer.serve_forever)
    pingThread.daemon = True
    pingThread.start()

# create dummy/test neighbourhood, should be replaced with real neighourhood
# initialization
def init_neighbourhood_dummy(vir_nodes):
    global neighbourhood
    neighbourhood = Neighbourhood(vir_nodes)


# MAIN

def main():
    global monitor, my_id, my_node, neighbourhood
    options, monitor = parse_args()
    my_id = options.id or 0
    my_node = {"host" : options.iface or
            socket.gethostbyname(socket.gethostname()),
            "port" : options.port or 13337}
    from twisted.internet import reactor
    from twisted.internet.task import LoopingCall

    log_status("Startup node" + str(my_id) + " with address " + str(my_node))

    initialize_UDP_socket(my_node["port"]+1)

    # initialize Neighbourhood
    init_neighbourhood_dummy([0,1,2,3])

    def init_done(s):
        print "Initialized"

    def all_done(_):
        print "Exiting..."
        reactor.stop()

    d = init_with_monitor(monitor, my_node, my_id)
    d.addBoth(init_done)
    #d.addBoth(all_done)

    #lc = LoopingCall(test)
    #lc.start(2)

    lc = LoopingCall(neighbourhood.lookup)
    lc.start(5)

    reactor.run()


if __name__ == '__main__':
    main()
