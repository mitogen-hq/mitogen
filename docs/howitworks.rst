
How econtext Works
==================

To accomplish the seemingly magical feat of bootstrapping a remote Python
process without any software installed on the remote machine requires a little
effort. The steps involved are not likely to be immediately obvious to the
casual reader, and required several iterations of research to discover, so we
document them thoroughly below.


The First Stage
---------------

, and with a custom *argv[0]*


Python Command Line
###################


Configuring argv[0]
###################


Source Minimization
###################


Signalling Success
##################


ExternalContext main()
----------------------


Reaping The First Stage
#######################


Generating A Synthetic `econtext` Package
#########################################


Setup The Broker And Master Context
###################################


Setup Logging
#############


The Module Importer
###################


Standard IO Redirection
#######################


Function Call Dispatch
######################



The Broker
----------


Differences Between Master And Slave Brokers
############################################

* Self destruct.


The Module Importer
-------------------

Child Package Enumeration
#########################


Negative Cache Hits
###################


