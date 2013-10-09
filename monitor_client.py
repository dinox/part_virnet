from twisted.internet.protocol import Protocol, ClientFactory
import sys

class OverlayProtocol(Protocol):
    data = ''

    def dataReceived(self, data):
        self.data += data

    def connectionLost(self, reason):
        self.finishRecieved(self.data)

    def finishReceived(self, data):
        self.factory.receive_finished(data)

class MonitorClientFactory(ClientFactory):
    protocol = OverlayProtocol

    def __init__(self, callback, errback):
        self.callback = callback
        self.errback = errback

    def buildProtocol(self, address):
        return ClientFactory.buildProtocol(self, address)

    def receive_finished(self, data):
        self.callback(data)

    def clientConnectionFailed(self, connector, reason):
        self.errback(reason)

def get_data(host, port, callback, errback):
    from twisted.internet import reactor
    factory = MonitorClientFactory(callback, errback)
    reactor.connectTCP(host, port, factory)

def main():
    host = "127.0.0.1"
    port = 13337

    data = ''

    from twisted.internet import reactor

    def got_data(d):
        data = d
        reactor.stop()

    def got_err(err):
        print >>sys.stderr, 'TCP Connection failed:', err
        conn_done()

    def conn_done():
        reactor.stop()

    get_data(host, port, got_data, got_err)

    reactor.run()

    print data


if __name__ == '__main__':
    main()

