
# evm loader

import idaapi
from idc import *

def accept_file(li, filename):
    if filename.endswith('.evm') or filename.endswith('.bytecode'):
        return {'format': "EVM", 'options': 1|0x8000}
    return 0

def load_file(li, neflags, format):
    
    # Select the PC processor module
    idaapi.set_processor_type("EVM", SETPROC_ALL|SETPROC_FATAL)
    
    # TODO: detect and emulate contract creation code
    li.seek(0)
    buf = li.read(li.size())
    if not buf:
        return 0

    if buf[0:2] == '0x':
        print "Detected hex"
        new_buf = buf[2:].strip().rstrip()
        buf_set = set()
        for c in new_buf:
            buf_set.update(c)
        hex_set = set(list('0123456789abcdef'))
        if buf_set <= hex_set: # subset
            print "Replacing original buffer with hex decoded version"
            buf = new_buf.decode('hex')

    # Load all shellcode into different segments
    start = 0x0
    seg = idaapi.segment_t()
    size = len(buf)
    end  = start + size
    
    # Create the segment
    seg.startEA = start
    seg.endEA   = end
    seg.bitness = 1 # 32-bit
    idaapi.add_segm_ex(seg, "evm", "CODE", 0)

    # TODO: make segments for stack, memory, storage

    # Copy the bytes
    idaapi.mem2base(buf, start, end)


    # check for swarm hash and make it data instead of code
    swarm_hash_address = buf.find('ebzzr0')
    if swarm_hash_address != -1:
        print "Swarm hash detected, making it data"
        for i in range(swarm_hash_address-1, swarm_hash_address+42):
            MakeByte(i)
        ida_bytes.set_cmt(swarm_hash_address-1, "swarm hash", True)
    # add entry point
    idaapi.add_entry(start, start, "start", 1) 

    # add comment to beginning of disassembly
    idaapi.describe(start, True, "EVM bytecode disassembly")

    # Mark for analysis
    AutoMark(start, AU_CODE)

    #setup_enums()
    return 1
