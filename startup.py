from plumbum import SshMachine

# Change these
username = "user13"
path_to_keyfile = "/home/erik/.ssh/user13"

nodes = []
f = open("nodes.txt", "r")

for line in f:
  s = line.strip().split(":")
  nodes.append({"id" : s[0], "host" : s[1]})

for node in nodes:
  print "Connecting to node%s with hostname %s." % (node["id"], node["host"])
  remote = SshMachine(node["host"], port = 22022, user = username, keyfile = path_to_keyfile)
  r_echo = remote["echo"]
  print r_echo["Erik is king."]
