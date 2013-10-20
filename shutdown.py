from plumbum import SshMachine, commands
from multiprocessing.pool import ThreadPool as Pool
import time, json

p = open("startup_config.json", "r")
conf = json.loads(p.read())
username = conf["username"]
path_to_keyfile = conf["path_to_keyfile"]

nodes = []
f = open("nodes.txt", "r")
n = open("neighbourhood.json", "r")

print """ Welcome to the super shutdowm script by
Erik Henriksson & Christoph Burkhalter. """

for line in f:
    s = line.strip().split(":")
    nodes.append({"id" : s[0], "host" : s[1]})

neighbourhood = json.loads(n.read())

def start_node(node):
    print "Connecting to node%s with hostname %s" % (node["id"], node["host"])
    try:
        remote = SshMachine(node["host"], port = 22022, user = username, 
                keyfile = path_to_keyfile)
    except:
        print "Could not connect to %s" % node
        return
    print "[%s]Connected" % node["id"]
    print "[%s]Killing python..." % node["id"]
    try:
        remote["killall"]("node")
    except Exception as e:
        print "[%s]Exception: %s" % (node["id"], e)
        print "[%s]Python could not get killed" % node["id"]
    remote.close()

pool_size = 15  # your "parallelness"
pool = Pool(pool_size)
pool.map(start_node, nodes)
