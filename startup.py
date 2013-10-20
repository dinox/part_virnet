from plumbum import SshMachine, commands
from multiprocessing.pool import ThreadPool as Pool
import time, json

# Change these
username = "user13"
path_to_keyfile = "/Users/erik/.ssh/user13"
p = open("startup_config.json", "r")
conf = json.loads(p.read())
username = conf["username"]
path_to_keyfile = conf["path_to_keyfile"]

nodes = []
f = open("nodes.txt", "r")
n = open("neighbourhood.json", "r")

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
                keyfile = path_to_keyfile)
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
        print remote["./node"]("--id", "%s" % (node["id"]), "--neighbours", 
                json.dumps(neighbourhood[node["id"]]), "erikhenriksson.se:12345")
    except commands.processes.ProcessExecutionError as e:
        print "[%s]Got an exception: %s" % (node["id"], e)
    remote.close()

pool_size = 15  # your "parallelness"
pool = Pool(pool_size)
pool.map(start_node, nodes)
