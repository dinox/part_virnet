import optparse, os

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

class MonitorService(object):
    def DNS_Lookup(self, data):
        return json.loads({"command" : "ok"})

    def DNS_Map(self, data):
        return json.loads({"command" : "ok"})

    commands = { "lookup"   : DNS_Lookup,
                 "map"      : DNS_Map   }

class MonitorProtocol(NetstringReceiver):

    def stringReceived(self, request):
        print "Received: %s" % request
        if command not in self.service.commands:
            self.transport.loseConnection()
            return
        command = json.loads(request)[command]
        data = json.loads(request)
        self.commandReceived(command, data)

    def commandReceived(self, command, data):
        reply = self.factory.reply(command, data)

        if reply is not None:
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
            return create_reply(data)
        except:
            return None # command failed

def main():
    options = parse_args()

    service = MonitorService()

    factory = MonitorFactory(service)

    from twisted.internet import reactor

    port = reactor.listenTCP(options.port or 0, factory,
                             interface=options.iface)

    print 'Serving %s.' % (port.getHost())

    reactor.run()


if __name__ == '__main__':
    main()
