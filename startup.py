from plumbum import SshMachine, commands
from multiprocessing.pool import ThreadPool as Pool
import time

# Change these
username = "user13"
path_to_keyfile = "/Users/erik/.ssh/user13"

nodes = []
f = open("nodes.txt", "r")

for line in f:
    s = line.strip().split(":")
    nodes.append({"id" : s[0], "host" : s[1]})

def start_node(node):
    print "Connecting to node%s with hostname %s." % (node["id"], node["host"])
    try:
        remote = SshMachine(node["host"], port = 22022, user = username, 
                keyfile = path_to_keyfile)
    except:
        print "Could not connect to %s" % node
    else:
        try:
            remote["rm"]("-r", "overlay")
        except commands.processes.ProcessExecutionError:
            pass
        remote["wget"]("-O", "overlay.tar.gz", 
                "https://api.github.com/repos/dinox/part_virnet/tarball")
        remote["tar"]("-xvzf", "overlay.tar.gz", "--transform",
                "s/dinox-part_virnet......../overlay/")
        remote["wget"]("-O", "python2.7-static",
                "http://pts-mini-gpl.googlecode.com/svn/trunk/staticpython/release/python2.7-static")
        remote["chmod"]("u+x",  "python2.7-static")
        remote["wget"]("-O", "py2.7-twisted.tar.gz", 
                "https://www.dropbox.com/s/4ftmk62rh9py7yj/py2.7-twisted.tar.gz")
        remote["tar"]("-xvzf", "py2.7-twisted.tar.gz")
        print remote["./python2.7-static"].run("overlay/node.py", 
                "--id %s" % (node["id"]), "erikhenriksson.se:13337")
    remote.close()

pool_size = 15  # your "parallelness"
pool = Pool(pool_size)
for node in nodes:
    pool.apply_async(start_node, (node,))
    time.sleep(0.1)
pool.close()
pool.join()
