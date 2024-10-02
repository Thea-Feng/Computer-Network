import argparse
from copy import copy
from pydoc import resolve
from dnslib import DNSRecord,RCODE,QTYPE,RR, DNSQuestion
import socket
from dnslib.server import DNSServer,DNSHandler,BaseResolver

from requests import request

Host = "127.0.0.1"
ip_set = []
cnt = 0
ROOT_SERVERS = ("198.41.0.4",
                "199.9.14.201",
                "192.33.4.12",
                "199.7.91.13",
                "192.203.230.10",
                "192.5.5.241",
                "192.112.36.4",
                "198.97.190.53",
                "192.36.148.17",
                "192.58.128.30",
                "193.0.14.129",
                "199.7.83.42",
                "202.12.27.33")

# ProxyResolver is copy from dnslib
class ProxyResolver(BaseResolver):

    def __init__(self,address,port,timeout=0,strip_aaaa=False):
        self.address = address
        self.port = port
        self.timeout = timeout
        self.strip_aaaa = strip_aaaa

    def resolve(self,request,handler):
        try:
            if handler.protocol == 'udp':
                proxy_r = request.send(self.address,self.port,
                                timeout=self.timeout)
            else:
                proxy_r = request.send(self.address,self.port,
                                tcp=True,timeout=self.timeout)
            reply = DNSRecord.parse(proxy_r)
        except socket.timeout:
            reply = request.reply()
            reply.header.rcode = getattr(RCODE,'NXDOMAIN')
        return reply
    
def search_additional(response, target_name, qtype, resolved, cache):
    rrsets = response.ar
    for rrset in rrsets:
        if rrset.rtype == 1: # A type
            try:
                response, resolved = search_recursive(target_name, qtype, str(rrset.rdata), resolved, cache) # how to get ip
            except socket.timeout:
                resolved = False
        if resolved:
            break
    return response, resolved
    
def search_authority(response, target_name, qtype, resolved, cache):
    rrsets = response.auth
    ns_ip = ""
    for rrset in rrsets:
        if rrset.rtype == 2: # NS type
            ns_ip = cache.get(str(rrset.rdata))
            if not ns_ip:
                ns_Arecord = search(str(rrset.rdata), 1, cache)
                ns_ip = str(ns_Arecord.rr[0].rdata) # get name of ff ????
                cache[str(rrset.rdata)] = ns_ip
            try:
                response, resolved = search_recursive(target_name, qtype, ns_ip, resolved, cache)
            except socket.timeout:
                resolved = False
        elif rrset.rtype == 6: # SOA type
            resolved = True
            break
        if resolved:
            break
    return response, resolved
        
def search(target_name, qtype, cache):
    resolved = False
    i = 0
    while i < len(ROOT_SERVERS):

        ip_ = ""
        copy_name = str(target_name)
        next_dot = copy_name.find(".")

        while not ip_ and next_dot > -1:
            ip_ = cache.get(copy_name)
            copy_name = copy_name[next_dot+1:]
            next_dot = copy_name.find('.')

        if not ip_:
            ip_ = ROOT_SERVERS[i]
        
        try:
            response, resolved = search_recursive(target_name, qtype, ip_, resolved, cache)
            if response.header.a:
                ans_type = response.rr[0].rtype
                if qtype != 5 and ans_type == 5: # CNAME
                    target_name = str(response.rr[0].rdata) # get name of RR
                    resolved = False
                    response = search(target_name, qtype, cache)
                elif qtype != ans_type:
                    return {}
                return response
            elif response.header.auth and response.auth[0].rtype == 10: # SOA
                break
            else:
                i += 1

        except socket.timeout:
            print("SEARCH: time out")
            i += 1
    return response

def update_cache(response, cache):
    name = response.auth[0].rdata
    rrsets = response.ar
    for rr in rrsets:
        if rr.rtype == 1:
            cache[str(rr.rname)] = str(rr.rdata) # here is a big problem

def search_recursive(target_name, qtype, ip_, resolved, cache):
    global cnt
    cnt += 1

    d = DNSRecord()
    d.add_question(DNSQuestion(target_name))
    try:
        print("No. {} research pass through ip: {}".format(cnt, ip_))
        a = d.send(ip_, tcp=False, timeout=3)
        response = d.parse(a)
        # print(response)
        # response = DNSRecord.parse(request.send(ip_, 1234, timeout=3))
        if response.header.a:
            resolved = True
            return response, resolved
        elif response.header.ar:
            if response.header.auth:
                update_cache(response, cache)
            response, resolved = search_additional(response, target_name, qtype, resolved, cache)
        elif response.header.auth and not resolved:
            response, resolved = search_authority(response, target_name, qtype, resolved, cache)
        return response, resolved

    except socket.timeout:
        print("----Time out in recursive search, another trying----")
        return None, False
            

def send_udp(data,host,port):
    """
        Helper function to send/receive DNS UDP request
    """
    print("send_upd voke")
    sock = None
    try:
        sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.sendto(data,(host,port))
        response,server = sock.recvfrom(8192)
        # print("HAHAHAHAHAH", response)
        return response
    finally:
        if (sock is not None):
            sock.close()

def print_result(ret_response):
    print('------------------Result--------------------')
    FORMATS = (("CNAME", "{alias} an alias for {name}"),
           ("A", "{name} has address {address}"))
    for type, str in FORMATS:
        for ret in ret_response.get(type, []):
            print(str.format(**ret))

def get_result(name, cache):
    global cnt
    print("-----------Search for {} CNAME type begins-----------".format(name))
    ret_response = {}
    cnt = 0
    response = search(name, 5, cache)
    clist = []
    if response != {}:
        for ans in response.rr:
            clist.append({"name": str(ans.rname), "alias": str(ans.rdata) + "is"})
    else:
        clist.append({"name": name, "alias": "Do not exist"})
    
    print("-----------Search for {} A type begins-----------".format(name))
    cnt = 0
    if cache.get(name):
        alist = [{"name": name, "address": cache[name]}]
    else:
        response = search(name, 1, cache)
        alist = []
        for ans in response.rr:
            alist.append({"name": str(ans.rname), "address": str(ans.rdata)})
    
    ret_response['CNAME'] = clist
    ret_response['A'] = alist

    cache['answers'][name] = ret_response

    return ret_response

resolver = ProxyResolver("8.8.8.8",53,5,False)
server = DNSServer(resolver,port=1234,address=Host,logger=None,tcp=False)
server.start_thread()
cache = {}
cache['answers'] = {}
argument_parse = argparse.ArgumentParser()
argument_parse.add_argument("-name", nargs="+", help="Names to search")

argument_parse.add_argument("-flag", help="1 for recursive search, 0 for directly search", default=1,type=int)
args = argument_parse.parse_args()

count = 0
flag = args.flag
if flag:
    for name in args.name:
        count += 1
        name = name + '.'
        ret = cache.get('answers').get(name)
        if ret:
            print("--------------Result from cache-------------")
            print_result(ret)
        else:
            print_result(get_result(name, cache))
        print()
else: 
    for name in args.name:
        d = DNSRecord()
        d.add_question(DNSQuestion(name))
        a = d.send(Host, 1234, tcp=False)
        res = d.parse(a)
        print('------------------Direct Search for{}----------------'.format(name))
        print(res)
        print()
server.stop()