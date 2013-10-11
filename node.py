import optparse, sys, json, socket, traceback

from twisted.internet import defer
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.protocols.basic import NetstringReceiver



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

class MonitorClientService(object):

    def OK(self, reply):
        pass

    def DNS_Reply(self, reply):
        if "node" in reply:
            return reply["node"]
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

def main():
    options, monitor = parse_args()
    my_id = options.id or 0
    my_node = {"host" : options.iface or
            socket.gethostbyname(socket.gethostname()),
            "port" : options.port or 0}
    from twisted.internet import reactor

    def init_done(s):
        print "Initialized"

    def all_done(_):
        print "Exiting..."
        reactor.stop()

    d = init_with_monitor(monitor, my_node, my_id)
    d.addBoth(init_done)
    d.addBoth(all_done)

    reactor.run()


if __name__ == '__main__':
    main()
