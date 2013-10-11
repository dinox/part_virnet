import optparse, os, json, traceback
from twisted.internet.protocol import ServerFactory, Protocol
from twisted.protocols.basic import NetstringReceiver

def parse_args():
    usage = """usage: %prog [options]"""

    parser = optparse.OptionParser(usage)

    help = "The port to listen on. Default to a random available port."
    parser.add_option('--port', type='int', help=help)

    help = "The interface to listen on. Default is 0.0.0.0."
    parser.add_option('--iface', help=help, default='0.0.0.0')

    options, args = parser.parse_args()

    return options

class Monitor(object):
    nodes = {}

class MonitorService(object):

    def __init__(self, monitor):
        self.monitor = monitor

    def DNS_Lookup(self, data):
        if "id" in data and data["id"] in self.monitor.nodes:
            return json.dumps({"command" : "dns_reply", "node" :
                self.monitor.nodes[data["id"]]})
        else:
            return json.dumps({"command" : "error", "reason" : "id does not " +
                                "exist"})

    def DNS_Map(self, data):
        if "id" in data and "node" in data:
            try:
                self.monitor.nodes[data["id"]] = data["node"]
            except:
                return json.dumps({"command" : "error", "reason" : ""})
            return json.dumps({"command" : "ok"})
        return json.dumps({"command" : "error", "reason" : "No id or no node in " +
                            "message"})

    commands = { "lookup"   : DNS_Lookup,
                 "map"      : DNS_Map   }

class MonitorProtocol(NetstringReceiver):
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
    options = parse_args()
    monitor = Monitor()
    service = MonitorService(monitor)
    factory = MonitorFactory(service)

    from twisted.internet import reactor
    port = reactor.listenTCP(options.port or 0, factory,
                             interface=options.iface)
    print 'Listening on %s.' % (port.getHost())
    reactor.run()

if __name__ == '__main__':
    main()
