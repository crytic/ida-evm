import idc
import idaapi
from idc import *
from idaapi import *
import idautils

import known_hashes

'''
    Code from manticore
'''

class EVMAsm(object):
    ''' 
        EVM Instruction factory
        
        Example use::

            >>> from manticore.platforms.evm import EVMAsm
            >>> EVMAsm.disassemble_one('\\x60\\x10')
            Instruction(0x60, 'PUSH', 1, 0, 1, 0, 'Place 1 byte item on stack.', 16, 0)
            >>> EVMAsm.assemble_one('PUSH1 0x10')
            Instruction(0x60, 'PUSH', 1, 0, 1, 0, 'Place 1 byte item on stack.', 16, 0)
            >>> tuple(EVMAsm.disassemble_all('\\x30\\x31'))
            (Instruction(0x30, 'ADDRESS', 0, 0, 1, 2, 'Get address of currently executing account.', None, 0), 
             Instruction(0x31, 'BALANCE', 0, 1, 1, 20, 'Get balance of the given account.', None, 1))
            >>> tuple(EVMAsm.assemble_all('ADDRESS\\nBALANCE'))
            (Instruction(0x30, 'ADDRESS', 0, 0, 1, 2, 'Get address of currently executing account.', None, 0),
             Instruction(0x31, 'BALANCE', 0, 1, 1, 20, 'Get balance of the given account.', None, 1))
            >>> EVMAsm.assemble_hex(
            ...                         """PUSH1 0x60
            ...                            BLOCKHASH 
            ...                            MSTORE
            ...                            PUSH1 0x2
            ...                            PUSH2 0x100
            ...                         """
            ...                      )
            '0x606040526002610100'
            >>> EVMAsm.disassemble_hex('0x606040526002610100')
            'PUSH1 0x60\\nBLOCKHASH\\nMSTORE\\nPUSH1 0x2\\nPUSH2 0x100'
    '''
    class Instruction(object):
        def __init__(self, opcode, name, operand_size, pops, pushes, fee, description, operand=None, offset=0):
            '''
            This represents an EVM instruction. 
            EVMAsm will create this for you.

            :param opcode: the opcode value
            :param name: instruction name
            :param operand_size: immediate operand size in bytes
            :param pops: number of items popped from the stack
            :param pushes: number of items pushed into the stack
            :param fee: gas fee for the instruction
            :param description: textual description of the instruction
            :param operand: optional immediate operand
            :param offset: optional offset of this instruction in the program

            Example use::

                instruction = EVMAsm.assemble_one('PUSH1 0x10')
                print 'Instruction: %s'% instruction
                print '\tdescription:', instruction.description
                print '\tgroup:', instruction.group
                print '\taddress:', instruction.offset
                print '\tsize:', instruction.size
                print '\thas_operand:', instruction.has_operand
                print '\toperand_size:', instruction.operand_size
                print '\toperand:', instruction.operand
                print '\tsemantics:', instruction.semantics
                print '\tpops:', instruction.pops
                print '\tpushes:', instruction.pushes
                print '\tbytes:', '0x'+instruction.bytes.encode('hex')
                print '\twrites to stack:', instruction.writes_to_stack
                print '\treads from stack:', instruction.reads_from_stack
                print '\twrites to memory:', instruction.writes_to_memory
                print '\treads from memory:', instruction.reads_from_memory
                print '\twrites to storage:', instruction.writes_to_storage
                print '\treads from storage:', instruction.reads_from_storage
                print '\tis terminator', instruction.is_terminator


            '''
            self._opcode = opcode 
            self._name = name 
            self._operand_size = operand_size
            self._pops = pops
            self._pushes = pushes
            self._fee = fee
            self._description = description
            self._operand = operand           #Immediate operand if any
            if operand_size != 0 and operand is not None:
                    mask = (1<<operand_size*8)-1
                    if ~mask & operand:
                        raise ValueError("operand should be %d bits long"%(operand_size*8))
            self._offset=offset

        def __eq__(self, other):
            ''' Instructions are equal if all features match '''
            return self._opcode == other._opcode and\
            self._name == other._name and\
            self._operand == other._operand and\
            self._operand_size == other._operand_size and\
            self._pops == other._pops and\
            self._pushes == other._pushes and\
            self._fee == other._fee and\
            self._offset == other._offset and\
            self._description == other._description 

        def __repr__(self):
            output = 'Instruction(0x%x, %r, %d, %d, %d, %d, %r, %r, %r)'%(self._opcode, self._name, self._operand_size, self._pops, self._pushes, self._fee, self._description, self._operand, self._offset)
            return output


        def __str__(self):
            output = self.name + (' 0x%x'%self.operand if self.has_operand else '')
            return output

        @property
        def opcode(self):
            ''' The opcode as an integer ''' 
            return self._opcode

        @property
        def name(self):
            ''' The instruction name/mnemonic ''' 
            if self._name == 'PUSH':
                return 'PUSH%d'%self.operand_size
            elif self._name == 'DUP':
                return 'DUP%d'%self.pops
            elif self._name == 'SWAP':
                return 'SWAP%d'%(self.pops-1)
            elif self._name == 'LOG':
                return 'LOG%d'%(self.pops-2)
            return self._name
            
        def parse_operand(self, buf):
            ''' Parses an operand from buf 

                :param buf: a buffer
                :type buf: iterator/generator/string
            '''
            buf = iter(buf)
            try:
                operand = 0
                for _ in range(self.operand_size):
                    operand <<= 8
                    operand |= ord(next(buf))
                self._operand = operand
            except StopIteration:
                raise Exception("Not enough data for decoding")

        @property
        def operand_size(self):
            ''' The immediate operand size '''
            return self._operand_size

        @property
        def has_operand(self):
            ''' True if the instruction uses an immediate operand'''
            return self.operand_size > 0

        @property
        def operand(self):
            ''' The immediate operand '''
            return self._operand

        @property
        def pops(self):
            '''Number words popped from the stack'''
            return self._pops

        @property
        def pushes(self):
            '''Number words pushed to the stack'''
            return self._pushes

        @property
        def size(self):
            ''' Size of the encoded instruction '''
            return self._operand_size + 1

        @property
        def fee(self):
            ''' The basic gas fee of the instruction '''
            return self._fee

        @property
        def semantics(self):
            ''' Canonical semantics '''
            return self._name

        @property
        def description(self):
            ''' Coloquial description of the instruction '''
            return self._description

        @property
        def bytes(self):
            ''' Encoded instruction '''
            bytes = []
            bytes.append(chr(self._opcode))
            for offset in reversed(xrange(self.operand_size)):
                c = (self.operand >> offset*8 ) & 0xff 
                bytes.append(chr(c))
            return ''.join(bytes)

        @property
        def offset(self):
            '''Location in the program (optional)'''
            return self._offset

        @property
        def group(self):
            '''Instruction classification as per the yellow paper'''
            classes = {
                        0:   'Stop and Arithmetic Operations',
                        1:   'Comparison & Bitwise Logic Operations',
                        2:   'SHA3',
                        3:   'Environmental Information',
                        4:   'Block Information',
                        5:   'Stack, Memory, Storage and Flow Operations',
                        6:   'Push Operations',
                        7:   'Push Operations',
                        8:   'Duplication Operations',
                        9:   'Exchange Operations',
                        0xa: 'Logging Operations',
                        0xf: 'System operations'
                      }
            return classes.get(self.opcode>>4, 'Invalid instruction')

        @property
        def uses_stack(self):
            ''' True if the instruction reads/writes from/to the stack '''
            return self.reads_from_stack or self.writes_to_stack

        @property
        def reads_from_stack(self):
            ''' True if the instruction reads from stack '''
            return self.pops > 0

        @property
        def writes_to_stack(self):
            ''' True if the instruction writes to the stack '''
            return self.pushes > 0
            
        @property
        def reads_from_memory(self):
            ''' True if the instruction reads from memory '''
            return self.semantics in ('MLOAD','CREATE', 'CALL', 'CALLCODE', 'RETURN', 'DELEGATECALL', 'REVERT')

        @property
        def writes_to_memory(self):
            ''' True if the instruction writes to memory '''
            return self.semantics in ('MSTORE', 'MSTORE8', 'CALLDATACOPY', 'CODECOPY', 'EXTCODECOPY')
            
        @property
        def reads_from_memory(self):
            ''' True if the instruction reads from memory '''
            return self.semantics in ('MLOAD','CREATE', 'CALL', 'CALLCODE', 'RETURN', 'DELEGATECALL', 'REVERT')

        @property
        def writes_to_storage(self):
            ''' True if the instruction writes to the storage '''
            return self.semantics in ('SSTORE')

        @property
        def reads_from_storage(self):
            ''' True if the instruction reads from the storage '''
            return self.semantics in ('SLOAD')

        @property
        def is_terminator(self):
            ''' True if the instruction is a basic block terminator '''
            return self.semantics in ('RETURN', 'STOP', 'INVALID', 'JUMP', 'JUMPI', 'SELFDESTRUCT', 'REVERT')

        @property
        def is_branch(self):
            ''' True if the instruction is a jump'''
            return self.semantics in ('JUMP', 'JUMPI')

        @property
        def is_environmental(self):
            ''' True if the instruction access enviromental data '''
            return self.group == 'Environmental Information'
            
        @property
        def is_system(self):
            ''' True if the instruction is a system operation '''
            return self.group == 'System operations'

        @property
        def uses_block_info(self):
            ''' True if the instruction access block information'''
            return self.group == 'Block Information'

        @property
        def is_arithmetic(self):
            ''' True if the instruction is an arithmetic operation '''
            return  self.semantics in ('ADD', 'MUL', 'SUB', 'DIV', 'SDIV', 'MOD', 'SMOD', 'ADDMOD', 'MULMOD', 'EXP', 'SIGNEXTEND')
 
    #from http://gavwood.com/paper.pdf
    _table = {#opcode: (name, immediate_operand_size, pops, pushes, gas, description)
                0x00: ('STOP', 0, 0, 0, 0, 'Halts execution.'),
                0x01: ('ADD', 0, 2, 1, 3, 'Addition operation.'),
                0x02: ('MUL', 0, 2, 1, 5, 'Multiplication operation.'),
                0x03: ('SUB', 0, 2, 1, 3, 'Subtraction operation.'),
                0x04: ('DIV', 0, 2, 1, 5, 'Integer division operation.'),
                0x05: ('SDIV', 0, 2, 1, 5, 'Signed integer division operation (truncated).'),
                0x06: ('MOD', 0, 2, 1, 5, 'Modulo remainder operation.'),
                0x07: ('SMOD', 0, 2, 1, 5, 'Signed modulo remainder operation.'),
                0x08: ('ADDMOD', 0, 3, 1, 8, 'Modulo addition operation.'),
                0x09: ('MULMOD', 0, 3, 1, 8, 'Modulo multiplication operation.'),
                0x0a: ('EXP', 0, 2, 1, 10, 'Exponential operation.'),
                0x0b: ('SIGNEXTEND', 0, 2, 1, 5, "Extend length of two's complement signed integer."),
                0x10: ('LT', 0, 2, 1, 3, 'Less-than comparision.'),
                0x11: ('GT', 0, 2, 1, 3, 'Greater-than comparision.'),
                0x12: ('SLT', 0, 2, 1, 3, 'Signed less-than comparision.'),
                0x13: ('SGT', 0, 2, 1, 3, 'Signed greater-than comparision.'),
                0x14: ('EQ', 0, 2, 1, 3, 'Equality comparision.'),
                0x15: ('ISZERO', 0, 1, 1, 3, 'Simple not operator.'),
                0x16: ('AND', 0, 2, 1, 3, 'Bitwise AND operation.'),
                0x17: ('OR', 0, 2, 1, 3, 'Bitwise OR operation.'),
                0x18: ('XOR', 0, 2, 1, 3, 'Bitwise XOR operation.'),
                0x19: ('NOT', 0, 1, 1, 3, 'Bitwise NOT operation.'),
                0x1a: ('BYTE', 0, 2, 1, 3, 'Retrieve single byte from word.'),
                0x1b: ('SHL', 0, 2, 1, 3, 'Shift Left.'),
                0x1c: ('SHR', 0, 2, 1, 3, 'Logical Shift Right.'),
                0x1d: ('SAR', 0, 2, 1, 3, 'Arithmetic Shift Right.'),
                0x20: ('SHA3', 0, 2, 1, 30, 'Compute Keccak-256 hash.'),
                0x30: ('ADDRESS', 0, 0, 1, 2, 'Get address of currently executing account     .'),
                0x31: ('BALANCE', 0, 1, 1, 20, 'Get balance of the given account.'),
                0x32: ('ORIGIN', 0, 0, 1, 2, 'Get execution origination address.'),
                0x33: ('CALLER', 0, 0, 1, 2, 'Get caller address.'),
                0x34: ('CALLVALUE', 0, 0, 1, 2, 'Get deposited value by the instruction/transaction responsible for this execution.'),
                0x35: ('CALLDATALOAD', 0, 1, 1, 3, 'Get input data of current environment.'),
                0x36: ('CALLDATASIZE', 0, 0, 1, 2, 'Get size of input data in current environment.'),
                0x37: ('CALLDATACOPY', 0, 3, 0, 3, 'Copy input data in current environment to memory.'),
                0x38: ('CODESIZE', 0, 0, 1, 2, 'Get size of code running in current environment.'),
                0x39: ('CODECOPY', 0, 3, 0, 3, 'Copy code running in current environment to memory.'),
                0x3a: ('GASPRICE', 0, 0, 1, 2, 'Get price of gas in current environment.'),
                0x3b: ('EXTCODESIZE', 0, 1, 1, 20, "Get size of an account's code."),
                0x3c: ('EXTCODECOPY', 0, 4, 0, 20, "Copy an account's code to memory."),
                0x3d: ('RETURNDATASIZE', 0, 0, 1, 2, "Pushes the size of the return data buffer onto the stack."),
                0x3e: ('RETURNDATACOPY', 0, 3, 0, 3, "Copies data from the return data buffer to memory."),
                0x3f: ('EXTCODEHASH', 0, 1, 1, 700, "Returns the keccak256 hash of a contract's code."),
                0x40: ('BLOCKHASH', 0, 1, 1, 20, 'Get the hash of one of the 256 most recent complete blocks.'),
                0x41: ('COINBASE', 0, 0, 1, 2, "Get the block's beneficiary address."),
                0x42: ('TIMESTAMP', 0, 0, 1, 2, "Get the block's timestamp."),
                0x43: ('NUMBER', 0, 0, 1, 2, "Get the block's number."),
                0x44: ('DIFFICULTY', 0, 0, 1, 2, "Get the block's difficulty."),
                0x45: ('GASLIMIT', 0, 0, 1, 2, "Get the block's gas limit."),
                0x46: ('CHAINID', 0, 0, 1, 2, "Returns the current chain's EIP-155 unique identifier."),
                0x48: ('BASEFEE', 0, 0, 1, 2, "Returns the value of the base fee of the current block it is executing in."),
                0x50: ('POP', 0, 1, 0, 2, 'Remove item from stack.'),
                0x51: ('MLOAD', 0, 1, 1, 3, 'Load word from memory.'),
                0x52: ('MSTORE', 0, 2, 0, 3, 'Save word to memory.'),
                0x53: ('MSTORE8', 0, 2, 0, 3, 'Save byte to memory.'),
                0x54: ('SLOAD', 0, 1, 1, 50, 'Load word from storage.'),
                0x55: ('SSTORE', 0, 2, 0, 0, 'Save word to storage.'),
                0x56: ('JUMP', 0, 1, 0, 8, 'Alter the program counter.'),
                0x57: ('JUMPI', 0, 2, 0, 10, 'Conditionally alter the program counter.'),
                0x58: ('GETPC', 0, 0, 1, 2, 'Get the value of the program counter prior to the increment.'),
                0x59: ('MSIZE', 0, 0, 1, 2, 'Get the size of active memory in bytes.'),
                0x5a: ('GAS', 0, 0, 1, 2, 'Get the amount of available gas, including the corresponding reduction the amount of available gas.'),
                0x5b: ('JUMPDEST', 0, 0, 0, 1, 'Mark a valid destination for jumps.'),
                0x60: ('PUSH', 1, 0, 1, 0, 'Place 1 byte item on stack.'),
                0x61: ('PUSH', 2, 0, 1, 0, 'Place 2-byte item on stack.'),
                0x62: ('PUSH', 3, 0, 1, 0, 'Place 3-byte item on stack.'),
                0x63: ('PUSH', 4, 0, 1, 0, 'Place 4-byte item on stack.'),
                0x64: ('PUSH', 5, 0, 1, 0, 'Place 5-byte item on stack.'),
                0x65: ('PUSH', 6, 0, 1, 0, 'Place 6-byte item on stack.'),
                0x66: ('PUSH', 7, 0, 1, 0, 'Place 7-byte item on stack.'),
                0x67: ('PUSH', 8, 0, 1, 0, 'Place 8-byte item on stack.'),
                0x68: ('PUSH', 9, 0, 1, 0, 'Place 9-byte item on stack.'),
                0x69: ('PUSH', 10, 0, 1, 0, 'Place 10-byte item on stack.'),
                0x6a: ('PUSH', 11, 0, 1, 0, 'Place 11-byte item on stack.'),
                0x6b: ('PUSH', 12, 0, 1, 0, 'Place 12-byte item on stack.'),
                0x6c: ('PUSH', 13, 0, 1, 0, 'Place 13-byte item on stack.'),
                0x6d: ('PUSH', 14, 0, 1, 0, 'Place 14-byte item on stack.'),
                0x6e: ('PUSH', 15, 0, 1, 0, 'Place 15-byte item on stack.'),
                0x6f: ('PUSH', 16, 0, 1, 0, 'Place 16-byte item on stack.'),
                0x70: ('PUSH', 17, 0, 1, 0, 'Place 17-byte item on stack.'),
                0x71: ('PUSH', 18, 0, 1, 0, 'Place 18-byte item on stack.'),
                0x72: ('PUSH', 19, 0, 1, 0, 'Place 19-byte item on stack.'),
                0x73: ('PUSH', 20, 0, 1, 0, 'Place 20-byte item on stack.'),
                0x74: ('PUSH', 21, 0, 1, 0, 'Place 21-byte item on stack.'),
                0x75: ('PUSH', 22, 0, 1, 0, 'Place 22-byte item on stack.'),
                0x76: ('PUSH', 23, 0, 1, 0, 'Place 23-byte item on stack.'),
                0x77: ('PUSH', 24, 0, 1, 0, 'Place 24-byte item on stack.'),
                0x78: ('PUSH', 25, 0, 1, 0, 'Place 25-byte item on stack.'),
                0x79: ('PUSH', 26, 0, 1, 0, 'Place 26-byte item on stack.'),
                0x7a: ('PUSH', 27, 0, 1, 0, 'Place 27-byte item on stack.'),
                0x7b: ('PUSH', 28, 0, 1, 0, 'Place 28-byte item on stack.'),
                0x7c: ('PUSH', 29, 0, 1, 0, 'Place 29-byte item on stack.'),
                0x7d: ('PUSH', 30, 0, 1, 0, 'Place 30-byte item on stack.'),
                0x7e: ('PUSH', 31, 0, 1, 0, 'Place 31-byte item on stack.'),
                0x7f: ('PUSH', 32, 0, 1, 0, 'Place 32-byte (full word) item on stack.'),
                0x80: ('DUP', 0, 1, 2, 3, 'Duplicate 1st stack item.'),
                0x81: ('DUP', 0, 2, 3, 3, 'Duplicate 2nd stack item.'),
                0x82: ('DUP', 0, 3, 4, 3, 'Duplicate 3rd stack item.'),
                0x83: ('DUP', 0, 4, 5, 3, 'Duplicate 4th stack item.'),
                0x84: ('DUP', 0, 5, 6, 3, 'Duplicate 5th stack item.'),
                0x85: ('DUP', 0, 6, 7, 3, 'Duplicate 6th stack item.'),
                0x86: ('DUP', 0, 7, 8, 3, 'Duplicate 7th stack item.'),
                0x87: ('DUP', 0, 8, 9, 3, 'Duplicate 8th stack item.'),
                0x88: ('DUP', 0, 9, 10, 3, 'Duplicate 9th stack item.'),
                0x89: ('DUP', 0, 10, 11, 3, 'Duplicate 10th stack item.'),
                0x8a: ('DUP', 0, 11, 12, 3, 'Duplicate 11th stack item.'),
                0x8b: ('DUP', 0, 12, 13, 3, 'Duplicate 12th stack item.'),
                0x8c: ('DUP', 0, 13, 14, 3, 'Duplicate 13th stack item.'),
                0x8d: ('DUP', 0, 14, 15, 3, 'Duplicate 14th stack item.'),
                0x8e: ('DUP', 0, 15, 16, 3, 'Duplicate 15th stack item.'),
                0x8f: ('DUP', 0, 16, 17, 3, 'Duplicate 16th stack item.'),
                0x90: ('SWAP', 0, 2, 2, 3, 'Exchange 1st and 2nd stack items.'),
                0x91: ('SWAP', 0, 3, 3, 3, 'Exchange 1st and 3rd stack items.'),
                0x92: ('SWAP', 0, 4, 4, 3, 'Exchange 1st and 4th stack items.'),
                0x93: ('SWAP', 0, 5, 5, 3, 'Exchange 1st and 5th stack items.'),
                0x94: ('SWAP', 0, 6, 6, 3, 'Exchange 1st and 6th stack items.'),
                0x95: ('SWAP', 0, 7, 7, 3, 'Exchange 1st and 7th stack items.'),
                0x96: ('SWAP', 0, 8, 8, 3, 'Exchange 1st and 8th stack items.'),
                0x97: ('SWAP', 0, 9, 9, 3, 'Exchange 1st and 9th stack items.'),
                0x98: ('SWAP', 0, 10, 10, 3, 'Exchange 1st and 10th stack items.'),
                0x99: ('SWAP', 0, 11, 11, 3, 'Exchange 1st and 11th stack items.'),
                0x9a: ('SWAP', 0, 12, 12, 3, 'Exchange 1st and 12th stack items.'),
                0x9b: ('SWAP', 0, 13, 13, 3, 'Exchange 1st and 13th stack items.'),
                0x9c: ('SWAP', 0, 14, 14, 3, 'Exchange 1st and 14th stack items.'),
                0x9d: ('SWAP', 0, 15, 15, 3, 'Exchange 1st and 15th stack items.'),
                0x9e: ('SWAP', 0, 16, 16, 3, 'Exchange 1st and 16th stack items.'),
                0x9f: ('SWAP', 0, 17, 17, 3, 'Exchange 1st and 17th stack items.'),
                0xa0: ('LOG', 0, 2, 0, 375, 'Append log record with no topics.'),
                0xa1: ('LOG', 0, 3, 0, 750, 'Append log record with one topic.'),
                0xa2: ('LOG', 0, 4, 0, 1125, 'Append log record with two topics.'),
                0xa3: ('LOG', 0, 5, 0, 1500, 'Append log record with three topics.'),
                0xa4: ('LOG', 0, 6, 0, 1875, 'Append log record with four topics.'),
                0xf0: ('CREATE', 0, 3, 1, 32000, 'Create a new account with associated code.'),
                0xf1: ('CALL', 0, 7, 1, 40, 'Message-call into an account.'),
                0xf2: ('CALLCODE', 0, 7, 1, 40, "Message-call into this account with alternative account's code."),
                0xf3: ('RETURN', 0, 2, 0, 0, 'Halt execution returning output data.'),
                0xf4: ('DELEGATECALL', 0, 6, 1, 40, "Message-call into this account with an alternative account's code, but persisting into this account with an alternative account's code."),
                0xf5: ('BREAKPOINT', 0, 0, 0, 40, 'Not in yellow paper FIXME'),
                0xf6: ('RNGSEED', 0, 1, 1, 0, 'Not in yellow paper FIXME'),
                0xf7: ('SSIZEEXT', 0, 2, 1, 0, 'Not in yellow paper FIXME'),
                0xf8: ('SLOADBYTES', 0, 3, 0, 0, 'Not in yellow paper FIXME'),
                0xf9: ('SSTOREBYTES', 0, 3, 0, 0, 'Not in yellow paper FIXME'),
                0xfa: ('SSIZE', 0, 1, 1, 40, 'Not in yellow paper FIXME'),
                0xfb: ('STATEROOT', 0, 1, 1, 0, 'Not in yellow paper FIXME'),
                0xfc: ('TXEXECGAS', 0, 0, 1, 0, 'Not in yellow paper FIXME'),
                0xfd: ('REVERT', 0, 2, 0, 0, 'Stop execution and revert state changes, without consuming all provided gas and providing a reason.'),
                0xfe: ('INVALID', 0, 0, 0, 0, 'Designated invalid instruction.'),
                0xff: ('SELFDESTRUCT', 0, 1, 0, 5000, 'Halt execution and register account for later deletion.')
            }

    @staticmethod
    #@memoized
    def _get_reverse_table():
        ''' Build an internal table used in the assembler '''
        reverse_table = {}
        for (opcode, (name, immediate_operand_size, pops, pushes, gas, description)) in EVMAsm._table.items():
            mnemonic = name
            if name == 'PUSH':
                mnemonic = '%s%d'%(name, (opcode&0x1f) + 1)
            elif name in ('SWAP', 'LOG', 'DUP'):
                mnemonic = '%s%d'%(name, (opcode&0xf) + 1)

            reverse_table[mnemonic] = opcode, name, immediate_operand_size, pops, pushes, gas, description
        return reverse_table

    @staticmethod
    def assemble_one(assembler, offset=0):
        ''' Assemble one EVM instruction from its textual representation. 
            
            :param assembler: assembler code for one instruction
            :param offset: offset of the instruction in the bytecode (optional)
            :return: An Instruction object

            Example use::

                >>> print evm.EVMAsm.assemble_one('LT')
            

        '''
        try:
            _reverse_table = EVMAsm._get_reverse_table()
            assembler = assembler.strip().split()
            opcode, name, operand_size, pops, pushes, gas, description = _reverse_table[assembler[0].upper()]
            if operand_size > 0:
                assert len(assembler) == 2
                operand = int(assembler[1],0)
            else:
                assert len(assembler) == 1
                operand = None

            return EVMAsm.Instruction(opcode, name, operand_size, pops, pushes, gas, description, operand=operand, offset=offset)
        except:
            raise Exception("Something wrong at offset %d"%offset)

    @staticmethod
    def assemble_all(assembler, offset=0):
        ''' Assemble a sequence of textual representation of EVM instructions 

            :param assembler: assembler code for any number of instructions
            :param offset: offset of the first instruction in the bytecode(optional)
            :return: An generator of Instruction objects

            Example use::
            
                >>> evm.EVMAsm.encode_one("""PUSH1 0x60
                    PUSH1 0x40
                    MSTORE
                    PUSH1 0x2
                    PUSH2 0x108
                    PUSH1 0x0
                    POP
                    SSTORE
                    PUSH1 0x40
                    MLOAD
                    """)

        '''
        if isinstance(assembler, str):
            assembler = assembler.split('\n')
        assembler = iter(assembler)
        for line in assembler:
            if not line.strip():
                continue
            instr = EVMAsm.assemble_one(line, offset=offset)
            yield instr
            offset += instr.size

    @staticmethod
    def disassemble_one(bytecode, offset=0):
        ''' Decode a single instruction from a bytecode

            :param bytecode: the bytecode stream 
            :param offset: offset of the instruction in the bytecode(optional)
            :type bytecode: iterator/sequence/str
            :return: an Instruction object

            Example use::
            
                >>> print EVMAsm.assemble_one('PUSH1 0x10')

        '''
        bytecode = iter(bytecode)
        opcode = ord(next(bytecode))
        invalid = ('INVALID', 0, 0, 0, 0, 'Unknown opcode')
        name, operand_size, pops, pushes, gas, description = EVMAsm._table.get(opcode, invalid)
        instruction = EVMAsm.Instruction(opcode, name, operand_size, pops, pushes, gas, description, offset=offset)
        if instruction.has_operand:
            instruction.parse_operand(bytecode)

        return instruction

    @staticmethod
    def disassemble_all(bytecode, offset=0):
        ''' Decode all instructions in bytecode

            :param bytecode: an evm bytecode (binary)
            :param offset: offset of the first instruction in the bytecode(optional)
            :type bytecode: iterator/sequence/str
            :return: An generator of Instruction objects

            Example use::
            
                >>> for inst in EVMAsm.decode_all(bytecode):
                ...    print inst

                ... 
                PUSH1 0x60
                PUSH1 0x40
                MSTORE
                PUSH1 0x2
                PUSH2 0x108
                PUSH1 0x0
                POP
                SSTORE
                PUSH1 0x40
                MLOAD


        '''

        bytecode = iter(bytecode)
        while True:
            instr = EVMAsm.disassemble_one(bytecode, offset=offset)
            offset += instr.size
            yield instr

    @staticmethod
    def disassemble(bytecode, offset=0):
        ''' Disassemble an EVM bytecode 

            :param bytecode: binary representation of an evm bytecode (hexadecimal)
            :param offset: offset of the first instruction in the bytecode(optional)
            :type bytecode: str
            :return: the text representation of the aseembler code

            Example use::
            
                >>> EVMAsm.disassemble("\x60\x60\x60\x40\x52\x60\x02\x61\x01\x00")
                ...
                PUSH1 0x60
                BLOCKHASH
                MSTORE
                PUSH1 0x2
                PUSH2 0x100

        '''
        return '\n'.join(map(str, EVMAsm.disassemble_all(bytecode, offset=offset)))

    @staticmethod
    def assemble(asmcode, offset=0):
        ''' Assemble an EVM program 

            :param asmcode: an evm assembler program
            :param offset: offset of the first instruction in the bytecode(optional)
            :type asmcode: str
            :return: the hex representation of the bytecode

            Example use::
            
                >>> EVMAsm.assemble(  """PUSH1 0x60
                                           BLOCKHASH
                                           MSTORE
                                           PUSH1 0x2
                                           PUSH2 0x100
                                        """
                                     )
                ...
                "\x60\x60\x60\x40\x52\x60\x02\x61\x01\x00"
        '''
        return ''.join(map(lambda x:x.bytes, EVMAsm.assemble_all(asmcode, offset=offset)))

    @staticmethod
    def disassemble_hex(bytecode, offset=0):
        ''' Disassemble an EVM bytecode 

            :param bytecode: canonical representation of an evm bytecode (hexadecimal)
            :param int offset: offset of the first instruction in the bytecode(optional)
            :type bytecode: str
            :return: the text representation of the aseembler code

            Example use::
            
                >>> EVMAsm.disassemble_hex("0x6060604052600261010")
                ...
                PUSH1 0x60
                BLOCKHASH
                MSTORE
                PUSH1 0x2
                PUSH2 0x100

        '''
        if bytecode.startswith('0x'):
            bytecode = bytecode[2:]
        bytecode = bytecode.decode('hex')
        return EVMAsm.disassemble(bytecode, offset=offset)

    @staticmethod
    def assemble_hex(asmcode, offset=0):
        ''' Assemble an EVM program 

            :param asmcode: an evm assembler program
            :param offset: offset of the first instruction in the bytecode(optional)
            :type asmcode: str
            :return: the hex representation of the bytecode

            Example use::
            
                >>> EVMAsm.assemble_hex(  """PUSH1 0x60
                                           BLOCKHASH
                                           MSTORE
                                           PUSH1 0x2
                                           PUSH2 0x100
                                        """
                                     )
                ...
                "0x6060604052600261010"
        '''
        return '0x' + EVMAsm.assemble(asmcode, offset=offset).encode('hex')





# thanks to https://github.com/themadinventor/ida-xtensa/issues/12 for showing all the ida7 sdk changes
# and thanks quarsklab for an IDP overview at https://blog.quarkslab.com/ida-processor-module.html


class EVMProcessor(idaapi.processor_t):
    id = 0x8000 + 0x6576
    flag = PR_ADJSEGS | PRN_HEX | PR_ASSEMBLE
    cnbits = 8
    dnbits = 8
    psnames = ["evm"]
    plnames = ["EVM"]
    segreg_size = 0
    instruc_start = 0
    reg_names = ["SP"]
    assembler = {
        "header": [".evm"],
        "flag": AS_NCHRE | ASH_HEXF0 | ASD_DECF0 | ASO_OCTF0 | ASB_BINF0 | AS_NOTAB,
        "uflag": 0,
        "name": "evm assembler",
        "origin": ".org",
        "end": ".end",
        "cmnt": ";",
        "ascsep": "'",
        "accsep": "'",
        "esccodes": "\"'",
        "a_ascii": ".ascii",
        "a_byte": ".byte",
        "a_word": ".word",
        "a_dword": ".dword",
        "a_bss": "dfs %s",
        "a_seg": "seg",
        "a_curip": "PC",
        "a_public": "",
        "a_weak": "",
        "a_extrn": ".extern",
        "a_comdef": "",
        "a_align": ".align",
        "lbrace": "(",
        "rbrace": ")",
        "a_mod": "%",
        "a_band": "&",
        "a_bor": "|",
        "a_xor": "^",
        "a_bnot": "~",
        "a_shl": "<<",
        "a_shr": ">>",
        "a_sizeof_fmt": "size %s",
    }


    def trace_sp(self, insn):
        pass

    @staticmethod
    def get_prototype(num):
        hash_str = '0x%x' %(num, )
        function_prototype = known_hashes.knownHashes.get(hash_str, '').encode('ascii','ignore')
        return function_prototype

    def notify_emu(self, insn):
        feature = insn.get_canon_feature()
        #print "emulating", insn.get_canon_mnem(), hex(feature)

        mnemonic = insn.get_canon_mnem()
        if mnemonic == "PUSH4":
            function_prototype = self.get_prototype(self.get_operand(insn[0]))
            if function_prototype:
                ida_bytes.set_cmt(insn.ea, function_prototype, True)
            
        elif mnemonic == "CALLI":
            # operand 0 is the address
            # operand 1 is the function hash
            add_cref(insn.ea, insn.ea + insn.size, fl_JN) # false branch is following instruction
            addr = insn[0].addr
            add_cref(insn.ea, addr, fl_CN) # true branch is stored in operand index 0
            ida_bytes.set_cmt(insn.ea, "JUMPI", True)

            jump_hash = insn[1].value
            function_prototype = self.get_prototype(jump_hash)
            label = '%s (0x%x)' %(function_prototype, jump_hash)
            if not ida_lines.get_extra_cmt(addr, ida_lines.E_PREV + 0): # don't dup
                ida_lines.add_extra_cmt(addr, True, label)
                if function_prototype == '':
                    function_prototype = 'func_0x%x' % (jump_hash, )
                set_name(addr, function_prototype, SN_NOCHECK|SN_NOWARN|SN_FORCE)
           
        elif mnemonic == "JUMPI":
            # add ref to next instruction for false branch
            add_cref(insn.ea, insn.ea + insn.size, fl_JN)
           
            # maybe we have a simple puch
            prev_insn = idautils.DecodePreviousInstruction(insn.ea)
            if prev_insn:
                if prev_insn.get_canon_mnem().startswith("PUSH"):
                    jump_addr = self.get_operand(prev_insn[0])
                    add_cref(insn.ea, jump_addr, fl_JN)

        elif mnemonic == "JUMP":
            prev_insn = idautils.DecodePreviousInstruction(insn.ea)
            if prev_insn:
                # TODO: implement stack modeling to resolve actual top value of stack
                if prev_insn.get_canon_mnem().startswith("PUSH"):
                    jump_addr = self.get_operand(prev_insn[0])
                    #print "found jump to", hex(jump_addr)
                    add_cref(insn.ea, jump_addr, fl_JN)
                    # TODO: adjust function boundary to include all code
                    #func = get_func(insn.ea)
                    #if func:
                    #    #print "appending new tail"
                    #    #append_func_tail(func, jump_addr, BADADDR)
                    #    #reanalyze_function(func)

        flows = (feature & CF_STOP) == 0
        if flows:
            add_cref(insn.ea, insn.ea + insn.size, fl_F)

        if may_trace_sp():
            if flows:
                self.trace_sp(insn)
            else:
                idc.recalc_spd(insn.ea)

        return True

    def notify_func_bounds(self, code, func_ea, max_func_end_ea):
        """
        find_func_bounds() finished its work
        The module may fine tune the function bounds
        args:
          possible code - one of FIND_FUNC_XXX (check find_func_bounds)
          func_ea - func start ea
          max_func_end_ea (from the kernel's point of view)
        returns: possible_return_code
        """
        #print hex(func_ea), hex(max_func_end_ea), code
        #print print_insn_mnem(max_func_end_ea-1)
        #append_func_tail(func, jump_addr, BADADDR)
        #reanalyze_function(func)
        return FIND_FUNC_OK

    @staticmethod
    def get_operand(op):
        operand = 0
        if op.type == o_idpspec0:
            # re-read all of the bytes from instruction
            buf = ida_bytes.get_bytes(op.addr, op.specval) # specval stores number of bytes for operand
            
            for i in range(len(buf)):
                operand <<= 8
                operand |= ord(buf[i])
        elif op.type == o_near:
            operand = op.addr
        return operand

    def notify_out_operand(self, ctx, op):
        if op.type == o_idpspec0:
            operand = self.get_operand(op)
            ctx.out_line("0x%x" %(operand, ))
        elif op.type == o_near:
            operand_value = self.get_operand(op)
            r = ctx.out_name_expr(op, operand_value, BADADDR)
            if not r:
                ctx.out_line("0x%x" %(operand_value, ))

        return True

    def notify_out_insn(self, ctx):
        ctx.out_mnemonic()
        if ctx.insn[0].type == o_idpspec0:
                ctx.out_char(" ")
                ctx.out_one_operand(0)
        elif ctx.insn[0].type == o_near:
            ctx.out_char(" ")
            ctx.out_one_operand(0)
        ctx.set_gen_cmt()
        ctx.flush_outbuf()
        return


    def notify_ana(self, insn):
        ea = insn.ea
        bytes_left = chunk_start(ea) + chunk_size(ea) - ea
        bytecode = ida_bytes.get_bytes(insn.ea, bytes_left) # get remaining bytes in chunk
        try:
            instruction = EVMAsm.disassemble_one(bytecode)
        except Exception as e:
            print(e)
            return

        insn.size = instruction.size

        #initialize operands to voids
        operands = [insn[i] for i in xrange(1, 6)]
        for o in operands:
            o.type = o_void

        # set the instruction
        insn.itype = self.instruction_index.get(instruction._opcode, 0)

        #detect "CALLI"
        if instruction.name == "JUMPI":
            # TODO: check for 4 prev instructions where there is a DUP2 in the middle
            #decode 3 previous instructions
            prev_insns = [insn]
            for i in range(3):
                prev_insns.append(idautils.DecodePreviousInstruction(prev_insns[-1].ea))
            prev_insns.pop(0) # remove orig

            # sanity check previous instructions
            for i in prev_insns:
                #print i.get_canon_mnem(),
                if i.ea == ida_idaapi.BADADDR:
                    print('ERROR')

            if (prev_insns[0].get_canon_mnem().startswith("PUSH2") and
                    prev_insns[1].get_canon_mnem().startswith("EQ") and
                    prev_insns[2].get_canon_mnem().startswith("PUSH4")):
                # switch it to a "CALLI"
                insn.itype = 1 # CALLI instruction index

                jump_target = self.get_operand(prev_insns[0][0]) # operand on the push2
                insn[0].type = o_near
                insn[0].addr = jump_target


                function_hash = self.get_operand(prev_insns[2][0]) # operand on the push4
                insn[1].type = o_imm
                insn[1].value = function_hash

                # set the target to be a function
                AutoMark(jump_target, AU_PROC)

        if instruction.has_operand:
            insn[0].type = o_idpspec0 # custom type
            insn[0].dtype = dt_byte32 
            insn[0].addr = ea + 1 # operand is located after opcode
            insn[0].specval = instruction.operand_size
            #o.specval = str(instruction.operand)
        

        # return the instruction size here
        return insn.size 


    def notify_assemble(self, ea, cs, ip, use32, line):
        try:
            asm = EVMAsm.assemble_one(line, 0)
        except Exception as e:
            print("Error trying to assemble '%s': %s" %(line, e))
            return None

        return asm.bytes

    def __init__(self):
        processor_t.__init__(self)

        self.reg_names = ["SP", "virtualCS", "virtualDS"]
        self.reg_first_sreg = self.reg_names.index("virtualCS")
        self.reg_code_sreg = self.reg_names.index("virtualCS")

        self.reg_last_sreg =  self.reg_names.index("virtualDS")
        self.reg_data_sreg =  self.reg_names.index("virtualDS")

        self.instruc = [] # why is there no T in this?
        self.instruction_index = {}
        
        #put first instruction as invalid
        self.instruc.append({'name':"INVALID", 'feature':0})
        self.instruction_index[0x100] = 0
        self.instruc.append({'name':"CALLI", 'feature':CF_USE2|CF_STOP|CF_CALL}) # pseudo instruction 
        self.instruction_index[0x101] = 1
        i = len(self.instruc)
        for (mnemonic, info) in EVMAsm._get_reverse_table().iteritems(): #_table.iteritems():
            features = 0 # initially zero

            if info[2] != 0: # has immediate
                features |= CF_USE1

            if mnemonic in ('RETURN', 'STOP', 'INVALID', 'JUMP', 'JUMPI', 'SELFDESTRUCT', 'REVERT'):
                features |= CF_STOP

            if mnemonic in ('JUMP', 'JUMPI'):
                features |= CF_JUMP

            self.instruc.append({'name': mnemonic, 'feature':features})
            self.instruction_index[info[0]] = i # look up index into instruc from opcode
            if mnemonic == 'RETURN':
                self.icode_return = i

            i += 1

        self.instruc_end = len(self.instruc)



def PROCESSOR_ENTRY():
    return EVMProcessor()
