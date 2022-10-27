#!/usr/bin/python

import sys
import zlib

doc_key = None
vbucket_num = None
num_keys = 1
arg_len = len(sys.argv)
loop_index = 1

while loop_index < arg_len:
    if sys.argv[loop_index] == "--key":
        doc_key = sys.argv[loop_index+1]
    elif sys.argv[loop_index] == "--vb":
        vbucket_num = int(sys.argv[loop_index+1])
    elif sys.argv[loop_index] == "--num_keys":
        num_keys = int(sys.argv[loop_index+1])
    loop_index += 2

if doc_key:
    vb_num = (((zlib.crc32(doc_key)) >> 16) & 0x7fff) & 1023
    print("VBucket:{0}, key: {1}".format(vb_num, doc_key))

if vbucket_num:
    print("VBucket: %s, Keys:" % vbucket_num)
    loop_index = 0
    key_count = 0
    while key_count != num_keys:
        t_doc_key = doc_key + "-" + str(loop_index+1)
        vb_num = (((zlib.crc32(t_doc_key)) >> 16) & 0x7fff) & 1023
        loop_index += 1
        if vb_num == vbucket_num:
            print(t_doc_key)
            key_count += 1
