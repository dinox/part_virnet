Partitioned Overlay Network
===========

Usage:
Edit startup_config.json.example with your planetlab details and rename to .json
(remove example).

On same computer (in different shells) execute
* `python monitor.py -p 12345`
* `python startup.py localhost:12345`

If you want to test the seq killing script add -k flag to startup.py

If you are behind firewall, remove that and try again. If you can't you will need 
to have tcp port 12345 open (or change that to free and open port of your choice).

Dependencies:
* Plumbum (pip install plumbum)
* Python 2.7.2
