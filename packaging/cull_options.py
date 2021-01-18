#!/usr/bin/env python3
import re
import argparse
import pathlib
import logging
import itertools
import pprint
import json

__doc__ = """Extract server options from options.c.

Output Python code for all options that options.c might send to the server.
This code is included in the rrsync script.

Note this parser does not understand #ifdef!

Note this is a fairly straight port of old-style perl code, so
it's kinda "get close enough, then bugger off the to pub" bodgy.
"""

output_template = """
# These options are the only options that rsync might send to the server,
# and only in the option format that the stock rsync produces.

# To disable a short-named option, add its letter to this string:
short_disabled = 's'

short_no_arg = {json.dumps(short_no_arg)}      # DO NOT REMOVE ANY
short_with_num = {json.dumps(short_with_num)}  # DO NOT REMOVE ANY

# To disable a long-named option, change its value to a -1.  The values mean:
# 0 = the option has no arg; 1 = the arg doesn't need any checking; 2 = only
# check the arg when receiving; and 3 = always check the arg.
long_opt = {json.dumps(long_opt)}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-v', '--verbose',
                        action='store_true')
    parser.add_argument('options_path',
                        nargs='?',
                        type=pathlib.Path,
                        default='../options.c')
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    with args.options_path.open() as f:
        # Extract the "server_options" function's lines.
        lines = list(
            itertools.takewhile(
                lambda line: line != '}\n',
                itertools.dropwhile(
                    lambda line: not line.startswith('void server_options'),
                    f)))

    short_no_arg = set()        # accumulator
    short_with_num = set()      # accumulator
    last_long_opt = None        # parser internal state

    # These include some extra long-args that BackupPC uses
    # (FIXME: wtf???)
    long_opt = {
        'block-size': 1,
        'daemon': -1,
        'debug': 1,
        'fake-super': 0,
        'fuzzy': 0,
        'group': 0,
        'hard-links': 0,
        'ignore-times': 0,
        'info': 1,
        'links': 0,
        'log-file': 3,
        'one-file-system': 0,
        'owner': 0,
        'perms': 0,
        'recursive': 0,
        'times': 0,
        'write-devices': -1
    }

    # NOTE: https://docs.python.org/3/whatsnew/3.8.html#assignment-expressions
    for line in lines:
        line = line.strip()
        if (m := re.match(r"argstr\[x\+\+\] = '([^.ie])'", line)):
            short_no_arg.add(m.group(1))
            last_long_opt = None
        elif (m := re.match(r'asprintf\([^,]+, "-([a-zA-Z0-9])%l?[ud]"', line)):
            short_no_arg.add(m.group(1))
            last_long_opt = None
        elif (m := re.match(r'args\[ac\+\+\] = "--([^"=]+)"', line)):
            last_long_opt = m.group(1)
            long_opt[last_long_opt] = long_opt.get(last_long_opt, 0)
        elif (last_long_opt and
              re.match(r'args\[ac\+\+\] = [^["\s]+;', line)):
            long_opt[last_long_opt] = 2
            last_long_opt = None
        elif re.match(r'return "--[^"]+-dest";', line):
            long_opt[last_long_opt] = 2
            last_long_opt = None
        elif (re.match(r'asprintf\([^,]+, "--[^"=]+=', line) or
              re.match(r'fmt = .*: "--[^"=]+)=', line)):
            long_opt[last_long_opt] = 1
            last_long_opt = None

    # Not strictly necessary in Python, but
    # convert the sets to sorted, flattened strings.
    short_no_arg = ''.join(sorted(short_no_arg))
    short_with_num = ''.join(sorted(short_with_num))

    # More bodginess -- hard-code the number of args for some options.
    for k, v in long_opt.items():
        if k.startswith('max-'):
            long_opt[opt] = 1
        if k.startswith('min-'):
            long_opt[opt] = 1
        if k == 'files-from':
            long_opt[opt] = 3
        # Oh no it's not using constants here!
        # It's using an expression, evaluated at ssh time,
        # which hard-codes in the variable that rrsync happens to use.
        # This is the point where I give up for today, because
        # something like json.dumps() can't express this!
        if k.startswith('remove-'):
            long_opt[opt] = f'-1 if only == "r" else {v}'
        if k.startswith('log-file'):
            long_opt[opt] = f'-1 if only == "r" else {v}'
        if k == 'sender':
            long_opt[opt] = f'-1 if only == "w" else {v}'

    print(output_template.format())


if __name__ == '__main__':
    main()
