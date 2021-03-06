##   The contents of this file are subject to the Mozilla Public License
##   Version 1.1 (the "License"); you may not use this file except in
##   compliance with the License. You may obtain a copy of the License at
##   http://www.mozilla.org/MPL/
##
##   Software distributed under the License is distributed on an "AS IS"
##   basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
##   License for the specific language governing rights and limitations
##   under the License.
##
##   The Original Code is RabbitMQ.
##
##   The Initial Developers of the Original Code are LShift Ltd,
##   Cohesive Financial Technologies LLC, and Rabbit Technologies Ltd.
##
##   Portions created before 22-Nov-2008 00:00:00 GMT by LShift Ltd,
##   Cohesive Financial Technologies LLC, or Rabbit Technologies Ltd
##   are Copyright (C) 2007-2008 LShift Ltd, Cohesive Financial
##   Technologies LLC, and Rabbit Technologies Ltd.
##
##   Portions created by LShift Ltd are Copyright (C) 2007-2009 LShift
##   Ltd. Portions created by Cohesive Financial Technologies LLC are
##   Copyright (C) 2007-2009 Cohesive Financial Technologies
##   LLC. Portions created by Rabbit Technologies Ltd are Copyright
##   (C) 2007-2009 Rabbit Technologies Ltd.
##
##   All Rights Reserved.
##
##   Contributor(s): ______________________________________.
##

from __future__ import nested_scopes

import sys
sys.path.append("../rabbitmq-codegen")  # in case we're next to an experimental revision
sys.path.append("codegen")              # in case we're building from a distribution package

from amqp_codegen import *
import string
import re

erlangTypeMap = {
    'octet': 'octet',
    'shortstr': 'shortstr',
    'longstr': 'longstr',
    'short': 'shortint',
    'long': 'longint',
    'longlong': 'longlongint',
    'bit': 'bit',
    'table': 'table',
    'timestamp': 'timestamp',
}

# Coming up with a proper encoding of AMQP tables in JSON is too much
# hassle at this stage. Given that the only default value we are
# interested in is for the empty table, we only support that.
def convertTable(d):
    if len(d) == 0:
        return "[]"
    else: raise 'Non-empty table defaults not supported', d

erlangDefaultValueTypeConvMap = {
    bool : lambda x: str(x).lower(),
    str : lambda x: "<<\"" + x + "\">>",
    int : lambda x: str(x),
    float : lambda x: str(x),
    dict: convertTable,
    unicode: lambda x: "<<\"" + x.encode("utf-8") + "\">>"
}

def erlangize(s):
    s = s.replace('-', '_')
    s = s.replace(' ', '_')
    return s

AmqpMethod.erlangName = lambda m: "'" + erlangize(m.klass.name) + '.' + erlangize(m.name) + "'"

def erlangConstantName(s):
    return '_'.join(re.split('[- ]', s.upper()))

class PackedMethodBitField:
    def __init__(self, index):
        self.index = index
        self.domain = 'bit'
        self.contents = []

    def extend(self, f):
        self.contents.append(f)

    def count(self):
        return len(self.contents)

    def full(self):
        return self.count() == 8
    
def genErl(spec):
    def erlType(domain):
        return erlangTypeMap[spec.resolveDomain(domain)]

    def fieldTypeList(fields):
        return '[' + ', '.join([erlType(f.domain) for f in fields]) + ']'

    def fieldNameList(fields):
        return '[' + ', '.join([erlangize(f.name) for f in fields]) + ']'

    def fieldTempList(fields):
        return '[' + ', '.join(['F' + str(f.index) for f in fields]) + ']'

    def fieldMapList(fields):
        return ', '.join([erlangize(f.name) + " = F" + str(f.index) for f in fields])

    def genLookupMethodName(m):
        print "lookup_method_name({%d, %d}) -> %s;" % (m.klass.index, m.index, m.erlangName())

    def genMethodId(m):
        print "method_id(%s) -> {%d, %d};" % (m.erlangName(), m.klass.index, m.index)

    def genMethodHasContent(m):
        print "method_has_content(%s) -> %s;" % (m.erlangName(), str(m.hasContent).lower())
    
    def genMethodIsSynchronous(m):
        hasNoWait = "nowait" in fieldNameList(m.arguments)
        if m.isSynchronous and hasNoWait:
          print "is_method_synchronous(#%s{nowait = NoWait}) -> not(NoWait);" % (m.erlangName())
        else:
          print "is_method_synchronous(#%s{}) -> %s;" % (m.erlangName(), str(m.isSynchronous).lower())

    def genMethodFieldTypes(m):
        """Not currently used - may be useful in future?"""
        print "method_fieldtypes(%s) -> %s;" % (m.erlangName(), fieldTypeList(m.arguments))

    def genMethodFieldNames(m):
        print "method_fieldnames(%s) -> %s;" % (m.erlangName(), fieldNameList(m.arguments))

    def packMethodFields(fields):
        packed = []
        bitfield = None
        for f in fields:
            if erlType(f.domain) == 'bit':
                if not(bitfield) or bitfield.full():
                    bitfield = PackedMethodBitField(f.index)
                    packed.append(bitfield)
                bitfield.extend(f)
            else:
                bitfield = None
                packed.append(f)
        return packed

    def methodFieldFragment(f):
        type = erlType(f.domain)
        p = 'F' + str(f.index)
        if type == 'shortstr':
            return p+'Len:8/unsigned, '+p+':'+p+'Len/binary'
        elif type == 'longstr':
            return p+'Len:32/unsigned, '+p+':'+p+'Len/binary'
        elif type == 'octet':
            return p+':8/unsigned'
        elif type == 'shortint':
            return p+':16/unsigned'
        elif type == 'longint':
            return p+':32/unsigned'
        elif type == 'longlongint':
            return p+':64/unsigned'
        elif type == 'timestamp':
            return p+':64/unsigned'
        elif type == 'bit':
            return p+'Bits:8'
        elif type == 'table':
            return p+'Len:32/unsigned, '+p+'Tab:'+p+'Len/binary'

    def genFieldPostprocessing(packed):
        for f in packed:
            type = erlType(f.domain)
            if type == 'bit':
                for index in range(f.count()):
                    print "  F%d = ((F%dBits band %d) /= 0)," % \
                          (f.index + index,
                           f.index,
                           1 << index)
            elif type == 'table':
                print "  F%d = rabbit_binary_parser:parse_table(F%dTab)," % \
                      (f.index, f.index)
            else:
                pass

    def genDecodeMethodFields(m):
        packedFields = packMethodFields(m.arguments)
        binaryPattern = ', '.join([methodFieldFragment(f) for f in packedFields])
        if binaryPattern:
            restSeparator = ', '
        else:
            restSeparator = ''
        recordConstructorExpr = '#%s{%s}' % (m.erlangName(), fieldMapList(m.arguments))
        print "decode_method_fields(%s, <<%s>>) ->" % (m.erlangName(), binaryPattern)
        genFieldPostprocessing(packedFields)
        print "  %s;" % (recordConstructorExpr,)

    def genDecodeProperties(c):
        print "decode_properties(%d, PropBin) ->" % (c.index)
        print "  %s = rabbit_binary_parser:parse_properties(%s, PropBin)," % \
              (fieldTempList(c.fields), fieldTypeList(c.fields))
        print "  #'P_%s'{%s};" % (erlangize(c.name), fieldMapList(c.fields))

    def genFieldPreprocessing(packed):
        for f in packed:
            type = erlType(f.domain)
            if type == 'bit':
                print "  F%dBits = (%s)," % \
                      (f.index,
                       ' bor '.join(['(bitvalue(F%d) bsl %d)' % (x.index, x.index - f.index)
                                     for x in f.contents]))
            elif type == 'table':
                print "  F%dTab = rabbit_binary_generator:generate_table(F%d)," % (f.index, f.index)
                print "  F%dLen = size(F%dTab)," % (f.index, f.index)
            elif type in ['shortstr', 'longstr']:
                print "  F%dLen = size(F%d)," % (f.index, f.index)
            else:
                pass

    def genEncodeMethodFields(m):
        packedFields = packMethodFields(m.arguments)
        print "encode_method_fields(#%s{%s}) ->" % (m.erlangName(), fieldMapList(m.arguments))
        genFieldPreprocessing(packedFields)
        print "  <<%s>>;" % (', '.join([methodFieldFragment(f) for f in packedFields]))

    def genEncodeProperties(c):
        print "encode_properties(#'P_%s'{%s}) ->" % (erlangize(c.name), fieldMapList(c.fields))
        print "  rabbit_binary_generator:encode_properties(%s, %s);" % \
              (fieldTypeList(c.fields), fieldTempList(c.fields))

    def massageConstantClass(cls):
        # We do this because 0.8 uses "soft error" and 8.1 uses "soft-error".
        return erlangConstantName(cls)

    def genLookupException(c,v,cls):
        mCls = massageConstantClass(cls)
        if mCls == 'SOFT_ERROR': genLookupException1(c,'false')
        elif mCls == 'HARD_ERROR': genLookupException1(c, 'true')
        elif mCls == '': pass
        else: raise 'Unknown constant class', cls

    def genLookupException1(c,hardErrorBoolStr):
        n = erlangConstantName(c)
        print 'lookup_amqp_exception(%s) -> {%s, ?%s, <<"%s">>};' % \
              (n.lower(), hardErrorBoolStr, n, n)

    methods = spec.allMethods()

    print """-module(rabbit_framing).
-include("rabbit_framing.hrl").

-export([lookup_method_name/1]).

-export([method_id/1]).
-export([method_has_content/1]).
-export([is_method_synchronous/1]).
-export([method_fieldnames/1]).
-export([decode_method_fields/2]).
-export([decode_properties/2]).
-export([encode_method_fields/1]).
-export([encode_properties/1]).
-export([lookup_amqp_exception/1]).

bitvalue(true) -> 1;
bitvalue(false) -> 0;
bitvalue(undefined) -> 0.
"""
    for m in methods: genLookupMethodName(m)
    print "lookup_method_name({_ClassId, _MethodId} = Id) -> exit({unknown_method_id, Id})."

    for m in methods: genMethodId(m)
    print "method_id(Name) -> exit({unknown_method_name, Name})."

    for m in methods: genMethodHasContent(m)
    print "method_has_content(Name) -> exit({unknown_method_name, Name})."

    for m in methods: genMethodIsSynchronous(m)
    print "is_method_synchronous(Name) -> exit({unknown_method_name, Name})."

    for m in methods: genMethodFieldNames(m)
    print "method_fieldnames(Name) -> exit({unknown_method_name, Name})."

    for m in methods: genDecodeMethodFields(m)
    print "decode_method_fields(Name, BinaryFields) ->"
    print "  rabbit_misc:frame_error(Name, BinaryFields)."

    for c in spec.allClasses(): genDecodeProperties(c)
    print "decode_properties(ClassId, _BinaryFields) -> exit({unknown_class_id, ClassId})."

    for m in methods: genEncodeMethodFields(m)
    print "encode_method_fields(Record) -> exit({unknown_method_name, element(1, Record)})."

    for c in spec.allClasses(): genEncodeProperties(c)
    print "encode_properties(Record) -> exit({unknown_properties_record, Record})."

    for (c,v,cls) in spec.constants: genLookupException(c,v,cls)
    print "lookup_amqp_exception(Code) ->"
    print "  rabbit_log:warning(\"Unknown AMQP error code '~p'~n\", [Code]),"
    print "  {true, ?INTERNAL_ERROR, <<\"INTERNAL_ERROR\">>}."    


def genHrl(spec):
    def erlType(domain):
        return erlangTypeMap[spec.resolveDomain(domain)]

    def fieldNameList(fields):
        return ', '.join([erlangize(f.name) for f in fields])

    def fieldNameListDefaults(fields):
        def fillField(field):
            result = erlangize(f.name)
            if field.defaultvalue != None:
                conv_fn = erlangDefaultValueTypeConvMap[type(field.defaultvalue)]
                result += ' = ' + conv_fn(field.defaultvalue)
            return result
        return ', '.join([fillField(f) for f in fields])
    
    methods = spec.allMethods()

    print "-define(PROTOCOL_VERSION_MAJOR, %d)." % (spec.major)
    print "-define(PROTOCOL_VERSION_MINOR, %d)." % (spec.minor)
    print "-define(PROTOCOL_PORT, %d)." % (spec.port)

    for (c,v,cls) in spec.constants:
        print "-define(%s, %s)." % (erlangConstantName(c), v)

    print "%% Method field records."
    for m in methods:
        print "-record(%s, {%s})." % (m.erlangName(), fieldNameListDefaults(m.arguments))

    print "%% Class property records."
    for c in spec.allClasses():
        print "-record('P_%s', {%s})." % (erlangize(c.name), fieldNameList(c.fields))

def generateErl(specPath):
    genErl(AmqpSpec(specPath))

def generateHrl(specPath):
    genHrl(AmqpSpec(specPath))
    
if __name__ == "__main__":
    do_main(generateHrl, generateErl)

