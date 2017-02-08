#!/usr/local/bin/python
"""
Python program for listing the vms on an ESX / vCenter host
"""
from __future__ import print_function

import atexit

import json

from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim

import tools.cli as cli

import re,sys

# Probably not the best idea but we use self signed certs and the
# warnings are annoying.
import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()

import ssl
context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
context.verify_mode = ssl.CERT_NONE
#
#

def connect_vc(hostname,username,password,prt=443):
    si = None
    si = connect.SmartConnect(host=hostname,user=username, pwd=password, port=prt, sslContext=context)
    content = si.RetrieveContent()
    return (si,content)

    atexit.register(connect.Disconnect, service_instance)

# Build a list of datacenters and return them as a dictionary
# We only look at the rootFolder so we know anything that has a ChildEntity.vmFolder is a datacenter.
def get_datacenters(content):
    dc = {}
    children = content.rootFolder.childEntity
    for child in children:
        if hasattr(child, 'vmFolder'): # it's a datacenter
            dc[child.name]={}
            dc[child.name]['dc'] = child
            if sys.stdout.isatty():
                print("Datacenter: %-30s" % child.name, end='\r')
                sys.stdout.flush()
     	else:
     		continue # some other non-datacenter type object

    if sys.stdout.isatty():
        print("")

    return dc

def get_clusters(dcenter):
    clusterList = dcenter.hostFolder.childEntity
    
    cl = {}
    for cluster in clusterList:
        cl[cluster.name]=[]
        if hasattr(cluster,'host'):
            for h in cluster.host:
                cl[cluster.name].append(h.name)
            if sys.stdout.isatty():
                print("Datacenter: %-s Cluster: %s %10s" % (dcenter.name,cluster.name,""), end='\r')
                sys.stdout.flush()    

    if sys.stdout.isatty():
        print("")
    return cl

def get_vms(datacenter):
    vms = {}
    vm_list = datacenter.childEntity
    
    for child in vm_list:
        if hasattr(child,'childEntity'):
            vms.update(get_vms(child))
        else:
            if isinstance(child,vim.VirtualMachine):
                vms[child.name] = child
            else:
                print("[%s]" % type(child))
            
    return vms

def get_nets(datacenter):
    return

def get_dstores(datacenter):
    return

def find_cluster(clusters,guesthost):
    for c in clusters:
        for h in clusters[c]:
            if h == guesthost:
                return c  # Found it.

    return guesthost # Can't find cluster, could be individual host.
    
def main():
    """
    Simple command-line program for listing the virtual machines on a system.
    """

    args = cli.get_args()

    audit = {}
    try:
        service_instance,content = connect_vc(args.host,args.user,args.password,args.port)

        if sys.stdout.isatty():
            print("vCenter: %s" % args.host)
        
        content = service_instance.RetrieveContent()

        container = content.rootFolder  # starting point to look into
        datacenters = get_datacenters(content)
        for dc in datacenters:
            datacenters[dc]['clusters'] = get_clusters(datacenters[dc]['dc'])

            datacenters[dc]['vms'] = get_vms(datacenters[dc]['dc'].vmFolder)
             
            get_nets(dc)
            get_dstores(dc)

        vmcount=0
        
        for dc in datacenters:
            for vm in sorted(datacenters[dc]['vms'],key=lambda s: s.lower()):
                vmcount+=1
                v = datacenters[dc]['vms'][vm]
                c = find_cluster(datacenters[dc]['clusters'],v.runtime.host.name)
                vort = "Template" if v.summary.config.template == True else "VM"
                audit[v.name]={}
                audit[v.name]['datacenter'] = dc
                audit[v.name]['cluster']    = c
                audit[v.name]['type']       = vort
                audit[v.name]['hostname']   = v.summary.guest.hostName
                audit[v.name]['guestid']    = v.config.guestId
                audit[v.name]['fullname']   = v.summary.config.guestFullName
                audit[v.name]['state']      = v.runtime.powerState
                audit[v.name]['ip']         = v.guest.ipAddress
                if sys.stdout.isatty():
                    print(vmcount,"Guests processed",end='\r')
                    sys.stdout.flush()
#                print("%-15s:%-10s %-8s %-30s %-30s %s %s %s %s" % (dc, c, vort,v.name,v.summary.guest.hostName, v.config.guestId, v.summary.config.guestFullName,v.guest.guestState,v.guest.ipAddress  ))
                #print vort, v.name, v.summary.guest.hostName, v.guest.guestId, v.summary.config.guestFullName,v.guest.guestState,v.guest.ipAddress #,v.summary
#        print("\ncount:",vmcount)
 
        print(json.dumps(audit, indent=4, separators=(',', ': ')))
    
    except vmodl.MethodFault as error:
        print("Caught vmodl fault : " + error.msg)
        return -1

    return 0

# Start program
if __name__ == "__main__":
    main()
