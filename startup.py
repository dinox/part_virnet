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
    except:
        print "Could not connect to %s" % node
        return
    print "[%s]Connected" % node["id"]
    try:
        remote["rm"]("-r", "overlay")
    except commands.processes.ProcessExecutionError:
        pass
    print "[%s]Downloading application..." % node["id"]
    remote["wget"]("-O", "overlay.tar.gz", 
            "https://api.github.com/repos/dinox/part_virnet/tarball")
    remote["tar"]("-xvzf", "overlay.tar.gz", "--transform",
            "s/dinox-part_virnet......../overlay/")
    remote["mv"]("overlay/node.py", ".")
    try:
        print "[%s]Downloading python..." % node["id"]
        remote["wget"]("-O", "python2.7-static",
                "http://pts-mini-gpl.googlecode.com/svn/trunk/staticpython/release/python2.7-static")
        remote["chmod"]("u+x",  "python2.7-static")
        print "[%s]Getting Twisted..." % node["id"]
        remote["wget"]("-O", "py2.7-twisted.tar.gz", 
                "https://www.dropbox.com/s/4ftmk62rh9py7yj/py2.7-twisted.tar.gz")
        remote["tar"]("-xvzf", "py2.7-twisted.tar.gz")
    except:
        print "[%s]Got an exception, continue with fingers crossed" % node["id"]
    print "[%s]Starting python node..." % node["id"]
    try:
        print remote["./python2.7-static"]("node.py", 
                "--id", "%s" % (node["id"]), "--neighbours", 
                json.dumps(neighbourhood[node["id"]]), "erikhenriksson.se:12345")
    except commands.processes.ProcessExecutionError as e:
        print "[%s]Got an exception: %s" % (node["id"], e)
    remote.close()

pool_size = 15  # your "parallelness"
pool = Pool(pool_size)
pool.map(start_node, nodes)
