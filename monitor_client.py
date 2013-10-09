from twisted.internet.protocol import Protocol, ClientFactory

class OverlayProtocol(Protocol):
    data = ''

    def dataReceived(self, data):
        self.data += data

    def connectionLost(self, reason):
        self.finishRecieved(self.data)

    def finishReceived(self, data):
        self.factory.receive_finished(data)

class MonitorClientFactory(Clientfactory):
    protocol = OverlayProtocol

    def buildProtocol(self, address):
        return ClientFactory.buildProtocol(self, address)

    def receive_finished(self, data):
        self.data = data
        from twisted.internet import reactor
        reactor.stop()

def main():
    factory = MonitorClientFactory()
    host = "127.0.0.1"
    port = 13337


    reactor.connectTCP(host, port, factory)
    reactor.run()
    print factory.data

if __name__ == '__main__':
    main()

