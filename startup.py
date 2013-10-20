from plumbum import SshMachine, commands
from multiprocessing.pool import ThreadPool as Pool
from multiprocessing import Process, Array, Value
import time, json, threading, signal, os

# Change these
username = "user13"
path_to_keyfile = "/Users/erik/.ssh/user13"
p = open("startup_config.json", "r")
conf = json.loads(p.read())
username = conf["username"]
path_to_keyfile = conf["path_to_keyfile"]
logfile = open("kill.log", "w")

nodes = []
f = open("nodes.txt", "r")
n = open("neighbourhood.json", "r")

k_node = 1
got_signal = False

print """ Welcome to the super startup script by
Erik Henriksson & Christoph Burkhalter. """

for line in f:
    s = line.strip().split(":")
    nodes.append({"id" : s[0], "host" : s[1]})

neighbourhood = json.loads(n.read())

def start_node(node):
    print "Connecting to node%s with hostname %s." % (node["id"], node["host"])
    try:
        remote = SshMachine(node["host"], port = 22022, user = username, 
                keyfile = path_to_keyfile, ssh_opts=["-o", "StrictHostKeyChecking=no"])
    except Exception as e:
        print "Could not connect to %s: %s" % (node["host"], e)
        return
    print "[%s]Connected" % node["id"]
    try:
        remote["rm"]("node")
    except commands.processes.ProcessExecutionError:
        pass
    print "[%s]Downloading application..." % node["id"]
    remote["wget"]("-O", "node", 
        "https://www.dropbox.com/s/mjw7dic2ywk5jrp/node")
    remote["chmod"]("u+x", "node")
    print "[%s]Starting python node..." % node["id"]
    try:
        remote["./node"]("--id", "%s" % (node["id"]), "--neighbours", 
                json.dumps(neighbourhood[node["id"]]),
                "erikhenriksson.se:12345")
    except commands.processes.ProcessExecutionError as e:
        print "[%s]Got an exception: %s" % (node["id"], e)
    remote.close()

def kill_node(node):
    print "Killing node%s" % node["id"]
    try:
        remote = SshMachine(node["host"], port = 22022, user = username, 
                keyfile = path_to_keyfile, ssh_opts=["-o StrictHostKeyChecking=no"])
    except Exception as e:
        print "Could not connect to %s: %s" % (node["host"], e)
        return
    try:
        remote["killall"]("node")
    except:
        print "Could not kill node%s" % node["id"]
    else:
        print "Node%s killed!" % node["id"]
    remote.close()


def kill_script(nodes):
    global logfile
    print "Waiting for network to initialize"
    wait_for_signal()
    print "Start killing nodes..."
    for node in nodes:
        kill_node(node)
        begin = time.time()
        wait_for_signal()
        end = time.time()
        print "Kill node%s: Network reaction time: %.3f seconds" % (node["id"], end-begin)
        logfile.write("%.3f:%s\n" % (end-begin, node["id"]))
        Process(target=start_node, args=(node,)).start()
        begin = time.time()
        wait_for_signal()
        end = time.time()
        logfile.write("%.3f:%s\n" % (end-begin, node["id"]))
        print "Start node%s: Network reaction time: %.3f seconds" % (node["id"], end-begin)

def wait_for_signal():
    global got_signal
    while not got_signal:
        time.sleep(0.01)
    got_signal = False

def signal_handler(signum, frame):
    global got_signal
    print 'Signal handler called with signal', signum
    got_signal = True

signal.signal(signal.SIGUSR1, signal_handler)
pid = str(os.getpid())
pidfile = "startup.pid"
file(pidfile, 'w').write(pid)
print "pid = %s" % pid
for node in nodes:
    Process(target=start_node, args=(node,)).start()
    pass
kill_script(nodes)
os.unlink(pidfile)
