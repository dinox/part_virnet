import optparse, os, json, traceback, time, sys, signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, 'third_party', 'Twisted-13.1.0'))
sys.path.append(os.path.join(SCRIPT_DIR, 'third_party', 'zope.interface-4.0.5', 'src'))

from twisted.internet.protocol import ServerFactory, Protocol
from twisted.protocols.basic import NetstringReceiver
from twisted.internet.task import LoopingCall

nodes = []
inited = False

def parse_args():
    usage = """usage: %prog [options]"""

    parser = optparse.OptionParser(usage)

    help = "The port to listen on. Default to a random available port."
    parser.add_option('-p', '--port', type='int', help=help)

    help = "The interface to listen on. Default is 0.0.0.0."
    parser.add_option('--iface', help=help, default='0.0.0.0')

    help = "If you want debug output. Default is no."
    parser.add_option('-d', help=help, default=False)

    options, args = parser.parse_args()

    return options

class Logger(object):
    @staticmethod
    def log(time, id, event, desc):
        global is_debug_mode
        if id != "Monitor":
            id = "node%s" % id
        if event != "Debug" or is_debug_mode: 
            print "[%s] %s: %s: %s" % (time, id, event, desc)

    @staticmethod
    def log_self(event, desc):
        Logger.log(time.strftime("%H:%M:%S"), "Monitor", event, desc)

class Monitor(object):
    nodes = []

    def __init__(self):
        self.stable = True

    def alive_nodes(self):
        def alive(node):
            return node["alive"]
        return map(lambda n: int(n["id"]), filter(alive, self.nodes))

    def stable_nodes(self):
        stable = []
        for node in self.nodes:
            if node["stable"]:
                stable.append(int(node["id"]))
        return stable

    def add_node(self, id, node):
        node["alive"] = True
        node["stable"] = False
        node["id"] = int(id)
        node["ping"] = time.time()
        curr = self.get_node(id)
        if curr:
            for k, v in node.items():
                curr[k] = v
            return
        self.nodes.append(node)

    def get_node(self, id):
        ret = filter(lambda n: n["id"] == int(id), self.nodes)
        if len(ret):
            return ret[0]
        return None

    def get_lookup_node(self, id):
        node = self.get_node(id)
        keys = ["host", "tcp_port", "udp_port"]
        if node:
            return {key : node[key] for key in keys}
        return None

    def view_is_same_as(self, other):
        return self.alive_nodes() == list(set(other) & set(self.alive_nodes()))

class MonitorService(object):

    def __init__(self, monitor):
        self.monitor = monitor

    def DNS_Lookup(self, data):
        try:
            if "id" in data and self.monitor.get_node(data["id"]):
                return json.dumps({"command" : "dns_reply", "node" :
                    self.monitor.get_lookup_node(data["id"]), "id" : data["id"]})
            else:
                return json.dumps({"command" : "dns_fail", "reason" : "id does not " +
                    "exist", "id" : data["id"]})
        except:
            traceback.print_exc()
            return json.dumps({"command" : "error", "reason" : "Exception"})

    def DNS_Map(self, data):
        if "id" in data and "node" in data:
            try:
                self.monitor.add_node(data["id"], data["node"])
            except:
                traceback.print_exc()
                return json.dumps({"command" : "error", "reason" : "Eception"})
            Logger.log_self("New node", "Added node%s to DNS list" % data["id"])
            return json.dumps({"command" : "ok"})
        return json.dumps({"command" : "error", "reason" : "No id or no node in " +
                            "message"})

    def Log(self, data):
        def message(command, d):
            d["command"] = command
            return json.dumps(d)
        if not "id" in data:
            return message("error", {"reason" : "id not in log message"})
        if not "time" in data:
            return message("error", {"reason" : "time not in log message"})
        if not "event" in data:
            return message("error", {"reason" : "event not in log message"})
        if not "desc" in data:
            return message("error", {"reason" : "desc not in log message"})
        Logger.log(data["time"], data["id"], data["event"], data["desc"])
        return message("ok", {})

    def Heartbeat(self, data):
        Logger.log_self("Debug", str(data))
        if "id" in data and self.monitor.get_node(data["id"]):
            self.monitor.get_node(data["id"])["ping"] = time.time()
            self.monitor.get_node(data["id"])["alive"] = True
        return json.dumps({"command" : "ok"})

    def Overview(self, data):
        if "id" in data and "nodes" in data:
            if self.monitor.view_is_same_as(map(int, data["nodes"])):
                self.monitor.get_node(data["id"])["stable"] = True
            else:
                self.monitor.get_node(data["id"])["stable"] = True
        return json.dumps({"command" : "ok"})

    commands = { "lookup"   : DNS_Lookup,
                 "map"      : DNS_Map   ,
                 "log_msg"  : Log       ,
                 "heartbeat": Heartbeat ,
                 "overlay_view" : Overview}

class MonitorProtocol(NetstringReceiver):
    def stringReceived(self, request):
        if is_debug_mode:
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
            if is_debug_mode:
                print "Sent: %s" % reply
            self.sendString(reply)

        self.transport.loseConnection()

class MonitorFactory(ServerFactory):

    protocol = MonitorProtocol

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



def main():
    global is_debug_mode
    options = parse_args()
    is_debug_mode = options.d
    monitor = Monitor()
    service = MonitorService(monitor)
    factory = MonitorFactory(service)

    from twisted.internet import reactor
    port = reactor.listenTCP(options.port or 0, factory,
                             interface=options.iface)
    print 'Listening on %s.' % (port.getHost())

    def alive_nodes():
        for node in monitor.nodes:
            if node["ping"] < time.time() - 5:
                node["alive"] = False

    def log_status():
        Logger.log_self("status", "DNS nodes: %s" %
                str(monitor.nodes))
        Logger.log_self("status", "Alive nodes: %s" %
                str(monitor.alive_nodes()))
        Logger.log_self("status", "Stable nodes: %s" %
                str(monitor.stable_nodes()))

    def stable_network():
        if not monitor.stable:
            if monitor.alive_nodes() == monitor.stable_nodes():
                stable = True
                send_signal()

    def send_signal():
        f = open("startup.pid", 'w')
        try:
            n = int(f.read())
            os.kill(n, 1)
        except:
            pass

    def network_inited():
        global inited
        if not inited and len(monitor.nodes) == 15:
            send_signal()
            inited = True

    LoopingCall(log_status).start(10)
    LoopingCall(alive_nodes).start(1)
    LoopingCall(stable_network).start(1)
    LoopingCall(network_inited).start(1)

    reactor.run()

if __name__ == '__main__':
    main()
